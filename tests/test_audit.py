"""
Audit test suite covering:
  1. Incoming request-response is logged
  2. Model create / update / delete is logged
  3. M2M field changes are logged
  4. Console (stream) output from each formatter includes all declared fields
  5. The same request_id is generated once and flows through app, api, and audit logs
"""

import io
import json
import logging

import pytest

from rest_framework import status
from rest_framework.test import APIClient

from tests.publications.models import Author, Book

# ---------------------------------------------------------------------------
# 1. Request / response logging
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRequestResponseLogging:
    """Incoming HTTP requests and their responses are captured in the audit log."""

    def test_get_request_is_logged(self, request_log_capture):
        client = APIClient()
        response = client.get("/api/authors/")

        assert response.status_code == status.HTTP_200_OK
        assert len(request_log_capture.by_level("API")) >= 1

    def test_post_request_is_logged(self, request_log_capture):
        client = APIClient()
        response = client.post(
            "/api/authors/",
            {"name": "Posted Author", "experience": "Some"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert len(request_log_capture.by_level("API")) >= 1

    def test_request_log_has_required_fields(self, request_log_capture):
        client = APIClient()
        client.get("/api/authors/")

        records = request_log_capture.by_level("API")
        assert records, "Expected at least one API log record"
        record = records[0]

        for field in (
            "service_name",
            "request_type",
            "protocol",
            "request_id",
            "user_id",
            "user_info",
            "request_repr",
            "response_repr",
            "error_message",
            "execution_time",
        ):
            assert hasattr(record, field), f"API log record missing field: {field}"

        assert "method" in record.request_repr
        assert "path" in record.request_repr
        assert "query_params" in record.request_repr
        assert "headers" in record.request_repr
        assert "headers" in record.response_repr

    def test_execution_time_is_non_negative(self, request_log_capture):
        client = APIClient()
        client.get("/api/authors/")

        records = request_log_capture.by_level("API")
        assert records
        assert records[0].execution_time >= 0

    def test_request_id_is_populated(self, request_log_capture):
        client = APIClient()
        client.get("/api/authors/")

        records = request_log_capture.by_level("API")
        assert records
        assert records[0].request_id, "request_id should be a non-empty UUID string"


# ---------------------------------------------------------------------------
# 2. Model CRUD logging
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestModelCRUDLogging:
    """CREATE, UPDATE, and DELETE operations each produce an audit log entry."""

    def test_create_is_logged(self, model_log_capture):
        Author.objects.create(name="New Author", experience="Ten years")

        events = model_log_capture.by_event_type("CREATE")
        assert events, "Expected a CREATE audit record"
        assert events[0].model == "Author"
        assert events[0].instance_id

    def test_create_log_has_required_fields(self, model_log_capture):
        Author.objects.create(name="Field Author", experience="Some")

        events = model_log_capture.by_event_type("CREATE")
        assert events
        record = events[0]

        for field in (
            "model",
            "event_type",
            "instance_id",
            "instance_repr",
            "user_id",
            "user_info",
            "extra",
            "request_id",
        ):
            assert hasattr(record, field), f"Model log record missing field: {field}"

    def test_update_is_logged(self, model_log_capture):
        author = Author.objects.create(name="Author", experience="Original")
        model_log_capture.clear()

        author.experience = "Updated experience"
        author.save()

        events = model_log_capture.by_event_type("UPDATE")
        assert events, "Expected an UPDATE audit record"
        assert events[0].model == "Author"

    def test_deletion_is_logged(self, model_log_capture):
        author = Author.objects.create(name="Doomed Author", experience="Temporary")
        author_id = str(author.pk)
        model_log_capture.clear()

        author.delete()

        events = model_log_capture.by_event_type("DELETE")
        assert events, "Expected a DELETE audit record"
        record = events[0]
        assert record.model == "Author"
        assert record.instance_id == author_id

    def test_delete_also_emits_pre_delete(self, model_log_capture):
        author = Author.objects.create(name="Pre-Delete Author", experience="Temp")
        model_log_capture.clear()

        author.delete()

        assert model_log_capture.by_event_type(
            "PRE_DELETE"
        ), "Expected a PRE_DELETE audit record"

    def test_instance_repr_contains_saved_values(self, model_log_capture):
        Author.objects.create(name="Repr Author", experience="Check repr")

        events = model_log_capture.by_event_type("CREATE")
        author_events = [e for e in events if e.model == "Author"]
        assert author_events
        repr_data = author_events[0].instance_repr
        assert repr_data.get("name") == "Repr Author"
        assert repr_data.get("experience") == "Check repr"


# ---------------------------------------------------------------------------
# 3. M2M field logging
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestM2MLogging:
    """Adding and removing M2M relationships produce M2M audit log entries."""

    def _create_book_with_authors(self):
        primary = Author.objects.create(name="Primary", experience="Lead")
        co = Author.objects.create(name="Co-author", experience="Support")
        book = Book.objects.create(title="Collaborative Work", author=primary)
        return book, co

    def test_m2m_add_is_logged(self, model_log_capture):
        book, co = self._create_book_with_authors()
        model_log_capture.clear()

        book.co_authors.add(co)

        events = model_log_capture.by_event_type("M2M")
        assert events, "Expected an M2M audit record after add"
        record = events[0]
        assert record.model == "Book"
        assert str(co.pk) in record.extra.get("related_ids", [])

    def test_m2m_remove_is_logged(self, model_log_capture):
        book, co = self._create_book_with_authors()
        book.co_authors.add(co)
        model_log_capture.clear()

        book.co_authors.remove(co)

        events = model_log_capture.by_event_type("M2M")
        assert events, "Expected an M2M audit record after remove"
        assert events[0].model == "Book"

    def test_m2m_log_contains_instance_repr(self, model_log_capture):
        book, co = self._create_book_with_authors()
        model_log_capture.clear()

        book.co_authors.add(co)

        events = model_log_capture.by_event_type("M2M")
        assert events
        assert events[0].instance_repr, "M2M log should carry the instance repr"


# ---------------------------------------------------------------------------
# 4. Formatter / console output
# ---------------------------------------------------------------------------


def _make_record(name, level=logging.INFO, **attrs):
    """Build a LogRecord pre-populated with the given extra attributes."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="/app/module.py",
        lineno=42,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    for key, value in attrs.items():
        setattr(record, key, value)
    return record


def _emit_to_stream(formatter, record):
    """Emit a record through a StreamHandler and return the parsed JSON output."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.emit(record)
    return json.loads(stream.getvalue().strip())


class TestFormatterConsoleOutput:
    """Each formatter produces JSON that contains every field it declares."""

    def test_audit_formatter_has_all_declared_fields(self):
        from activity_audit.formatters import AuditFormatter

        formatter = AuditFormatter()
        record = _make_record(
            "audit.model",
            model="Author",
            event_type="CREATE",
            request_id="req-abc",
            instance_id="7",
            instance_repr={"name": "Alice"},
            user_id="u-1",
            user_info={"email": "alice@example.com"},
            extra={"source": "test"},
        )

        output = _emit_to_stream(formatter, record)

        for field in (
            "timestamp",
            "level",
            "name",
            "message",
            "log_type",
            "model",
            "event_type",
            "request_id",
            "instance_id",
            "instance_repr",
            "user_id",
            "user_info",
            "extra",
        ):
            assert field in output, f"AuditFormatter missing field in output: {field}"

        assert output["model"] == "Author"
        assert output["event_type"] == "CREATE"
        assert output["request_id"] == "req-abc"
        assert output["instance_repr"] == {"name": "Alice"}

    def test_api_formatter_has_all_declared_fields(self):
        from activity_audit.formatters import APIFormatter

        formatter = APIFormatter()
        record = _make_record(
            "audit.request",
            service_name="test-svc",
            request_type="internal",
            protocol="http",
            request_id="req-xyz",
            user_id="u-2",
            user_info={"email": "bob@example.com"},
            request_repr={
                "method": "GET",
                "path": "/api/test/",
                "headers": {},
                "query_params": {},
            },
            response_repr={"headers": {}, "body": []},
            error_message=None,
            execution_time=0.045,
        )

        output = _emit_to_stream(formatter, record)

        for field in (
            "timestamp",
            "level",
            "name",
            "message",
            "log_type",
            "service_name",
            "request_type",
            "protocol",
            "request_id",
            "user_id",
            "user_info",
            "request_repr",
            "response_repr",
            "error_message",
            "execution_time",
        ):
            assert field in output, f"APIFormatter missing field in output: {field}"

        assert output["service_name"] == "test-svc"
        assert output["execution_time"] == pytest.approx(0.045)
        assert output["request_repr"]["method"] == "GET"

    def test_app_formatter_has_all_declared_fields(self):
        from activity_audit.formatters import AppFormatter

        formatter = AppFormatter()
        record = _make_record("app.general")

        output = _emit_to_stream(formatter, record)

        for field in (
            "timestamp",
            "level",
            "name",
            "path",
            "module",
            "function",
            "request_id",
            "message",
            "exception",
            "log_type",
        ):
            assert field in output, f"AppFormatter missing field in output: {field}"

    def test_app_formatter_includes_request_id_from_contextvars(self):
        """AppFormatter pulls request_id from contextvars when not on the record."""
        import structlog.contextvars as ctx
        from activity_audit.formatters import AppFormatter

        ctx.bind_contextvars(request_id="contextvar-id")
        try:
            formatter = AppFormatter()
            record = _make_record("app.general")
            output = _emit_to_stream(formatter, record)
            assert output["request_id"] == "contextvar-id"
        finally:
            ctx.clear_contextvars()

    def test_formatter_output_is_valid_json(self):
        """All formatters produce well-formed JSON (no trailing garbage)."""
        from activity_audit.formatters import APIFormatter, AppFormatter, AuditFormatter

        cases = [
            (
                AuditFormatter(),
                _make_record(
                    "audit.model",
                    model="X",
                    event_type="CREATE",
                    request_id="",
                    instance_id="1",
                    instance_repr={},
                    user_id="",
                    user_info={},
                    extra={},
                ),
            ),
            (
                APIFormatter(),
                _make_record(
                    "audit.request",
                    service_name="",
                    request_type="",
                    protocol="",
                    request_id="",
                    user_id="",
                    user_info={},
                    request_repr={},
                    response_repr={},
                    error_message=None,
                    execution_time=0,
                ),
            ),
            (AppFormatter(), _make_record("app")),
        ]

        for formatter, record in cases:
            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            handler.setFormatter(formatter)
            handler.emit(record)
            raw = stream.getvalue().strip()
            try:
                json.loads(raw)
            except json.JSONDecodeError as exc:
                pytest.fail(
                    f"{formatter.__class__.__name__} produced invalid JSON: {exc}\n{raw}"
                )


# ---------------------------------------------------------------------------
# 5. request_id propagation across app / api / audit loggers
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
class TestRequestIdPropagation:
    """A single UUID request_id is minted per request and appears identically
    in the app log (AppFormatter reads contextvars), the api log (middleware
    binds it via merge_contextvars), and the audit model log (signal snapshots
    it from contextvars in push_log).

    The app_log_capture fixture formats records at emit time so that
    contextvars are still populated when request_id is resolved.
    """

    def test_request_id_is_identical_across_all_three_loggers(
        self, app_log_capture, request_log_capture, model_log_capture
    ):
        client = APIClient()
        response = client.post(
            "/api/authors/",
            {"name": "Propagation Author", "experience": "Ten years"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

        api_records = request_log_capture.by_level("API")
        audit_records = model_log_capture.by_event_type("CREATE")
        app_outputs = app_log_capture.formatted_outputs

        assert api_records, "No API log captured"
        assert audit_records, "No AUDIT CREATE log captured"
        assert (
            app_outputs
        ), "No app log captured — check perform_create logs via app.publications"

        api_request_id = api_records[0].request_id
        audit_request_id = audit_records[0].request_id
        app_request_id = app_outputs[0]["request_id"]

        assert api_request_id, "API request_id must be non-empty"
        assert (
            api_request_id == audit_request_id
        ), f"api ({api_request_id!r}) != audit ({audit_request_id!r})"
        assert (
            api_request_id == app_request_id
        ), f"api ({api_request_id!r}) != app ({app_request_id!r})"

    def test_each_request_gets_a_unique_request_id(self, request_log_capture):
        client = APIClient()
        client.get("/api/authors/")
        client.get("/api/authors/")

        api_records = request_log_capture.by_level("API")
        assert len(api_records) >= 2, "Expected at least two API log records"

        first_id = api_records[0].request_id
        second_id = api_records[1].request_id
        assert (
            first_id != second_id
        ), "Different requests must receive different request_ids"

    def test_request_id_is_a_valid_uuid(self, request_log_capture):
        import uuid

        client = APIClient()
        client.get("/api/authors/")

        records = request_log_capture.by_level("API")
        assert records
        try:
            uuid.UUID(records[0].request_id)
        except ValueError:
            pytest.fail(f"request_id {records[0].request_id!r} is not a valid UUID")

    def test_m2m_log_carries_same_request_id_as_api_log(
        self, request_log_capture, model_log_capture
    ):
        """M2M changes triggered inside an API request must share the request_id
        that the middleware minted for that request.

        Without an active request the M2M signal still fires but request_id is
        empty — this test verifies the thread-local is properly read when the
        change happens within the request lifecycle.
        """
        client = APIClient()

        primary = Author.objects.create(name="Primary", experience="Lead")
        co = Author.objects.create(name="Co-author", experience="Support")
        book = Book.objects.create(title="Collaborative Work", author=primary)

        model_log_capture.clear()
        request_log_capture.clear()

        response = client.post(
            f"/api/books/{book.pk}/add_co_author/",
            {"co_author_id": co.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        api_records = request_log_capture.by_level("API")
        m2m_records = model_log_capture.by_event_type("M2M")

        assert api_records, "No API log captured for the add_co_author request"
        assert m2m_records, "No M2M audit log captured"

        api_request_id = api_records[0].request_id
        m2m_request_id = m2m_records[0].request_id

        assert api_request_id, "API request_id must be non-empty"
        assert m2m_request_id, "M2M request_id is empty — the thread-local was not read during M2M signal handling"
        assert (
            api_request_id == m2m_request_id
        ), f"request_id mismatch: api={api_request_id!r}, m2m={m2m_request_id!r}"
