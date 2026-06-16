# HIPAA Audit Gap Analysis

Architecture: Django → stdout → Docker logs → Vector → ClickHouse (self-hosted, in-VPC) → Grafana

---

## Critical — Must Fix

### 1. Sentry Integration Shipping PHI Outside VPC — §164.314

`settings.py` maps AUDIT/API log levels to Sentry. If Sentry is active in production, full request/response payloads and model reprs containing patient data are leaving the VPC to a third-party with no BAA coverage.

**Fix:** Disable Sentry for `audit.*` loggers in production, or strip PHI fields before they reach the Sentry handler.

---

### 2. Response Status Code Missing from API Logs — §164.312(b)

`middleware.py:181` has a `# TODO` for status code. HIPAA requires distinguishing authorized access (200) from denied access (403/401) to identify unauthorized access attempts.

**Fix:** `response.status_code` is directly available on the Django `HttpResponse` object — add it to `response_repr`.

---

### 3. Log Integrity / Tamper-Evidence — §164.312(c)(1)

Audit logs must be protected from unauthorized alteration.

**Fix:**
- ClickHouse ingest user must have `INSERT` only — no `ALTER`/`DELETE`/`TRUNCATE`
- Docker daemon socket access restricted to the Vector service account only
- Separate admin-only ClickHouse role for schema changes

---

### 4. Log Retention Not Enforced — §164.530(j)

HIPAA requires audit log retention for 6 years (2190 days). `backupCount` on local file handlers is irrelevant with Docker log streaming, but ClickHouse TTL and Vector buffering are not configured.

**Fix:**
- Set ClickHouse TTL policy to 6+ years explicitly on audit tables
- Set Vector sink buffer to `type = "disk"` — the default in-memory buffer silently drops events when ClickHouse is unavailable

---

### 5. No Audit of Audit-Log Access — §164.312(b)

Grafana queries against ClickHouse constitute access to ePHI audit trails. Those accesses are not themselves logged or reviewed.

**Fix:** Enable ClickHouse query logging and retain Grafana access logs. Review them periodically as part of your access management program.

---

### 6. Failed Login Attempts Not Captured — §164.312(d)

`push_usage_log` only runs when explicitly called by the application. Django's `user_login_failed` signal is not wired, so brute-force attacks against patient portals leave no trace in the audit trail.

**Fix:** Wire `user_login_failed` (and optionally `user_logged_out`) signals in `apps.py:ready()`.

---

### 7. Admin Interface Excluded from Logging — §164.308(a)(1)

`UNREGISTERED_URLS` defaults include `r"^/admin/"` and `LogEntry` is in `UNREGISTERED_CLASSES`. Superuser admin actions carry the highest insider-threat risk and must be in the audit trail.

**Fix:** Remove `^/admin/` from the default exclusion list and remove `LogEntry` from `UNREGISTERED_CLASSES`, or capture admin actions via a dedicated signal.

---

### 8. Acting User's `sex` and `date_of_birth` in Every Log Entry

`get_user_details()` in `middleware.py:66–73` captures `sex` and `date_of_birth` of the user performing the action — not the patient. This unnecessarily expands the ePHI footprint across every single log entry and is directly at risk from point 1 (Sentry).

**Fix:** Strip `sex` and `date_of_birth` from `get_user_details()`. Audit identity only needs `user_id`, `email`, and `role`.

---

## Medium Priority

### 9. `pre_save` + `on_commit` Double-Logging

`handle_pre_save` in `signals.py` calls `push_log`, which wraps emission in `transaction.on_commit`. The pre-commit state semantic is lost since the log is deferred to after commit anyway. Every save emits two entries: PRE_CREATE + CREATE (or PRE_UPDATE + UPDATE), doubling ClickHouse storage for every write.

**Fix:** Remove the `pre_save` signals unless there is a documented use case for capturing pre-commit field state.

---

### 10. Bulk Operations Log Only the First Object's Repr

`signals.py:84–91` — `bulk_create_with_signals` logs `instance_repr` for `created_objs[0]` only, with a `total_count` field. If 500 patient records are bulk-created, the audit shows only one record's state.

**Fix:** Either log all object IDs in the `extra` field, or formally document that bulk operations are audited at the batch level only (not per-record).

---

### 11. SFTP Client Uses `AutoAddPolicy` — `protocols.py:131`

`paramiko.AutoAddPolicy()` accepts any host key silently, making PHI file transfers vulnerable to man-in-the-middle attacks.

**Fix:** Use `paramiko.RejectPolicy()` with explicitly pinned trusted host keys.

---

### 12. Celery / Async Context Loses User Identity Silently

Background Celery tasks that trigger model saves have no request context. `get_user_details()` returns `"", {}` silently — audit entries for async PHI processing have no actor identity, making them useless for accountability.

**Fix:** Explicitly inject the acting user into task context and call `set_current_user()` at the start of tasks that perform auditable operations.

---

## Architecture-Specific

### 13. Silent Log Loss on Container Crash

`transaction.on_commit` in `signals.py:150` defers the audit log write until after the database commits. If the container crashes in the window between DB commit and stdout emission, the database change is committed but the audit event is never emitted — silently lost with no fallback.

**Fix:** Document this as a known gap in the threat model, or add a DB-side audit table as a secondary sink for critical events.

---

### 14. Vector Sink Buffer Not Configured for Durability

The default Vector buffer is in-memory. If ClickHouse is temporarily unavailable, events in the buffer are dropped with no recovery.

**Fix:** Set `type = "disk"` with a defined `max_size` in the Vector ClickHouse sink buffer configuration.

```toml
[sinks.clickhouse.buffer]
type = "disk"
max_size = 268435488  # 256MB
when_full = "block"
```
