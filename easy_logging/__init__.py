default_app_config = "easy_logging.apps.EasyLoggingConfig"

from easy_logging.utils import (
    get_console_formatter,
    get_json_file_formatter,
    get_json_file_handler,
    get_api_formatter,
    get_api_handler,
    get_audit_formatter,
    get_audit_handler,
    get_login_formatter,
    get_login_handler,
)

__all__ = [
    "get_console_formatter",
    "get_json_file_formatter",
    "get_json_file_handler",
    "get_api_formatter",
    "get_api_handler",
    "get_audit_formatter",
    "get_audit_handler",
    "get_login_formatter",
    "get_login_handler",
]
