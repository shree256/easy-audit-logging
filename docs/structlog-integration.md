# Structlog Integration — Design & Migration Guide

> Authored: 2026-06-16
> Scope: Evaluating structlog as a replacement / complement to the stdlib `logging` layer in `django-activity-audit`

---

## Current Architecture (Baseline)

| Component | File | Responsibility |
|-----------|------|----------------|
| Custom log levels (`AUDIT=21`, `API=22`, `LOGIN=23`) | `logger_levels.py` | Monkey-patched onto `logging.Logger` |
| Named loggers (`audit.model`, `audit.request`, `audit.login`) | `signals.py:21`, `middleware.py:16`, `utils.py:150` | One logger per concern |
| Context carriers (`request_id`, `user_id`) | `middleware.py:8–82` | `asgiref.local.Local()` thread-locals |
| Payload construction | `signals.py:123–152` (`push_log`) | Manually builds dict, passed as `extra={}` |
| Formatters | `formatters.py` | Manually serialize `LogRecord.extra` to JSON |
| Handlers | `handlers.py` | `RotatingFileHandler` + async `QueueHandler` variants |

### What push_log() does today

```python
# signals.py:123-152
def push_log(message, model, event_type, instance_id, instance_repr, extra={}):
    user_id, user_info = get_user_details()      # pulls from thread-local
    request_id = get_request_id()                # pulls from thread-local
    payload = {
        "model": model,
        "event_type": event_type,
        "request_id": request_id or "",
        "user_id": user_id,
        "user_info": user_info,
        "instance_id": str(instance_id),
        "instance_repr": instance_repr,
        "extra": extra,
    }
    transaction.on_commit(lambda: logger.audit(message, extra=payload))
```

Every field is packed manually, every call site must import and invoke `get_request_id()` / `get_user_details()`.

---

## Pros of Structlog

### 1. Context binding replaces manual dict packing

With structlog, fields bound at request entry flow automatically to every log call in that request — no explicit retrieval needed:

```python
# middleware.py — bind once at request start
import structlog.contextvars as ctx

ctx.bind_contextvars(
    request_id=request_id,
    user_id=user_id,
    user_info=user_info,
)

# signals.py — push_log becomes lean
log = structlog.get_logger("audit.model")

def push_log(message, model, event_type, instance_id, instance_repr, extra={}):
    transaction.on_commit(lambda: log.audit(
        message,
        model=model,
        event_type=event_type,
        instance_id=str(instance_id),
        instance_repr=instance_repr,
        extra=extra,
    ))
    # request_id, user_id, user_info injected automatically by merge_contextvars
```

### 2. `structlog.contextvars` replaces `asgiref.local.Local()`

The entire `_thread_locals` block in `middleware.py:8–82` (`set_request_id`, `get_request_id`, `set_current_request`, `get_current_user`, `clear_request`, etc.) is replaced by three calls:

```python
# request start
structlog.contextvars.bind_contextvars(request_id=uuid, user_id=uid, user_info=info)

# request end (in finally block)
structlog.contextvars.clear_contextvars()
```

`contextvars` is async-native — it scopes to the current `asyncio.Task`, so concurrent async requests never bleed context into each other. The current `asgiref.local.Local()` approach requires careful `clear_request()` discipline to avoid leaks (see `improvements.md` — issue #7).

### 3. Processor pipeline — composable and testable

The four monolithic formatters (`AppFormatter`, `APIFormatter`, `AuditFormatter`, `LoginFormatter`) in `formatters.py` each manually extract fields from `LogRecord` and serialize to JSON (~150 lines total). Structlog replaces them with a composable processor list:

```python
import structlog
from structlog.processors import CallsiteParameter

shared_processors = [
    structlog.contextvars.merge_contextvars,          # inject request_id, user_id, user_info
    structlog.processors.add_log_level,               # adds "level" key
    structlog.processors.TimeStamper(fmt="iso"),      # ISO 8601 timestamp
    structlog.processors.CallsiteParameterAdder([     # file + line — see below
        CallsiteParameter.FILENAME,
        CallsiteParameter.LINENO,
        CallsiteParameter.FUNC_NAME,
    ]),
    structlog.processors.JSONRenderer(),              # final JSON serialization
]

structlog.configure(
    processors=shared_processors,
    wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```

Each processor is a pure function — easy to test or swap individually. Adding a new field means appending one processor, not editing four formatters.

### 4. `CallsiteParameterAdder` — file and line in every signal log

**This directly addresses the question: "when performing audit action in signals, can I get file local too along logger?"**

`CallsiteParameterAdder` walks the call stack once per log call and injects:

| Parameter | Captured value (example) |
|-----------|--------------------------|
| `FILENAME` | `signals.py` |
| `LINENO` | `146` |
| `FUNC_NAME` | `push_log` |
| `MODULE` | `signals` |
| `PATHNAME` | `/app/activity_audit/signals.py` |

No changes to `push_log()` — the processor chain handles it. Every `push_log()` call gets:

```json
{
    "timestamp": "2026-06-16T10:22:45.123Z",
    "level": "audit",
    "event": "CREATE event for Author (id: abc123)",
    "filename": "signals.py",
    "lineno": 146,
    "func_name": "push_log",
    "model": "Author",
    "event_type": "CREATE",
    "request_id": "f3c9a1b2-...",
    "user_id": "cae8ffb4-..."
}
```

> If you want the callsite that triggered `.save()` in user code (not `signals.py` itself), that requires `inspect.stack()` traversal. This is expensive and fragile — the signal-layer callsite is the correct and meaningful audit origin for most use cases.

### 5. `structlog.testing.capture_logs()` — structured test assertions

Current tests assert against formatted log strings or check handler call counts. With structlog:

```python
import structlog.testing

def test_create_event_logged(db):
    with structlog.testing.capture_logs() as logs:
        Author.objects.create(name="Test", bio="Bio")

    audit_logs = [l for l in logs if l.get("event_type") == "CREATE"]
    assert len(audit_logs) == 1
    assert audit_logs[0]["model"] == "Author"
    assert audit_logs[0]["event_type"] == "CREATE"
    assert "instance_repr" in audit_logs[0]
```

No string parsing. No mock handlers. The captured entries are plain dicts.

### 6. Lazy rendering — zero overhead when filtered

`push_log()` today builds the full payload dict unconditionally, even if `AUDIT` level is filtered out by the handler. Structlog defers all dict construction and serialization until the processor chain confirms the level passes — filtered calls are nearly free.

### 7. Per-logger context with `bind()`

Signal handlers can pre-bind model-level context at module load:

```python
# signals.py
log = structlog.get_logger("audit.model")

def push_log(message, model, event_type, instance_id, instance_repr, extra={}):
    bound = log.bind(model=model, event_type=event_type)
    transaction.on_commit(
        lambda: bound.audit(message, instance_id=str(instance_id), ...)
    )
```

The bound logger carries `model` and `event_type` into all subsequent calls — useful when a signal handler emits multiple events in sequence.

---

## Cons of Structlog

### 1. Custom log levels are second-class citizens

`AUDIT=21`, `API=22`, `LOGIN=23` are monkey-patched onto `logging.Logger` in `logger_levels.py`. Structlog's `BoundLogger` has no `.audit()` / `.api()` / `.login()` methods by default.

**Mitigation:** Use `structlog.make_filtering_bound_logger()` with a custom wrapper:

```python
import structlog

class AuditBoundLogger(structlog.stdlib.BoundLogger):
    def audit(self, event, **kw):
        return self._proxy_to_logger("audit", event, **kw)

    def api(self, event, **kw):
        return self._proxy_to_logger("api", event, **kw)

    def login(self, event, **kw):
        return self._proxy_to_logger("login", event, **kw)

structlog.configure(wrapper_class=AuditBoundLogger, ...)
```

This requires registering the custom integer levels on the stdlib side first (same as now via `logger_levels.py`), then bridging through `structlog.stdlib.ProcessorFormatter`.

### 2. Two-layer configuration when using stdlib handlers

If the existing `RotatingFileHandler` / `QueueHandler` chain is kept (to avoid rewriting the async handler infrastructure), both layers must be configured:

```
structlog processor chain  →  stdlib logging.Logger  →  existing handlers
```

The bridge is `structlog.stdlib.ProcessorFormatter` — it wraps the processor chain as a stdlib `Formatter`. This is documented and supported but adds conceptual overhead and a config split between `structlog.configure()` and Django's `LOGGING` dict.

### 3. Significant migration surface

Every `logger.audit(msg, extra=payload)` call across `signals.py`, `middleware.py`, `protocols.py`, and `utils.py` must change. The custom handlers (`AuditLogHandler`, `APILogHandler`) extract fields from `LogRecord.__dict__` populated by `extra=` — that extraction logic must be rewritten or the handlers retired.

### 4. Existing formatters become redundant

`AuditFormatter`, `APIFormatter`, `LoginFormatter`, `AppFormatter` (~200 lines in `formatters.py`) produce the same JSON that structlog's `JSONRenderer` would generate. They become dead code — a clean break, but a breaking change for any downstream project that subclassed them.

### 5. Added dependency

`structlog` is a mandatory new dependency for a library package. Not all consumers will have it. A clean opt-in design (e.g. `pip install django-activity-audit[structlog]`) is needed.

---

## Summary: Pros vs Cons

| | Structlog | Current stdlib |
|--|-----------|----------------|
| Context propagation | `bind_contextvars` — automatic, async-safe | `asgiref.local.Local()` — manual, leak-prone |
| File/line in logs | `CallsiteParameterAdder` — zero call-site code | Not captured in audit formatter |
| Payload construction | Keyword args on log call | Manual dict + `extra={}` |
| Formatter logic | Composable processor list | ~200 lines across 4 classes |
| Test assertions | `capture_logs()` → typed dicts | String matching / mock handlers |
| Performance | Lazy — skipped if level filtered | Dict always constructed |
| Custom log levels | Requires `BoundLogger` wrapper | Monkey-patched, works today |
| Handler compatibility | Needs `ProcessorFormatter` bridge | Works natively |
| Migration cost | High — all call sites change | Zero |
| Dependency | New required dep | None |

---

## Recommended Migration Strategy

### Phase 1 — Hybrid: structlog processors, stdlib handlers (low risk)

Keep all existing handlers and Django `LOGGING` config. Replace the formatters with `structlog.stdlib.ProcessorFormatter`:

```python
# formatters.py replacement
import structlog
from structlog.stdlib import ProcessorFormatter

renderer = ProcessorFormatter(
    processor=structlog.processors.JSONRenderer(),
    foreign_pre_chain=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder([
            structlog.processors.CallsiteParameter.FILENAME,
            structlog.processors.CallsiteParameter.LINENO,
            structlog.processors.CallsiteParameter.FUNC_NAME,
        ]),
    ],
)
```

Wire it into the existing Django `LOGGING` dict:

```python
LOGGING = {
    "formatters": {
        "audit_json": {"()": lambda: renderer},
    },
    "handlers": {
        "audit_file": {
            **get_async_audit_handler(filename="audit_logs/audit.log"),
            "formatter": "audit_json",
        },
        ...
    },
}
```

This unlocks `CallsiteParameterAdder` and cleaner processor composition with zero changes to handlers or call sites.

### Phase 2 — Context migration

Replace `asgiref.local.Local()` thread-locals in `middleware.py:8–82` with `structlog.contextvars`:

```python
# middleware.py

import structlog.contextvars as ctx

class AuditLoggingMiddleware:
    def __call__(self, request):
        request_id = str(uuid.uuid4())
        ctx.clear_contextvars()
        ctx.bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
            user_id, user_info = _extract_user(request)
            ctx.bind_contextvars(user_id=user_id, user_info=user_info)
            ...
        finally:
            ctx.clear_contextvars()
        return response
```

Remove `get_request_id()`, `get_user_details()`, `set_current_request()`, `clear_request()` from `push_log()` — the processor chain picks them up automatically via `merge_contextvars`.

This also fixes the thread-local leak described in `improvements.md` (issue #7) as a side effect.

### Phase 3 — Call-site cleanup

Refactor `push_log()` to use structlog native calls, retire `extra={}` pattern, update tests to use `capture_logs()`.

---

## File/Line Info in Signal Handlers — Implementation Detail

Add `CallsiteParameterAdder` to the processor chain (Phase 1). The processor requires a `_record` key to be present, which `ProcessorFormatter` injects automatically when bridging from stdlib.

Every log entry emitted from `push_log()` (signals.py:146) will include:

```json
{
    "filename": "signals.py",
    "lineno": 146,
    "func_name": "push_log"
}
```

To also capture the Django model file that owns the `.save()` call, add a lightweight stack inspector:

```python
import inspect

def _get_save_callsite() -> dict:
    for frame_info in inspect.stack():
        if frame_info.filename.endswith("signals.py"):
            continue
        if frame_info.function in ("save", "bulk_create", "bulk_update"):
            continue
        return {
            "trigger_file": frame_info.filename,
            "trigger_line": frame_info.lineno,
            "trigger_func": frame_info.function,
        }
    return {}
```

Pass the result as `extra` in `push_log()`. Use sparingly — `inspect.stack()` is expensive and should be guarded behind a debug flag or sampled.

---

## Output Log Shape (Post-Migration)

```json
{
    "timestamp": "2026-06-16T10:22:45.123Z",
    "level": "audit",
    "logger": "audit.model",
    "event": "CREATE event for Author (id: abc123)",
    "filename": "signals.py",
    "lineno": 146,
    "func_name": "push_log",
    "request_id": "f3c9a1b2-0001-4abc-beef-deadbeef0001",
    "user_id": "cae8ffb4-ba52-409c-9a6f-e10362bfaf97",
    "user_info": {
        "email": "user@example.com",
        "first_name": "Ada",
        "last_name": "Lovelace"
    },
    "model": "Author",
    "event_type": "CREATE",
    "instance_id": "9f1b2c3d-...",
    "instance_repr": { "name": "Ada Lovelace", "bio": "Mathematician" },
    "extra": {}
}
```

All fields from the current `AuditFormatter` output are preserved. New fields: `filename`, `lineno`, `func_name`. The `request_id` / `user_id` / `user_info` fields are no longer passed manually — they come from the processor chain.

---

## Dependency

```toml
# pyproject.toml
[project.optional-dependencies]
structlog = ["structlog>=24.0"]
```

```bash
pip install django-activity-audit[structlog]
```

The core package remains dependency-free. Structlog features activate only when the optional extra is installed and `structlog.configure()` is called by the host application.
