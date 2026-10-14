"""Bounded, redacted diagnostics for web runs (one application worker)."""

import contextvars
import json
import logging
import os
import platform
import re
import sqlite3
import sys
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

REDACTED = "[OCULTO]"
RETENTION = 10
MAX_EVENTS = 600
MAX_TEXT = 12000
INCOMPLETE_WARNING = "Alguns eventos desta execução não foram guardados devido a uma falha de diagnóstico."
_active_run = contextvars.ContextVar("diagnostic_run", default=None)
_sensitive_key = re.compile(
    r"password|passwd|secret|token|authorization|cookie|username|email|"
    r"verification_code|validatecode|^otp$", re.I
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Redactor:
    def __init__(self, secrets=()):
        self._lock = threading.RLock()
        self._secrets = set()
        self.register(*secrets)

    def register(self, *values):
        with self._lock:
            for value in values:
                if value:
                    text = str(value)
                    self._secrets.update((text, quote(text, safe=""), quote_plus(text)))

    def text(self, value):
        value = str(value)
        with self._lock:
            for secret in sorted(self._secrets, key=len, reverse=True):
                value = value.replace(secret, REDACTED)
        # URLs never retain authentication, query values or fragments. Playlist
        # paths can also embed IPTV credentials, so redact their entire path.
        def clean_url(match):
            try:
                url = urlsplit(match.group(0))
                host = url.netloc.rsplit("@", 1)[-1]
                path = url.path
                if re.search(r"/(live|movie|series|timeshift)/", path, re.I):
                    path = "/" + REDACTED
                return urlunsplit((url.scheme, host, path,
                                   "redacted" if url.query else "", ""))
            except ValueError:
                return REDACTED
        value = re.sub(r"(?:https?|socks[45]h?)://[^\s<>\"']+", clean_url, value)
        value = re.sub(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", REDACTED, value)
        value = re.sub(r"(?i)\b(Bearer|Basic)\s+\S+", r"\1 " + REDACTED, value)
        value = re.sub(
            r"(?im)(\b(?:password|passwd|username|token|secret|cookie|authorization|"
            r"código (?:obtido|encontrado)|code|otp)\b[^:=\n]{0,25}[:=]\s*)"
            r"(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;&]+)",
            lambda m: m.group(1) + REDACTED, value
        )
        # Relative URLs in requests exception messages bypass clean_url above.
        value = re.sub(r"([?&][\w%.-]+=)[^\s&\"'<>)]*", r"\1" + REDACTED, value)
        value = re.sub(r"\b\d{6}\b", REDACTED, value)
        return value[:MAX_TEXT] + ("… [truncado]" if len(value) > MAX_TEXT else "")

    def clean(self, value):
        if isinstance(value, dict):
            return {str(k): v if isinstance(v, bool) and str(k).endswith(("_present", "_configured"))
                    else v if str(k) in ("email_timeout_seconds", "email_poll_seconds") and isinstance(v, (int, float))
                    else REDACTED if _sensitive_key.search(str(k)) else self.clean(v)
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value[:100]]
        if isinstance(value, str):
            return self.text(value)
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return self.text(value)


def sanitize_text(value):
    active = _active_run.get()
    redactor = active.redactor if active else Redactor(
        os.getenv(key, "") for key in ("PERSONAL_GMAIL", "GMAIL_APP_PASSWORD", "DIAGNOSTICS_TOKEN")
    )
    return redactor.text(value)


def register_secrets(*values):
    active = _active_run.get()
    if active:
        active.redactor.register(*values)


def has_active_run():
    return _active_run.get() is not None


def diagnostic_event(kind, message, **details):
    active = _active_run.get()
    if active:
        active.event(kind, message, details=details)


def runtime_metadata():
    packages = {}
    for name in ("Flask", "requests", "beautifulsoup4", "gunicorn", "PySocks"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "não instalado"
    return {"python": platform.python_version(), "platform": platform.system(),
            "revision": os.getenv("RENDER_GIT_COMMIT", os.getenv("APP_VERSION", "local")),
            "packages": packages}


class RunHistory:
    """SQLite stores only sanitized data; connections never cross threads."""

    def __init__(self, path, retention=RETENTION, max_events=MAX_EVENTS):
        self.path = os.path.abspath(path)
        self.retention = retention
        self.max_events = max_events
        self.storage_error = None
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS event_run ON events(run_id, sequence);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

    def create(self, run_id, metadata, redactor):
        data = {"id": run_id, "status": "running", "created_at": utc_now(),
                "finished_at": None, "duration_seconds": None, "step": 0,
                "message": "A iniciar automação", "error": None, "error_type": None,
                "attempt": 0, "total_attempts": None, "event_count": 0,
                "dropped_events": 0, "lost_events": 0, "storage_warning": None,
                "metadata": redactor.clean(metadata)}
        with self.connection() as db:
            db.execute("INSERT INTO runs(id, data) VALUES (?, ?)", (run_id, json.dumps(data)))
            db.execute("DELETE FROM runs WHERE id NOT IN "
                       "(SELECT id FROM runs ORDER BY sequence DESC LIMIT ?)", (self.retention,))

    def add_event(self, run_id, event):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return
            data = json.loads(row[0])
            if event.get("lost_events", 0):
                data.update(lost_events=event["lost_events"], storage_warning=INCOMPLETE_WARNING)
            db.execute("INSERT INTO events(run_id, data) VALUES (?, ?)", (run_id, json.dumps(event)))
            if data["event_count"] >= self.max_events:
                db.execute("DELETE FROM events WHERE sequence = "
                           "(SELECT sequence FROM events WHERE run_id = ? ORDER BY sequence LIMIT 1)", (run_id,))
                data["dropped_events"] += 1
            else:
                data["event_count"] += 1
            if event["kind"] == "progress":
                data.update(step=event["details"]["step"], message=event["message"])
            elif event["kind"] == "attempt":
                data.update(attempt=event["details"]["attempt"],
                            total_attempts=event["details"]["total_attempts"])
            db.execute("UPDATE runs SET data = ? WHERE id = ?", (json.dumps(data), run_id))

    def finish(self, run_id, status, error=None, error_type=None, lost_events=0):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return
            data = json.loads(row[0])
            if lost_events:
                data.update(lost_events=lost_events, storage_warning=INCOMPLETE_WARNING)
            finished = utc_now()
            data.update(status=status, finished_at=finished, error=error, error_type=error_type,
                        duration_seconds=round((datetime.fromisoformat(finished) -
                                                datetime.fromisoformat(data["created_at"])).total_seconds(), 3))
            db.execute("UPDATE runs SET data = ? WHERE id = ?", (json.dumps(data), run_id))

    def get(self, run_id):
        with self.connection() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            data["events"] = [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM events WHERE run_id = ? ORDER BY sequence", (run_id,))]
            return data

    def list(self, include_events=False):
        with self.connection() as db:
            db.execute("BEGIN")
            runs = [json.loads(row[0]) for row in db.execute("SELECT data FROM runs ORDER BY sequence DESC")]
            if include_events:
                for run in runs:
                    run["events"] = [json.loads(row[0]) for row in db.execute(
                        "SELECT data FROM events WHERE run_id = ? ORDER BY sequence", (run["id"],))]
            return runs

    def recover_interrupted(self):
        # Called once per process startup; deployment intentionally uses one worker.
        for run in self.list():
            if run["status"] == "running":
                message = "Execução interrompida: o processo do servidor reiniciou antes de concluir."
                self.add_event(run["id"], {"timestamp": utc_now(), "level": "ERROR", "source": "app",
                                          "kind": "interrupted", "message": message, "details": {}})
                self.finish(run["id"], "interrupted", message, "ProcessInterrupted")


class RunCapture:
    def __init__(self, history, run_id, redactor):
        self.history, self.run_id, self.redactor = history, run_id, redactor
        self.lost_events = 0
        self.finish_failed = False
        self._lock = threading.RLock()

    def storage_failed(self, exc):
        # Do not recursively log a broken logging sink or interrupt generation.
        if not self.history.storage_error:
            print("Diagnóstico: falha de armazenamento (" + type(exc).__name__ + ")", file=sys.stderr)
        self.history.storage_error = type(exc).__name__

    def event(self, kind, message, details=None, level="INFO", source="app", trace=None):
        with self._lock:
            try:
                event = {"timestamp": utc_now(), "level": level, "source": source,
                         "kind": kind, "message": self.redactor.text(message),
                         "details": self.redactor.clean(details or {}), "lost_events": self.lost_events}
                if trace:
                    event["traceback"] = self.redactor.text(trace)
                self.history.add_event(self.run_id, event)
                self.history.storage_error = None
            except Exception as exc:
                self.lost_events += 1
                self.storage_failed(exc)

    def finish(self, status, error=None, error_type=None):
        try:
            self.history.finish(self.run_id, status, self.redactor.text(error) if error else None,
                                error_type, lost_events=self.lost_events)
            self.history.storage_error = None
        except Exception as exc:
            self.finish_failed = True
            self.storage_failed(exc)

    @contextmanager
    def activate(self):
        token = _active_run.set(self)
        try:
            yield self
        finally:
            _active_run.reset(token)


class RunLogHandler(logging.Handler):
    def emit(self, record):
        active = _active_run.get()
        if active and record.name.split(".")[0] in ("app", "__main__", "scraper", "email_service", "proxy_manager"):
            try:
                active.event("log", record.getMessage(), level=record.levelname, source=record.name,
                             trace="".join(traceback.format_exception(*record.exc_info)) if record.exc_info else None)
            except Exception as exc:
                active.lost_events += 1
                active.storage_failed(exc)


class RunConsoleFormatter(logging.Formatter):
    """Sanitize the fully formatted traceback without mutating the log record."""

    def __init__(self, original):
        super().__init__()
        self.original = original or logging.Formatter()

    def format(self, record):
        formatted = self.original.format(record)
        return sanitize_text(formatted) if has_active_run() else formatted


def install_log_capture():
    root = logging.getLogger()
    for handler in root.handlers:
        if not isinstance(handler, RunLogHandler) and not isinstance(handler.formatter, RunConsoleFormatter):
            handler.setFormatter(RunConsoleFormatter(handler.formatter))
    if not any(isinstance(handler, RunLogHandler) for handler in root.handlers):
        root.addHandler(RunLogHandler(level=logging.INFO))
