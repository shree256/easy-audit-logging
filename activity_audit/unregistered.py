from django.apps import apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db.migrations import Migration
from django.db.migrations.recorder import MigrationRecorder

UNREGISTERED_CLASSES = [
    Migration,
    Session,
    Permission,
    ContentType,
    MigrationRecorder.Migration,
]

if apps.is_installed("silk"):
    from silk.models import (
        BaseProfile,
        Profile,
        Request,
        Response,
        SQLQuery,
        SQLQueryManager,
    )

    UNREGISTERED_CLASSES.extend(
        [Request, Response, SQLQueryManager, SQLQuery, BaseProfile, Profile]
    )

if apps.is_installed("django.contrib.admin"):
    from django.contrib.admin.models import LogEntry

    UNREGISTERED_CLASSES.extend([LogEntry])
