# Easy Audit Logging

A Django package that extends the default logging mechanism to track CRUD operations and container logs.

## Features

- Automatic logging of CRUD operations (Create, Read, Update, Delete)
- Tracks both HTTP requests and model changes
- Custom AUDIT log level (15) between DEBUG and WARNING
- Structured JSON logs for audit trails
- Human-readable container logs
- Configurable log rotation
- Separate log files for audit and container logs
- Console and file output options

## Installation

1. Install the package:
```bash
pip install easy-audit-logging
```

2. Add 'easy_logging' to your INSTALLED_APPS in settings.py:
```python
INSTALLED_APPS = [
    ...
    'easy_logging',
]
```

3. Add the middleware to your MIDDLEWARE in settings.py:
```python
MIDDLEWARE = [
    ...
    'easy_logging.middleware.AuditUserMiddleware',
]
```

4. Configure logging in settings.py:
```python
Pass
```

## Log Types

### Audit Logs
- JSON formatted
- Contains CRUD operation details
- Includes user information and model changes
- Stored in audit.log by default

Example audit log entry:
```json
{
  "timestamp": "2024-04-27T08:25:30.123456",
  "level": "AUDIT",
  "logger": "audit_logger",
  "message": "Model created: User",
  "event_type": "CREATE",
  "model": "auth.User",
  "pk": 123,
  "fields": {
    "username": "john_doe",
    "email": "john@example.com"
  },
  "user": "admin",
  "source": "audit"
}
```

### Container Logs
- Human-readable format
- Contains Django application logs
- Includes request/response information
- Stored in container.log by default

Example container log entry:
```
[2024-04-27 08:25:30] INFO [django.server] "GET /api/users/ HTTP/1.1" 200 1234
[2024-04-27 08:25:31] WARNING [django.request] Not Found: /api/nonexistent/
```

## Advanced Configuration

### Custom Log Rotation
```python
LOGGING = get_logging_config(
    log_rotation={
        "maxBytes": 10485760,  # 10MB
        "backupCount": 5,
        "encoding": "utf-8",
    }
)
```

### Disable File Logging
```python
LOGGING = get_logging_config(
    audit_log_file=None,      # Disable audit log file
    container_log_file=None,  # Disable container log file
    console_output=True,      # Only console output
)
```

### Different Log Levels
```python
LOGGING = get_logging_config(
    audit_log_level=15,           # AUDIT level for audit logs
    container_log_level=logging.DEBUG,  # DEBUG level for container logs
)
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 📆 Features

- **Custom AUDIT log level (15)** between DEBUG and WARNING.
- **Structured JSON logs** for better parsing and analytics.
- **Middleware** to capture the authenticated user on each request.
- **Signals** to track model `CREATE`, `UPDATE`, and `DELETE` events.
- **Ready for modern log pipelines** — no database storage needed.

---

## 🛠 Installation

### 1. Install via pip

```bash
pip install easy-audit-logging
```

or if using directly from GitHub:

```bash
pip install git+https://github.com/yourusername/easy-audit-logging.git
```

### 2. Add to `INSTALLED_APPS` in `settings.py`

```python
INSTALLED_APPS += [
    "audit_logging",
]
```

### 3. Add the middleware

```python
MIDDLEWARE += [
    "audit_logging.middleware.AuditUserMiddleware",
]
```

### 4. Configure the logger in `settings.py`

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "audit_json": {
            "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": %(message)s}',
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "audit_file": {
            "level": "AUDIT",
            "class": "logging.FileHandler",
            "filename": "logs/audit.log",
            "formatter": "audit_json",
        },
    },
    "loggers": {
        "audit_logger": {
            "handlers": ["audit_file"],
            "level": "AUDIT",
            "propagate": False,
        },
    },
}
```

Make sure the `logs/` directory exists.

---

## 📃 How It Works

| Event | Captured via | Output |
|:------|:-------------|:-------|
| Model Create/Update/Delete | Django model signals | Structured JSON in `audit.log` |
| Request user identity | Django middleware | Injected into each audit log |

---

## 🔥 Example Audit Log

```json
{
  "timestamp": "2025-04-27T08:25:30",
  "level": "AUDIT",
  "name": "audit_logger",
  "message": {
    "timestamp": "2025-04-27T08:25:30",
    "event_type": "UPDATE",
    "model": "User",
    "pk": 123,
    "fields": {
      "email": "new@example.com",
      "username": "newuser"
    },
    "user": "admin_user",
    "source": "audit"
  }
}
```

---

## 📢 Notes

- Compatible with **Django 3.2+** and **Python 3.7+**.
- Designed for easy integration with observability stacks using **Vector**, **ClickHouse**, and **Grafana**.

---

## 🔗 Related Tools

- [Vector.dev](https://vector.dev/)
- [ClickHouse](https://clickhouse.com/)
- [Grafana](https://grafana.com/)

---

## 💜 License

This project is licensed under the MIT License.

---
