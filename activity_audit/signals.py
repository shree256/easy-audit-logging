import inspect

from functools import wraps
from typing import Any, List

import structlog.contextvars as ctx

from django.apps import apps
from django.db import models, transaction
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver
from django.forms.models import model_to_dict

from activity_audit.config import get_logger
from activity_audit.unregistered import UNREGISTERED_CLASSES

_log = get_logger("audit.model")

EVENT_TYPES = [
    "CREATE",
    "UPDATE",
    "DELETE",
    "BULK_CREATE",
    "BULK_UPDATE",
    "M2M",
    "PRE_CREATE",
    "PRE_UPDATE",
    "PRE_DELETE",
]


def should_audit(instance_or_class):
    """Return True or False to indicate whether the instance or class should be audited."""
    # do not audit any model listed in UNREGISTERED_CLASSES
    for unregistered_class in UNREGISTERED_CLASSES:
        # Skip None values (e.g., when silk is not installed)
        if unregistered_class is None:
            continue
        # Handle instances: isinstance works for instances
        if isinstance(instance_or_class, unregistered_class):
            return False
        # Handle classes: check if it's the same class or a subclass
        if inspect.isclass(instance_or_class):
            try:
                if issubclass(instance_or_class, unregistered_class):
                    return False
            except TypeError:
                # issubclass can raise TypeError if arguments are not classes
                pass
    return True


_patched_models: set = set()
_queryset_patched: bool = False


def patch_queryset_bulk_methods() -> None:
    """Patch QuerySet.bulk_create and bulk_update exactly once."""
    global _queryset_patched
    if _queryset_patched:
        return
    _queryset_patched = True

    original_bulk_create = models.QuerySet.bulk_create
    original_bulk_update = models.QuerySet.bulk_update

    @wraps(original_bulk_create)
    def bulk_create_with_signals(
        self, objs: List[models.Model], *args: Any, **kwargs: Any
    ) -> List[models.Model]:
        if not objs:
            return original_bulk_create(self, objs, *args, **kwargs)

        created_objs = original_bulk_create(self, objs, *args, **kwargs)

        model_class = self.model
        if not should_audit(model_class):
            return created_objs

        first_obj = created_objs[0]
        push_log(
            f"{EVENT_TYPES[3]} event by {model_class.__name__} (id: {first_obj.pk})",
            model_class.__name__,
            EVENT_TYPES[3],
            str(first_obj.pk),
            instance_to_dict(first_obj),
            {"total_count": len(created_objs)},
        )
        return created_objs

    @wraps(original_bulk_update)
    def bulk_update_with_signals(
        self, objs: List[models.Model], fields: List[str], batch_size=None
    ) -> None:
        if not objs:
            return original_bulk_update(self, objs, fields, batch_size)

        result = original_bulk_update(self, objs, fields, batch_size)

        model_class = self.model
        if not should_audit(model_class):
            return result

        first_obj = objs[0]
        push_log(
            f"{EVENT_TYPES[4]} event by {model_class.__name__}",
            model_class.__name__,
            EVENT_TYPES[4],
            str(first_obj.pk),
            instance_to_dict(first_obj),
            {"total_count": len(objs), "fields": fields},
        )
        return result

    models.QuerySet.bulk_create = bulk_create_with_signals
    models.QuerySet.bulk_update = bulk_update_with_signals


def push_log(
    message: str,
    model: str,
    event_type: str,
    instance_id: str,
    instance_repr: str,
    extra: dict = {},
) -> None:
    try:
        # Snapshot contextvars now — on_commit fires after the transaction commits
        # and the middleware may have already cleared contextvars by then.
        ctx_vars = ctx.get_contextvars()
        bound = _log.bind(
            model=model,
            instance_id=str(instance_id),
            event_type=event_type,
            request_id=ctx_vars.get("request_id", ""),
            user_id=ctx_vars.get("user_id", ""),
            user_info=ctx_vars.get("user_info", {}),
            instance_repr=instance_repr,
            extra=extra,
        )

        def safe_audit_log():
            try:
                bound.audit(message)
            except Exception as e:
                _log.error("Failed to write audit log", error=str(e))

        transaction.on_commit(safe_audit_log)
    except Exception as e:
        _log.error("Failed to prepare audit log", error=str(e))


def instance_to_dict(instance: models.Model) -> dict:
    return model_to_dict(instance, fields=[f.name for f in instance._meta.fields])


def patch_model_event(model_class: type[models.Model]) -> None:
    """Monkey patch a model to add signal handling capabilities."""

    if model_class not in _patched_models:
        _patched_models.add(model_class)

        # Store the original methods
        original_save = model_class.save

        # SAVE ---------------------------------------------------------------------------
        @wraps(original_save)
        def save_with_signals(self: models.Model, *args: Any, **kwargs: Any) -> None:
            is_new = self._state.adding

            # Call the original save method
            original_save(self, *args, **kwargs)

            # Log the event
            event_type = EVENT_TYPES[0] if is_new else EVENT_TYPES[1]

            instance_repr = instance_to_dict(self)

            push_log(
                f"{event_type} event by {model_class.__name__} (id: {self.pk})",
                model_class.__name__,
                event_type,
                str(self.pk),
                instance_repr,
            )

        # PRE_SAVE ----------------------------------------------------------------------
        @receiver(pre_save, sender=model_class)
        def handle_pre_save(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            if not should_audit(instance):
                return

            is_new = instance._state.adding
            event_type = (
                EVENT_TYPES[6] if is_new else EVENT_TYPES[7]
            )  # PRE_CREATE or PRE_UPDATE

            # For new instances, we might not have a pk yet, so use a placeholder
            instance_id = str(instance.pk) if instance.pk else "pending"
            instance_repr = instance_to_dict(instance)

            push_log(
                f"{event_type} event by {model_class.__name__} (id: {instance_id})",
                model_class.__name__,
                event_type,
                instance_id,
                instance_repr,
            )

        # Replace the methods
        model_class.save = save_with_signals

        # DELETE -----------------------------------------------------------------------
        @receiver(pre_delete, sender=model_class)
        def handle_pre_delete(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            if not should_audit(instance):
                return

            instance_repr = instance_to_dict(instance)

            push_log(
                f"{EVENT_TYPES[8]} event by {model_class.__name__} (id: {instance.pk})",
                model_class.__name__,
                EVENT_TYPES[8],  # PRE_DELETE
                str(instance.pk),
                instance_repr,
            )

        # Add delete signal handling
        @receiver(post_delete, sender=model_class)
        def handle_delete(
            sender: type[models.Model], instance: models.Model, **kwargs: Any
        ) -> None:
            instance_repr = instance_to_dict(instance)

            push_log(
                f"{EVENT_TYPES[2]} event by {model_class.__name__} (id: {instance.pk})",
                model_class.__name__,
                EVENT_TYPES[2],
                str(instance.pk),
                instance_repr,
            )

        # M2M ------------------------------------------------------------------------
        for field in model_class._meta.many_to_many:

            @receiver(m2m_changed, sender=getattr(model_class, field.name).through)
            def handle_m2m_changed(
                sender: type[models.Model],
                instance: models.Model,
                action: str,
                pk_set: set,
                _field_name: str = field.name,
                **kwargs: Any,
            ) -> None:
                if action not in ["post_add", "post_remove", "post_clear"]:
                    return

                push_log(
                    f"M2M {action} event by {model_class.__name__} (id: {instance.pk})",
                    model_class.__name__,
                    EVENT_TYPES[5],
                    str(instance.pk),
                    {"id": str(instance.pk)},
                    {
                        "action": action,
                        "field_name": _field_name,
                        "related_ids": list(map(str, pk_set)) if pk_set else [],
                    },
                )


def setup_model_signals() -> None:
    """Set up signals for all models in the project."""
    patch_queryset_bulk_methods()
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            if not should_audit(model):
                continue

            if model not in _patched_models:
                patch_model_event(model)


# Initialize signals when the module is imported
setup_model_signals()
