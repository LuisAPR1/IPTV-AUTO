"""Regression coverage for durable, bounded and redacted run diagnostics."""

import contextvars
import json
import logging
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diagnostics import (
    REDACTED,
    Redactor,
    RunCapture,
    RunConsoleFormatter,
    RunHistory,
    RunLogHandler,
    diagnostic_event,
    has_active_run,
    register_secrets,
    sanitize_text,
)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "history.sqlite3"
        self.history = RunHistory(self.path)

    def capture(self, run_id="run-1", secrets=(), history=None):
        history = history or self.history
        redactor = Redactor(secrets)
        history.create(run_id, {"revision": "test"}, redactor)
        return RunCapture(history, run_id, redactor)

    def test_retains_newest_ten_runs_and_deletes_their_events(self):
        for number in range(14):
            capture = self.capture(f"run-{number}")
            capture.event("progress", "step", details={"step": 2})
            capture.finish("completed")

        self.assertEqual(
            [run["id"] for run in self.history.list()],
            [f"run-{number}" for number in range(13, 3, -1)],
        )
        self.assertIsNone(self.history.get("run-3"))
        with self.history.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 10)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM events WHERE run_id NOT IN (SELECT id FROM runs)"
            ).fetchone()[0], 0)

    def test_restart_recovers_only_unfinished_runs_once(self):
        completed = self.capture("completed")
        completed.finish("completed")
        pending = self.capture("pending")
        pending.event("progress", "Waiting for email", details={"step": 4})

        restarted = RunHistory(self.path)
        restarted.recover_interrupted()
        restarted.recover_interrupted()
        recovered = restarted.get("pending")
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual(recovered["error_type"], "ProcessInterrupted")
        self.assertIsNotNone(recovered["finished_at"])
        self.assertGreaterEqual(recovered["duration_seconds"], 0)
        self.assertEqual(sum(event["kind"] == "interrupted" for event in recovered["events"]), 1)
        self.assertEqual(restarted.get("completed")["status"], "completed")

    def test_event_limit_keeps_last_events_and_counts_omissions(self):
        history = RunHistory(self.path, max_events=3)
        capture = self.capture(history=history)
        for number in range(8):
            capture.event("progress", f"step {number}", details={"step": number})
        run = history.get("run-1")
        self.assertEqual([event["message"] for event in run["events"]], ["step 5", "step 6", "step 7"])
        self.assertEqual(run["event_count"], 3)
        self.assertEqual(run["dropped_events"], 5)
        self.assertEqual(run["step"], 7)

    def test_secrets_are_removed_before_data_reaches_disk(self):
        secret = "unusual password/+with spaces"
        capture = self.capture(secrets=[secret])
        with capture.activate():
            register_secrets("runtime-secret-value")
            diagnostic_event(
                "request", f"failed: {secret}; runtime-secret-value",
                headers={"Authorization": "Bearer private-value", "Cookie": "session=hidden-cookie"},
                nested={"username": "iptv-user", "email": "person@example.com"},
                url="https://proxy-user:proxy-pass@example.com/live/user/pass/77?token=query-secret#private",
                otp="451782",
            )
            capture.finish("error", f"request failed: {secret}", "RequestException")

        run = self.history.get("run-1")
        export = json.dumps(run)
        raw_database = self.path.read_bytes()
        for sensitive in (secret, "runtime-secret-value", "private-value", "hidden-cookie",
                          "iptv-user", "person@example.com", "proxy-user", "proxy-pass",
                          "query-secret", "451782", "/user/pass/"):
            self.assertNotIn(sensitive, export)
            self.assertNotIn(sensitive.encode(), raw_database)
        self.assertIn("example.com", export)
        self.assertIn(REDACTED, export)

    def test_redacts_encoded_values_mail_otp_and_relative_request_urls(self):
        redactor = Redactor(["private value/+with spaces"])
        original = (
            "private%20value%2F%2Bwith%20spaces private+value%2F%2Bwith+spaces "
            "user@example.com OTP: 349128 Bearer abc.def.ghi "
            "Max retries exceeded with url: /get?username=alpha&password=beta "
            "https://user:pass@api.example.com/check?code=211583#fragment"
        )
        cleaned = redactor.text(original)
        for value in ("private%20value", "private+value", "user@example.com", "349128",
                      "abc.def.ghi", "alpha", "beta", "user:pass", "211583", "fragment"):
            self.assertNotIn(value, cleaned)
        self.assertIn("api.example.com/check", cleaned)

    def test_exception_traceback_is_preserved_with_secrets_removed(self):
        capture = self.capture(secrets=["secret-in-exception"])
        handler = RunLogHandler()
        try:
            raise ValueError("secret-in-exception at https://example.com/request?key=private-query")
        except ValueError:
            record = logging.LogRecord("scraper", logging.ERROR, __file__, 1,
                                       "Failed secret-in-exception", (), sys.exc_info())
        with capture.activate():
            handler.emit(record)
        event = self.history.get("run-1")["events"][0]
        self.assertIn("ValueError", event["traceback"])
        self.assertIn("test_exception_traceback", event["traceback"])
        self.assertNotIn("secret-in-exception", json.dumps(event))
        self.assertNotIn("private-query", json.dumps(event))

    def test_threads_capture_only_their_own_runs_and_secrets(self):
        barrier = threading.Barrier(2)
        handler = RunLogHandler()
        captures = [self.capture(f"thread-{number}", [f"secret-{number}"]) for number in range(2)]

        def record(number):
            with captures[number].activate():
                barrier.wait(timeout=5)
                handler.emit(logging.LogRecord("scraper", logging.INFO, __file__, 1,
                                               f"message-{number} secret-{number}", (), None))
            self.assertFalse(has_active_run())

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(record, range(2)))
        for number in range(2):
            events = self.history.get(f"thread-{number}")["events"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["message"], f"message-{number} {REDACTED}")
        self.assertFalse(has_active_run())

    def test_explicit_copy_context_propagates_capture_to_nested_thread(self):
        capture = self.capture()
        with capture.activate():
            context = contextvars.copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertFalse(pool.submit(has_active_run).result())
                pool.submit(context.run, diagnostic_event, "email", "Waiting in child thread").result()
        self.assertEqual(self.history.get("run-1")["events"][0]["kind"], "email")
        self.assertFalse(has_active_run())

    def test_concurrent_events_do_not_lose_counts_or_exceed_limit(self):
        history = RunHistory(self.path, max_events=40)
        capture = self.capture(history=history)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda number: capture.event("log", f"event {number}"), range(120)))
        run = history.get("run-1")
        self.assertIsNone(history.storage_error)
        self.assertEqual(len(run["events"]), 40)
        self.assertEqual(run["event_count"], 40)
        self.assertEqual(run["dropped_events"], 80)

    def test_unrelated_loggers_and_logs_outside_run_are_ignored(self):
        capture = self.capture()
        handler = RunLogHandler()
        handler.emit(logging.LogRecord("scraper", logging.INFO, __file__, 1, "outside", (), None))
        with capture.activate():
            handler.emit(logging.LogRecord("urllib3", logging.INFO, __file__, 1, "unrelated", (), None))
            self.assertTrue(has_active_run())
        self.assertEqual(self.history.get("run-1")["events"], [])

    def test_capture_storage_failure_does_not_interrupt_generation(self):
        capture = self.capture()
        with patch.object(self.history, "add_event", side_effect=sqlite3.OperationalError("disk full")):
            with patch("sys.stderr"):
                capture.event("progress", "still generating")
        self.assertEqual(self.history.storage_error, "OperationalError")

    def test_active_context_is_restored_after_exception(self):
        capture = self.capture(secrets=["inside-secret"])
        with self.assertRaises(RuntimeError):
            with capture.activate():
                self.assertEqual(sanitize_text("inside-secret"), REDACTED)
                raise RuntimeError("test")
        self.assertFalse(has_active_run())

    def test_lost_events_warning_survives_recovery_and_restart(self):
        capture = self.capture("affected-run")
        with patch.object(self.history, "add_event", side_effect=sqlite3.OperationalError("disk full")):
            with patch("sys.stderr"):
                capture.event("log", "first lost event")
                capture.event("log", "second lost event")
        self.assertEqual(capture.lost_events, 2)
        self.assertEqual(self.history.storage_error, "OperationalError")
        capture.event("log", "storage recovered")
        self.assertIsNone(self.history.storage_error)
        affected = self.history.get("affected-run")
        self.assertEqual(affected["lost_events"], 2)
        self.assertTrue(affected["storage_warning"])
        self.assertEqual(affected["events"][0]["message"], "storage recovered")
        capture.finish("error", "Provider failed", "ProviderError")

        healthy = self.capture("healthy-run")
        healthy.event("log", "all events recorded")
        healthy.finish("completed")
        reopened = RunHistory(self.path)
        self.assertEqual(reopened.get("affected-run")["lost_events"], 2)
        self.assertTrue(reopened.get("affected-run")["storage_warning"])
        self.assertEqual(reopened.get("healthy-run")["lost_events"], 0)
        self.assertIsNone(reopened.get("healthy-run")["storage_warning"])

    def test_finish_persists_lost_events_without_another_event(self):
        capture = self.capture()
        with patch.object(self.history, "add_event", side_effect=sqlite3.OperationalError("disk full")):
            with patch("sys.stderr"):
                capture.event("log", "lost last event")
        capture.finish("completed")
        run = RunHistory(self.path).get("run-1")
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["lost_events"], 1)
        self.assertTrue(run["storage_warning"])
        self.assertIsNone(self.history.storage_error)
        self.assertFalse(capture.finish_failed)

    def test_presence_booleans_remain_useful_but_strings_stay_redacted(self):
        cleaned = Redactor().clean({
            "token_present": True, "email_configured": False,
            "nested": {"password_present": False, "secret_configured": True},
            "token": "private-token", "token_configured": "private-value",
            "authorization_present": "Bearer private-header", "otp": 324178,
        })
        self.assertIs(cleaned["token_present"], True)
        self.assertIs(cleaned["email_configured"], False)
        self.assertIs(cleaned["nested"]["password_present"], False)
        self.assertIs(cleaned["nested"]["secret_configured"], True)
        for key in ("token", "token_configured", "authorization_present", "otp"):
            self.assertEqual(cleaned[key], REDACTED)

    def test_console_formatter_redacts_message_and_complete_traceback(self):
        capture = self.capture(secrets=["console-private-secret"])
        try:
            raise ValueError("console-private-secret password=exception-password")
        except ValueError:
            record = logging.LogRecord("scraper", logging.ERROR, __file__, 1,
                                       "Failed %s", ("console-private-secret",), sys.exc_info())
        formatter = RunConsoleFormatter(logging.Formatter("%(levelname)s %(message)s"))
        with capture.activate():
            formatted = formatter.format(record)
        self.assertTrue(formatted.startswith("ERROR Failed " + REDACTED))
        self.assertIn("Traceback", formatted)
        self.assertIn("ValueError", formatted)
        self.assertNotIn("console-private-secret", formatted)
        self.assertNotIn("exception-password", formatted)
        # A later handler still receives the original record for its own formatting.
        self.assertEqual(record.getMessage(), "Failed console-private-secret")
        self.assertIn("console-private-secret", formatter.format(record))

    def test_http_hook_records_only_sanitized_response_metadata(self):
        import requests
        from scraper import IPTVScraper

        capture = self.capture()
        response = requests.Response()
        response.status_code = 403
        response.url = "https://api-user:api-password@example.com/submit?token=query-private#private-fragment"
        response.elapsed = timedelta(milliseconds=27)
        response._content = b"response-body-private"
        response.headers["Set-Cookie"] = "response-cookie-private"
        response.request = requests.Request(
            "POST", response.url, data="request-body-private",
            headers={"Authorization": "Bearer header-private", "Cookie": "request-cookie-private"},
        ).prepare()
        with capture.activate():
            IPTVScraper._record_http_response(response)
        event = self.history.get("run-1")["events"][0]
        self.assertEqual(event["kind"], "http")
        self.assertEqual(event["details"], {"method": "POST", "status_code": 403,
                                          "duration_ms": 27.0, "url": "https://example.com/submit?redacted"})
        for secret in ("api-user", "api-password", "query-private", "private-fragment",
                       "response-body-private", "response-cookie-private", "request-body-private",
                       "header-private", "request-cookie-private"):
            self.assertNotIn(secret, json.dumps(event))

    def test_proxy_threads_propagate_capture_and_summarize_failure_types(self):
        import requests
        from scraper import IPTVScraper

        capture = self.capture()
        scraper = IPTVScraper(email_service=Mock())
        self.addCleanup(scraper.session.close)
        self.assertIn(scraper._record_http_response, scraper.session.hooks["response"])
        proxies = deque(["http://blocked.example:80", "http://timeout.example:80"])
        manager = SimpleNamespace(has_proxies=lambda: bool(proxies), get_next_proxy=proxies.popleft,
                                  mark_failed=Mock())

        def fake_get(url, **kwargs):
            self.assertTrue(has_active_run())
            if "timeout.example" in kwargs["proxies"]["https"]:
                raise requests.exceptions.ConnectTimeout("Timed out")
            response = requests.Response()
            response.status_code = 429
            response.url = url
            response.elapsed = timedelta(milliseconds=10)
            response.request = requests.Request("GET", url).prepare()
            kwargs["hooks"]["response"](response)
            return response

        with patch("requests.get", side_effect=fake_get):
            with patch("requests.sessions.Session.request", side_effect=AssertionError("Network disabled")):
                with capture.activate():
                    selected = scraper._find_working_proxy(manager)
        self.assertIsNone(selected)
        events = self.history.get("run-1")["events"]
        self.assertEqual([event["kind"] for event in events], ["http", "proxy_search"])
        self.assertEqual(events[-1]["details"], {
            "tested": 2, "found": False, "failure_counts": {"http_429": 1, "ConnectTimeout": 1},
        })
        self.assertEqual(manager.mark_failed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
