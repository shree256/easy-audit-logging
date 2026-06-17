import contextlib
import json
import re
import time
import uuid

from asgiref.local import Local
from asgiref.sync import (
    iscoroutinefunction,
    markcoroutinefunction,
    sync_to_async,
)
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

import structlog.contextvars as ctx

from .constants import REQUEST_TYPES
from .settings import REGISTERED_URLS, SERVICE_NAME, UNREGISTERED_URLS
from .structlog_support import get_logger

_log = get_logger("audit.request")

_thread_locals = Local()


class MockRequest:
    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)


def get_current_request():
    return getattr(_thread_locals, "request", None)


def set_current_request(request):
    _thread_locals.request = request


def get_request_id():
    return getattr(_thread_locals, "request_id", None)


def set_request_id(request_id):
    _thread_locals.request_id = request_id


def get_current_user():
    request = get_current_request()
    if request:
        return getattr(request, "user", None)
    return None


def set_current_user(user):
    try:
        _thread_locals.request.user = user
    except AttributeError:
        request = MockRequest(user=user)
        _thread_locals.request = request


def get_user_details():
    user = get_current_user()
    if user is None:
        return "", {}

    id = str(user.id) if hasattr(user, "id") else ""
    info = {
        "title": user.title if hasattr(user, "title") else "",
        "email": user.email if hasattr(user, "email") else "",
        "first_name": user.first_name if hasattr(user, "first_name") else "",
        "middle_name": user.middle_name if hasattr(user, "middle_name") else "",
        "last_name": user.last_name if hasattr(user, "last_name") else "",
        "sex": user.sex if hasattr(user, "sex") else "",
        "date_of_birth": user.date_of_birth if hasattr(user, "date_of_birth") else "",
    }
    return id, info


def clear_request():
    with contextlib.suppress(AttributeError):
        del _thread_locals.request
    with contextlib.suppress(AttributeError):
        del _thread_locals.request_id


def should_log_url(url):
    # check if current url is blacklisted
    for unregistered_url in UNREGISTERED_URLS:
        pattern = re.compile(unregistered_url)
        if pattern.match(url):
            return False

    # only audit URLs listed in REGISTERED_URLS (if it's set)
    if len(REGISTERED_URLS) > 0:
        for registered_url in REGISTERED_URLS:
            pattern = re.compile(registered_url)
            if pattern.match(url):
                return True
        return False

    # all good
    return True


class AuditLoggingMiddleware(MiddlewareMixin):
    """
    log structure:
    {
        "timestamp": "2021-01-01 12:00:00.000",
        "level": "INFO",
        "name": "audit.request",
        "service_name": "default",
        "protocol": "http",
        "request_repr": {
            "endpoint": "https://example.com/api/v1/users",
            "method": "GET",
            "headers": {"Content-Type": "application/json"},
            "body": {"name": "John Doe", "email": "john.doe@example.com"},
        },
        "response_repr": {
            "status_code": 200,
            "body": {"name": "John Doe", "email": "john.doe@example.com"},
        },
        "error_message": "",
        "execution_time": 0,
    }
    """

    def __init__(self, get_response):
        self.get_response = get_response

        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self):
            return self.__acall__(request)
        set_current_request(request)
        request_id = str(uuid.uuid4())
        set_request_id(request_id)
        ctx.clear_contextvars()
        ctx.bind_contextvars(request_id=request_id)

        if not should_log_url(request.path):
            return self.get_response(request)

        log_data = {
            "service_name": SERVICE_NAME,
            "request_type": REQUEST_TYPES[0],
            "protocol": None,
            "request_repr": {},
            "response_repr": {},
            "error_message": None,
            "execution_time": 0,
        }
        start_time = time.time()

        # Log request
        request_data = {
            "method": request.method,
            "path": request.path,
            "query_params": dict(request.GET.items()),
            "headers": dict(request.headers),
        }

        if request.content_type == "application/json":
            try:
                body = json.loads(request.body)
                request_data["body"] = body
            except json.JSONDecodeError:
                request_data["body"] = "Invalid JSON"

        # Get response
        response = self.get_response(request)
        end_time = time.time()

        # Capture user details AFTER authentication has happened
        user_id, user_info = get_user_details()
        ctx.bind_contextvars(user_id=user_id, user_info=user_info)

        # TODO: Find way to add status code to response_data

        # Log response
        response_data = {
            "headers": dict(response.headers),
        }

        if isinstance(response, HttpResponse):
            try:
                content = response.content.decode("utf-8")
                if content:
                    try:
                        response_data["body"] = json.loads(content)
                    except json.JSONDecodeError:
                        response_data["body"] = content
            except UnicodeDecodeError:
                response_data["body"] = "Binary content"

        log_data["execution_time"] = end_time - start_time
        log_data["protocol"] = "https" if request.is_secure() else "http"
        log_data["request_repr"] = request_data
        log_data["response_repr"] = response_data

        bound = _log.bind(**log_data)
        bound.api("Audit Internal Request")

        clear_request()
        ctx.clear_contextvars()

        return response

    async def __acall__(self, request):
        set_current_request(request)
        request_id = str(uuid.uuid4())
        set_request_id(request_id)
        ctx.clear_contextvars()
        ctx.bind_contextvars(request_id=request_id)

        if not should_log_url(request.path):
            return await self.get_response(request)

        log_data = {
            "service_name": SERVICE_NAME,
            "request_type": REQUEST_TYPES[0],
            "protocol": None,
            "request_repr": {},
            "response_repr": {},
            "error_message": None,
            "execution_time": 0,
        }
        start_time = time.time()

        # Log request
        request_data = {
            "method": request.method,
            "path": request.path,
            "query_params": dict(request.GET.items()),
            "headers": dict(request.headers),
        }

        if request.content_type == "application/json":
            try:
                body = json.loads(request.body)
                request_data["body"] = body
            except json.JSONDecodeError:
                request_data["body"] = "Invalid JSON"

        # Get response
        response = await self.get_response(request)
        end_time = time.time()

        # Capture user details AFTER authentication has happened
        user_id, user_info = await sync_to_async(
            get_user_details, thread_sensitive=True
        )()
        ctx.bind_contextvars(user_id=user_id, user_info=user_info)

        # TODO: Find way to add status code to response_data

        # Log response
        response_data = {
            "headers": dict(response.headers),
        }

        if isinstance(response, HttpResponse):
            try:
                content = response.content.decode("utf-8")
                if content:
                    try:
                        response_data["body"] = json.loads(content)
                    except json.JSONDecodeError:
                        response_data["body"] = content
            except UnicodeDecodeError:
                response_data["body"] = "Binary content"

        log_data["execution_time"] = end_time - start_time
        log_data["protocol"] = "https" if request.is_secure() else "http"
        log_data["request_repr"] = request_data
        log_data["response_repr"] = response_data

        bound = _log.bind(**log_data)
        bound.api("Audit Internal Request")

        clear_request()
        ctx.clear_contextvars()

        return response
