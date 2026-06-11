# activity_audit — Code Review

> Reviewed: 2026-06-08  
> Reviewer: Claude Code  
> Scope: Full app audit following bug fixes for `AppRegistryNotReady` and `request_id` thread-local propagation

---

## Recent Fixes (Verified Correct)

| Fix | File | Status |
|-----|------|--------|
| `AppRegistryNotReady` — model imports deferred to `unregistered.py`, loaded in `apps.ready()` | `unregistered.py`, `apps.py`, `settings.py` | ✅ Correct |
| `request_id` not written to `app.log` — captured via `prepare()` in handler (producer thread) before record is queued to background `QueueListener` thread | `handlers.py` | ✅ Correct |
| `watchfiles` reload loop — log files moved to `/logs/` (outside `/app/`), `watchfiles` logger silenced at WARNING | `config/settings/local.py`, `local.yml` | ✅ Correct |

---

## Critical Issues (Must Fix)

### 1. Cross-request PHI data leak — shared `self.log_data` in middleware
**File:** `middleware.py:127–140`

`self.log_data` is constructed once in `__init__` and stored on the middleware instance. Middleware instances are shared across all requests. Under concurrent ASGI (multiple coroutines on one instance), request A's `user_id`, `request_repr`, `response_repr` overwrite request B's in the same dict — PHI from one patient's session can be written into another patient's audit record.

**Fix:** Build `log_data` as a local dict inside `__call__` and `__acall__`, not on `self`.

```python
# Before (in __init__)
self.log_data = {"service_name": SERVICE_NAME, ...}

# After (top of __call__ and __acall__)
log_data = {"service_name": SERVICE_NAME, ...}
```

---

### 2. `QuerySet.bulk_create/bulk_update` monkey-patched N times — wrappers nest
**File:** `signals.py:129–130, 244–247`

Inside `patch_model_event`, the patching logic does:
```python
original_bulk_create = models.QuerySet.bulk_create   # captured per call
...
models.QuerySet.bulk_create = bulk_create_with_signals  # assigned globally
```
This runs once per audited model. The second model captures the already-patched
method as its "original", the third wraps the double-patched version, and so on.
After N models are patched, every `bulk_create` call traverses N nested wrappers.

**Fix:** Extract the `QuerySet` patches into a separate function called exactly once from `setup_model_signals()`, before the per-model loop.

---

### 3. `get_calling_model()` frame-walking is broken — bulk auditing is non-functional
**File:** `signals.py:57–79, 193–196, 225–228`

```python
if calling_model == model_class.__name__:
```
`calling_model` is `module_name.split(".")[-1]` (e.g. `"views"`, `"tasks"`).
`model_class.__name__` is a class name (e.g. `"Patient"`, `"Appointment"`).
These will almost never match, so bulk audit logs are silently never written for virtually all models.

**Fix:** Rethink bulk auditing using Django signals (`post_bulk_create` is unavailable natively, but a custom `QuerySet` mixin on a project-level base queryset is more reliable than frame introspection).

---

### 4. `request.body` access can crash real requests
**File:** `middleware.py:165–170, 229–234`

Only `json.JSONDecodeError` is caught. The following are unhandled and will 500 the request:
- `RawPostDataException` — body stream already consumed by DRF/multipart parsers
- `RequestDataTooBig` — body exceeds `DATA_UPLOAD_MAX_MEMORY_SIZE`
- `UnicodeDecodeError` — binary upload body

Audit middleware must never break actual requests.

**Fix:**
```python
try:
    body = json.loads(request.body)
    request_data["body"] = body
except Exception:
    pass  # never let audit logging crash the request
```

---

## Warnings (Should Fix)

### 5. PHI/SSN written into `audit.log` via `instance_to_dict`
**File:** `signals.py:117–118`

`model_to_dict(instance, fields=[f.name for f in instance._meta.fields])` dumps all
concrete fields including encrypted `social_security_number` and other PHI directly
into the audit log file. This directly violates HIPAA rules documented in `CLAUDE.md`:
> "Never log PHI to console" / "SSN handling — only access via `get_ssn` endpoint"

**Fix:** Add a per-model field deny-list or use a model-level `AUDIT_EXCLUDE_FIELDS`
attribute. At minimum, exclude all `EncryptedField` instances.

---

### 6. Regex patterns recompiled on every request in `should_log_url`
**File:** `middleware.py:84–100`

```python
for unregistered_url in UNREGISTERED_URLS:
    pattern = re.compile(unregistered_url)   # compiled on every request
```
This is in the hot path for every HTTP request.

**Fix:** Compile once at module load:
```python
_UNREGISTERED_PATTERNS = [re.compile(p) for p in UNREGISTERED_URLS]
_REGISTERED_PATTERNS   = [re.compile(p) for p in REGISTERED_URLS]
```

---

### 7. `clear_request()` not called on early return — thread-local leaks
**File:** `middleware.py:148–153`

```python
set_current_request(request)
set_request_id(request_id)

if not should_log_url(request.path):
    return self.get_response(request)   # clear_request() never called
```
The thread-local `request` and `request_id` persist on the worker thread and
are seen by the next request handled by that thread.

**Fix:** Use `try/finally`:
```python
set_current_request(request)
set_request_id(request_id)
try:
    if not should_log_url(request.path):
        return self.get_response(request)
    ...
finally:
    clear_request()
```

---

### 8. Bulk wrappers never call `should_audit` — unregistered models audited on bulk paths
**File:** `signals.py:179–242`

`bulk_create_with_signals` and `bulk_update_with_signals` have no `should_audit` guard,
so `Session`, `Permission`, `Migration` etc. are audited on bulk paths but excluded on
single-save paths. Inconsistent and wasteful.

---

### 9. `SFTPClient.upload` — unconditional assignment clobbers success and real errors
**File:** `protocols.py:209–237`

```python
if not error:
    try:
        ...upload...
    except Exception:
        self.log_payload["error_message"] = str(e)   # real error

# This runs unconditionally — overwrites both the success case and the real exception:
self.log_payload["error_message"] = f"Path validation failed. Error: {str(error)}"
```
On a fully successful upload, `error_message` is set to `"Path validation failed. Error: None"`.

**Fix:** Wrap the final assignment in an `else` block.

---

### 10. `HTTPClient.request` returns `None` on exception and calls `.json()` unconditionally
**File:** `protocols.py:97–118`

```python
except Exception:
    ...
    return response   # response is None here
```
Callers expecting a `requests.Response` will raise `AttributeError`. On the success path,
`response.json()` is called regardless of `Content-Type`, which will raise for non-JSON
responses and discard the real response object.

---

### 11. `push_usage_log` imports `get_user_details` through `signals` — unwanted side effect
**File:** `utils.py:139`

```python
from .signals import get_user_details
```
Importing `signals` triggers `setup_model_signals()` at the bottom of that module as a
side effect. Import directly from the canonical source:
```python
from .middleware import get_user_details
```

---

### 12. Sentry filter attached at settings-load time — before Sentry is initialised
**File:** `settings.py:24–27`

```python
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if handler.__class__.__name__.startswith("Sentry"):
        handler.addFilter(AuditToSentryFilter())
```
At settings-load time Sentry SDK has not yet added its handler, so this loop finds nothing
and the filter is never attached. Move to `apps.ready()`.

---

## Suggestions (Consider)

### 13. `default_app_config` is dead
**File:** `__init__.py:1`

Deprecated in Django 3.2, removed in Django 4.1. It is a no-op. Remove it.

---

### 14. Timestamp formatting duplicated across all 4 formatters
**File:** `formatters.py:42–44` (and 3 other formatters)

```python
datetime.datetime.fromtimestamp(record.created).strftime(self.timestamp_format)[:-3]
```
This block is copy-pasted in `JsonFormatter`, `APIFormatter`, `AuditFormatter`, and
`LoginFormatter`. Also uses server local time with no timezone. Extract a shared:
```python
class BaseAuditFormatter(logging.Formatter):
    def _timestamp(self, record) -> str:
        return datetime.datetime.fromtimestamp(
            record.created, tz=datetime.timezone.utc
        ).strftime(self.timestamp_format)[:-3]
```

---

### 15. `apps.ready()` no-op attribute accesses are misleading
**File:** `apps.py:14–16`

```python
logger_levels.AUDIT
logger_levels.API
logger_levels.LOGIN
```
These are bare attribute reads that do nothing — the level registration already
happened when `logger_levels` was imported. The import itself is the side effect.
Remove the three lines or replace with a comment.

---

### 16. `AuditToSentryFilter` mutates `record.levelname` — corrupts file logs
**File:** `settings.py:8–20`

Overwriting `record.levelname = "INFO"` means formatters downstream will log `"INFO"`
instead of `"AUDIT"` / `"API"` in file logs too (filters run before formatting).
If Sentry integration is needed, use a `before_send` hook in Sentry config instead.

---

### 17. Minor style issues

| Location | Issue |
|----------|-------|
| `middleware.py:64` | `id = str(user.id)` shadows the builtin `id` |
| `protocols.py:193` | `f"Connection not established"` — f-string with no placeholders |
| `signals.py:88` | `instance_repr: str` type hint but callers pass `dict` |
| `middleware.py:21–25` | `MockRequest.__init__` passes `*args, **kwargs` to `object.__init__` which rejects them |
| `formatters.py`, `signals.py` | Several lines exceed 80-char limit — run `make format` |

---

## Priority Order

| Priority | Issue | File |
|----------|-------|------|
| 🔴 P0 | Cross-request PHI data leak (`self.log_data`) | `middleware.py` |
| 🔴 P0 | PHI/SSN in `audit.log` via `instance_to_dict` | `signals.py` |
| 🔴 P0 | `request.body` access can crash requests | `middleware.py` |
| 🟠 P1 | `QuerySet` patch nested N times | `signals.py` |
| 🟠 P1 | Bulk auditing effectively broken (`get_calling_model`) | `signals.py` |
| 🟠 P1 | `clear_request()` missing on early return | `middleware.py` |
| 🟡 P2 | Regex recompiled on every request | `middleware.py` |
| 🟡 P2 | Bulk wrappers skip `should_audit` | `signals.py` |
| 🟡 P2 | `SFTPClient.upload` error message clobbered | `protocols.py` |
| 🟡 P2 | `HTTPClient.request` returns `None` silently | `protocols.py` |
| 🟡 P2 | `push_usage_log` imports via `signals` | `utils.py` |
| 🟡 P2 | Sentry filter never attaches | `settings.py` |
| 🔵 P3 | Timestamp duplication, `default_app_config`, style nits | various |
