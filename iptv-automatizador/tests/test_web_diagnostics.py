"""Exercise the public web flow without making external requests."""

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as web
from diagnostics import Redactor, RunCapture, RunHistory, RunLogHandler


class WebDiagnosticsTests(unittest.TestCase):
    token = "test-diagnostics-private-key"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.history = RunHistory(Path(self.directory.name) / "history.sqlite3")
        self.start_patch(patch.dict(web.app.config, TESTING=True))
        self.start_patch(patch.object(web, "jobs", {}))
        self.history_mock = self.start_patch(patch.object(web, "get_history", return_value=self.history))
        self.start_patch(patch.object(web, "PERSONAL_GMAIL", "test-mail@example.com"))
        self.start_patch(patch.object(web, "GMAIL_APP_PASSWORD", "mail-app-private-password"))
        self.start_patch(patch.object(web, "runtime_metadata", return_value={"revision": "test"}))
        self.start_patch(patch.object(web.logging.getLogger(), "handlers", [RunLogHandler()]))
        self.start_patch(patch("requests.sessions.Session.request", side_effect=AssertionError("Network disabled in tests")))
        self.email_class = self.start_patch(patch.object(web, "TempMailService"))
        self.scraper_class = self.start_patch(patch.object(web, "IPTVScraper"))
        self.save_latest = self.start_patch(patch.object(web, "save_latest_trial"))
        self.scraper = self.scraper_class.return_value
        self.scraper.last_error = ""
        self.scraper.run_automation.return_value = None
        self.client = web.app.test_client()
        self.headers = {}

    def start_patch(self, item):
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def create_run(self, run_id="existing-run"):
        redactor = Redactor([self.token])
        self.history.create(run_id, {"revision": "test"}, redactor)
        capture = RunCapture(self.history, run_id, redactor)
        capture.event("progress", "Fetching page", details={"step": 2})
        return capture

    def generate(self, execute=True):
        with patch.object(web.threading, "Thread") as thread_class:
            response = self.client.post("/api/generate")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        kwargs = thread_class.call_args.kwargs
        self.assertTrue(kwargs["daemon"])
        if execute:
            kwargs["target"](*kwargs["args"])
        return response.json["job_id"]

    def test_all_diagnostic_apis_are_public(self):
        self.create_run()
        routes = ("/api/diagnostics/runs", "/api/diagnostics/runs/existing-run",
                  "/api/diagnostics/export", "/api/diagnostics/runs/existing-run/export")
        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertNotIn("Authorization", response.headers.get("Vary", ""))

    def test_legacy_token_configuration_does_not_restrict_access(self):
        with patch.dict(web.app.config, DIAGNOSTICS_TOKEN="obsolete-key"):
            response = self.client.get("/api/diagnostics/runs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["runs"], [])

    def test_page_serves_only_shell_without_saved_runs_or_secret(self):
        self.create_run("private-run-id")
        response = self.client.get("/diagnostics")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertNotIn("private-run-id", body)
        self.assertNotIn(self.token, body)
        self.assertNotIn("Fetching page", body)
        self.assertNotIn("auth-form", body)
        self.assertNotIn("Bearer", body)
        self.assertNotIn('type="password"', body)
        self.assertNotIn("localStorage", body)
        self.assertNotIn("sessionStorage", body)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.history_mock.assert_not_called()

    def test_list_detail_and_json_download_have_expected_scope(self):
        self.create_run("first-run").finish("completed")
        self.create_run("second-run").finish("error", "Provider failed", "ProviderError")
        listing = self.client.get("/api/diagnostics/runs", headers=self.headers)
        self.assertEqual([run["id"] for run in listing.json["runs"]], ["second-run", "first-run"])
        self.assertNotIn("events", listing.json["runs"][0])
        detail = self.client.get("/api/diagnostics/runs/second-run", headers=self.headers)
        self.assertEqual(detail.json["run"]["events"][0]["kind"], "progress")
        all_runs = self.client.get("/api/diagnostics/export", headers=self.headers)
        self.assertEqual(all_runs.mimetype, "application/json")
        self.assertIn("attachment", all_runs.headers["Content-Disposition"])
        self.assertEqual(len(all_runs.json["runs"]), 2)
        self.assertTrue(all_runs.json["runs"][0]["events"])
        one_run = self.client.get("/api/diagnostics/runs/first-run/export", headers=self.headers)
        self.assertEqual([run["id"] for run in one_run.json["runs"]], ["first-run"])
        for response in (listing, detail, all_runs, one_run):
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        for route in ("/api/diagnostics/runs/missing", "/api/diagnostics/runs/missing/export"):
            self.assertEqual(self.client.get(route, headers=self.headers).status_code, 404)

    def test_success_is_recorded_without_exporting_generated_credentials(self):
        credentials = {"username": "generated-user", "password": "generated-password",
                       "m3u_url": "https://example.com/get?username=generated-user&password=generated-password"}
        self.scraper.run_automation.return_value = credentials
        run_id = self.generate()
        progress = self.client.get(f"/api/progress/{run_id}")
        self.assertEqual(progress.json["status"], "completed")
        self.assertEqual(progress.json["percent"], 100)
        self.assertEqual(progress.json["credentials"], credentials)
        self.save_latest.assert_called_once_with(credentials)
        run = self.history.get(run_id)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["events"][-1]["kind"], "finish")
        self.email_class.return_value.cleanup.assert_called_once()
        self.scraper.session.close.assert_called_once()
        export = self.client.get("/api/diagnostics/export", headers=self.headers).get_data(as_text=True)
        for secret in (*credentials.values(), self.token, "test-mail@example.com", "mail-app-private-password"):
            self.assertNotIn(secret, export)

    def test_swallowed_scraper_error_is_available_in_diagnostic_report(self):
        self.scraper.last_error = "Provider refused https://example.com/validate?password=provider-password"
        run_id = self.generate()
        run = self.history.get(run_id)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_type"], "GenerationFailed")
        self.assertIn("Provider refused", run["error"])
        self.assertNotIn("provider-password", json.dumps(run))
        self.assertEqual(web.jobs[run_id]["error"], run["error"])
        self.save_latest.assert_not_called()
        self.email_class.return_value.cleanup.assert_called_once()
        self.scraper.session.close.assert_called_once()

    def test_unexpected_exception_keeps_redacted_traceback_and_final_status(self):
        self.scraper.run_automation.side_effect = RuntimeError("mail-app-private-password code=543219")
        run_id = self.generate()
        run = self.history.get(run_id)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_type"], "RuntimeError")
        tracebacks = [event["traceback"] for event in run["events"] if "traceback" in event]
        self.assertTrue(any("RuntimeError" in trace for trace in tracebacks))
        self.assertNotIn("mail-app-private-password", json.dumps(run))
        self.assertNotIn("543219", json.dumps(run))
        self.email_class.return_value.cleanup.assert_called_once()
        self.scraper.session.close.assert_called_once()

    def test_initialization_failure_is_recorded_without_cleanup_of_missing_service(self):
        self.email_class.side_effect = ValueError("Email initialization failed")
        run_id = self.generate()
        run = self.history.get(run_id)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_type"], "ValueError")
        self.assertIn("Email initialization failed", run["error"])
        self.scraper_class.assert_not_called()
        self.email_class.return_value.cleanup.assert_not_called()
        self.assertFalse(any("UnboundLocalError" in event.get("traceback", "") for event in run["events"]))

    def test_cleanup_errors_are_recorded_without_hiding_primary_error(self):
        self.scraper.last_error = "Primary provider failure"
        self.email_class.return_value.cleanup.side_effect = RuntimeError("Email cleanup failed")
        self.scraper.session.close.side_effect = OSError("HTTP cleanup failed")
        run_id = self.generate()
        run = self.history.get(run_id)
        self.assertIn("Primary provider failure", run["error"])
        self.assertEqual(run["error_type"], "GenerationFailed")
        traces = "\n".join(event.get("traceback", "") for event in run["events"])
        self.assertIn("Email cleanup failed", traces)
        self.assertIn("HTTP cleanup failed", traces)
        self.assertIsNotNone(run["finished_at"])

    def test_worker_start_failure_finishes_the_created_report(self):
        with patch.object(web.threading, "Thread") as thread_class:
            thread_class.return_value.start.side_effect = RuntimeError("Worker failed mail-app-private-password")
            response = self.client.post("/api/generate")
        self.assertEqual(response.status_code, 503)
        run = self.history.get(response.json["job_id"])
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_type"], "RuntimeError")
        self.assertNotIn("mail-app-private-password", json.dumps(run))
        self.assertEqual(web.jobs[run["id"]]["status"], "error")

    def test_repeated_generation_joins_existing_worker_even_after_five_minutes(self):
        run_id = self.generate(execute=False)
        web.jobs[run_id]["created_at"] = 1
        with patch.object(web.threading, "Thread") as thread_class:
            response = self.client.post("/api/generate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["job_id"], run_id)
        thread_class.assert_not_called()
        self.assertEqual(len(self.history.list()), 1)
        self.assertEqual(web.jobs[run_id]["status"], "running")

    def test_storage_failure_returns_actionable_error_and_does_not_start_worker(self):
        self.history_mock.side_effect = sqlite3.OperationalError("storage unavailable")
        with patch.object(web.threading, "Thread") as thread_class:
            response = self.client.post("/api/generate")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["success"])
        thread_class.assert_not_called()
        self.assertFalse(web.jobs)
        response = self.client.get("/api/diagnostics/export", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("Traceback", response.get_data(as_text=True))

    def test_progress_survives_restart_with_interruption_detail(self):
        self.create_run("interrupted-run")
        self.history.recover_interrupted()
        response = self.client.get("/api/progress/interrupted-run")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "error")
        self.assertIn("reiniciou", response.json["error"])
        self.assertEqual(response.json["diagnostics_url"], "/diagnostics#interrupted-run")
        self.assertIsNone(response.json["credentials"])
        self.assertEqual(self.client.get("/api/progress/missing-run").status_code, 404)

    def test_failed_event_writes_are_reported_as_degraded_diagnostics(self):
        original_add_event = self.history.add_event
        first_write = True

        def fail_once(*args, **kwargs):
            nonlocal first_write
            if first_write:
                first_write = False
                raise sqlite3.OperationalError("disk full")
            return original_add_event(*args, **kwargs)

        with patch.object(self.history, "add_event", side_effect=fail_once), patch("sys.stderr"):
            run_id = self.generate()
        self.assertFalse(web.jobs[run_id]["diagnostics_available"])
        self.assertIsNone(self.history.storage_error)
        response = self.client.get("/api/diagnostics/export", headers=self.headers)
        self.assertTrue(response.json["storage_warning"])
        self.assertEqual(response.json["runs"][0]["lost_events"], 1)

        healthy_run_id = self.generate()
        self.assertTrue(web.jobs[healthy_run_id]["diagnostics_available"])
        response = self.client.get(f"/api/diagnostics/runs/{healthy_run_id}/export", headers=self.headers)
        self.assertIsNone(response.json["storage_warning"])
        self.assertIsNone(response.json["runs"][0]["storage_warning"])
        # The warning belongs to the affected run, including after reopening storage.
        self.history_mock.return_value = RunHistory(self.history.path)
        response = self.client.get(f"/api/diagnostics/runs/{run_id}/export", headers=self.headers)
        self.assertTrue(response.json["storage_warning"])
        self.assertEqual(response.json["runs"][0]["lost_events"], 1)

    def test_real_scraper_retries_preserve_attempts_last_error_and_tracebacks(self):
        import scraper as scraper_module

        manager = Mock()
        manager.has_proxies.return_value = True
        instances = []

        def construct_scraper(**kwargs):
            instance = scraper_module.IPTVScraper(**kwargs)
            instances.append(instance)
            return instance

        self.scraper_class.side_effect = construct_scraper
        searches = []

        def find_proxy(*args, **kwargs):
            attempt = self.history.list()[0]["attempt"]
            searches.append(attempt)
            return f"http://proxy-{attempt}.example:8080"

        failures = [RuntimeError("First provider failure"),
                    ValueError("Last provider failure mail-app-private-password code=548321")]
        with patch.object(scraper_module, "MAX_PROXY_RETRIES", 2):
            with patch.object(scraper_module.IPTVScraper, "_get_proxy_manager", return_value=manager):
                with patch.object(scraper_module.IPTVScraper, "_find_working_proxy", side_effect=find_proxy):
                    with patch.object(scraper_module.IPTVScraper, "_run_single_attempt", side_effect=failures) as attempt:
                        run_id = self.generate()
        self.assertEqual(attempt.call_count, 2)
        self.assertEqual(searches, [1, 2])
        self.assertEqual(instances[0].last_error, str(failures[-1]))
        self.assertEqual(manager.mark_failed.call_count, 2)
        run = self.history.get(run_id)
        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error_type"], "GenerationFailed")
        self.assertEqual(run["attempt"], 2)
        self.assertEqual(run["total_attempts"], 2)
        self.assertIn("Last provider failure", run["error"])
        attempts = [event for event in run["events"] if event["kind"] == "attempt"]
        self.assertEqual([event["details"]["attempt"] for event in attempts], [1, 2])
        traces = "\n".join(event.get("traceback", "") for event in run["events"])
        self.assertIn("RuntimeError", traces)
        self.assertIn("ValueError", traces)
        self.assertNotIn("mail-app-private-password", json.dumps(run))
        self.assertNotIn("548321", json.dumps(run))


if __name__ == "__main__":
    unittest.main()
