import enum


class LogType(str, enum.Enum):
    APP = "app"
    API = "api"
    AUDIT = "audit"
    LOGIN = "login"


CONSOLE_FORMAT = (
    "%(levelname)s %(asctime)s %(pathname)s %(module)s %(funcName)s %(message)s"
)

REQUEST_TYPES = [
    "internal",
    "external",
]

