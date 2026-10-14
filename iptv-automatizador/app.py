#!/usr/bin/env python3
"""
Web App Mobile para Gerador de Trials IPTV
Interface Web moderna e responsiva para telemóveis e desktop.
"""

import os
import sys
import json
import uuid
import threading
import logging
import copy
import time
import sqlite3
from functools import wraps
from typing import Dict, Any
from flask import Flask, render_template, jsonify, request, Response

# Assegurar que o directório actual está no path de importação
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import PERSONAL_GMAIL, GMAIL_APP_PASSWORD, DIAGNOSTICS_DB_PATH
from config import EMAIL_TIMEOUT, EMAIL_POLL_INTERVAL, MAX_PROXY_RETRIES, PROXYSCRAPE_TYPES, PROXYSCRAPE_TIMEOUT
from email_service import TempMailService
from scraper import IPTVScraper
from diagnostics import (RunHistory, RunCapture, Redactor, RETENTION, install_log_capture,
                         diagnostic_event, sanitize_text, runtime_metadata, utc_now)

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)
install_log_capture()

app = Flask(__name__, template_folder=os.path.join(current_dir, "templates"))

# Estado dos Jobs em memória
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.RLock()
history_lock = threading.Lock()
history = None
history_initialization_error = None
LATEST_TRIAL_FILE = os.path.join(current_dir, "latest_trial.json")


def get_history():
    global history, history_initialization_error
    with history_lock:
        if history is None:
            try:
                store = RunHistory(DIAGNOSTICS_DB_PATH)
                store.recover_interrupted()
                history = store
                history_initialization_error = None
            except Exception as exc:
                history_initialization_error = type(exc).__name__
                raise
        return history


def save_latest_trial(creds: Dict[str, str]):
    """Guarda as últimas credenciais geradas em ficheiro para consulta rápida."""
    try:
        with open(LATEST_TRIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Erro ao guardar último trial")


def load_latest_trial() -> Dict[str, str]:
    """Carrega as últimas credenciais geradas."""
    if os.path.exists(LATEST_TRIAL_FILE):
        try:
            with open(LATEST_TRIAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def run_scraper_task(job_id: str, capture: RunCapture):
    """Executa a automação IPTV em segundo plano."""
    with capture.activate():
        job = jobs[job_id]
        email_service = None
        scraper = None
        status, error, error_type, credentials = "error", None, None, None

        def on_progress(step_index: int, message: str):
            message = sanitize_text(message)
            with jobs_lock:
                job.update(step=step_index, percent=max(5, min(95, int(step_index / 8.0 * 100))),
                           message=message)
                log_entry = f"[Passo {step_index}] {message}"
                if not job["logs"] or job["logs"][-1] != log_entry:
                    job["logs"].append(log_entry)
                    job["logs"] = job["logs"][-100:]
            diagnostic_event("progress", message, step=step_index)

        try:
            diagnostic_event("start", "Execução iniciada")
            on_progress(1, "Inicializando serviço de email e parâmetros...")
            email_service = TempMailService(personal_gmail=PERSONAL_GMAIL, app_password=GMAIL_APP_PASSWORD)
            scraper = IPTVScraper(email_service=email_service, progress_callback=on_progress)
            credentials = scraper.run_automation()
            if credentials and credentials.get("username") and credentials.get("password"):
                capture.redactor.register(*credentials.values())
                save_latest_trial(credentials)
                status = "completed"
                logger.info("Job %s concluído com sucesso.", job_id)
            else:
                detail = getattr(scraper, "last_error", "")
                error = "Não foi possível extrair todas as credenciais." + (f" Último erro: {detail}" if detail else "")
                error_type = "GenerationFailed"
                logger.error("Job %s falhou: %s", job_id, error)
        except Exception as exc:
            error, error_type = str(exc), type(exc).__name__
            logger.exception("Job %s falhou com erro", job_id)
        finally:
            if email_service is not None:
                try:
                    email_service.cleanup()
                except Exception:
                    logger.exception("Falha na limpeza do serviço de email")
            if scraper is not None:
                try:
                    scraper.session.close()
                except Exception:
                    logger.exception("Falha na limpeza da sessão HTTP")
            error = sanitize_text(error) if error else None
            diagnostic_event("finish", "Execução concluída" if status == "completed" else "Execução falhou",
                             status=status, error=error, error_type=error_type)
            capture.finish(status, error, error_type)
            with jobs_lock:
                job.update(status=status, error=error,
                           message="Trial de 48h gerado com sucesso!" if status == "completed" else error,
                           credentials=credentials if status == "completed" else None,
                           finished_at=time.time(), diagnostics_available=not (capture.lost_events or capture.finish_failed))
                if status == "completed":
                    job["percent"] = 100


@app.route("/")
def index():
    """Página principal (Mobile-First Web App)."""
    return render_template("index.html")


@app.route("/diagnostics")
def diagnostics_page():
    return render_template("diagnostics.html")


def diagnostics_storage_errors(view):
    @wraps(view)
    def protected(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except (OSError, sqlite3.Error):
            return jsonify(success=False, message="Histórico indisponível. Verifica o armazenamento do servidor."), 503
    return protected


@app.after_request
def private_diagnostics(response):
    if request.path == "/diagnostics" or request.path.startswith("/api/diagnostics"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


def diagnostic_report(runs):
    store = get_history()
    return {"schema_version": 1, "exported_at": utc_now(), "retention": RETENTION,
            "storage_warning": "Alguns eventos podem não ter sido guardados." if
            store.storage_error or any(run.get("storage_warning") for run in runs) else None,
            "runs": runs}


def report_download(payload, filename):
    return Response(json.dumps(payload, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/diagnostics/runs")
@diagnostics_storage_errors
def diagnostics_runs():
    return jsonify(diagnostic_report(get_history().list()))


@app.get("/api/diagnostics/runs/<job_id>")
@diagnostics_storage_errors
def diagnostics_run(job_id):
    run = get_history().get(job_id)
    if not run:
        return jsonify(success=False, message="Execução não encontrada nas últimas 10."), 404
    return jsonify(schema_version=1, run=run)


@app.get("/api/diagnostics/export")
@diagnostics_storage_errors
def diagnostics_export():
    return report_download(diagnostic_report(get_history().list(include_events=True)), "diagnostico-ultimas-10.json")


@app.get("/api/diagnostics/runs/<job_id>/export")
@diagnostics_storage_errors
def diagnostics_run_export(job_id):
    run = get_history().get(job_id)
    if not run:
        return jsonify(success=False, message="Execução não encontrada nas últimas 10."), 404
    return report_download(diagnostic_report([run]), f"diagnostico-{run['id']}.json")


@app.route("/api/generate", methods=["POST"])
def generate_trial():
    """Inicia um novo processo de geração de trial IPTV."""
    with jobs_lock:
        # A background thread is not cancelled by Gunicorn's request timeout.
        for j_id, j_data in jobs.items():
            if j_data.get("status") == "running":
                return jsonify({
                    "success": True,
                    "job_id": j_id,
                    "message": "Já existe uma automação em curso. A acompanhar progresso..."
                })
        job_id = uuid.uuid4().hex
        redactor = Redactor((PERSONAL_GMAIL, GMAIL_APP_PASSWORD))
        try:
            store = get_history()
            metadata = runtime_metadata()
            metadata["settings"] = {"gmail_configured": bool(PERSONAL_GMAIL and GMAIL_APP_PASSWORD),
                                    "email_timeout_seconds": EMAIL_TIMEOUT,
                                    "email_poll_seconds": EMAIL_POLL_INTERVAL,
                                    "max_proxy_retries": MAX_PROXY_RETRIES,
                                    "proxyscrape_types": PROXYSCRAPE_TYPES,
                                    "proxyscrape_timeout_ms": PROXYSCRAPE_TIMEOUT,
                                    "workers_supported": 1}
            store.create(job_id, metadata, redactor)
        except Exception:
            return jsonify(success=False, message="Não foi possível guardar o diagnóstico. Verifica o armazenamento do servidor."), 503
        capture = RunCapture(store, job_id, redactor)
        while len(jobs) >= RETENTION:
            del jobs[next(iter(jobs))]
        jobs[job_id] = {"id": job_id, "status": "running", "step": 1, "percent": 5,
                        "message": "Iniciando sessão de automação...", "logs": [],
                        "credentials": None, "error": None, "created_at": time.time(),
                        "diagnostics_url": f"/diagnostics#{job_id}"}
        try:
            threading.Thread(target=run_scraper_task, args=(job_id, capture), daemon=True).start()
        except Exception as exc:
            with capture.activate():
                logger.exception("Falha ao iniciar worker de geração")
                error = sanitize_text(str(exc))
            capture.finish("error", error, type(exc).__name__)
            jobs[job_id].update(status="error", error=error)
            return jsonify(success=False, job_id=job_id, message="Falha ao iniciar execução. Consulta o diagnóstico."), 503

    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "Automação iniciada."
    })


@app.route("/api/progress/<job_id>", methods=["GET"])
def get_progress(job_id: str):
    """Retorna o estado e progresso actual de um job."""
    with jobs_lock:
        job = copy.deepcopy(jobs.get(job_id))
    if not job:
        try:
            saved = get_history().get(job_id)
        except Exception:
            return jsonify(success=False, message="Diagnóstico temporariamente indisponível."), 503
        if not saved:
            return jsonify({"success": False, "message": "Job não encontrado. Consulta o histórico de diagnóstico."}), 404
        job = {"id": job_id, "status": "error" if saved["status"] == "interrupted" else saved["status"],
               "step": saved["step"], "percent": 100 if saved["status"] == "completed" else 0,
               "message": saved["message"], "error": saved["error"], "logs": [], "credentials": None,
               "diagnostics_url": f"/diagnostics#{job_id}"}
    return jsonify(job)


@app.route("/api/latest", methods=["GET"])
def get_latest():
    """Retorna as credenciais do último trial gerado."""
    latest = load_latest_trial()
    return jsonify(latest)


@app.route("/api/download-m3u")
def download_m3u():
    """Redireciona ou descarrega a playlist M3U."""
    m3u_url = request.args.get("url")
    if not m3u_url:
        return "URL M3U não fornecido", 400
    
    try:
        import requests
        resp = requests.get(m3u_url, timeout=15)
        if resp.status_code == 200:
            return Response(
                resp.content,
                mimetype="application/x-mpegurl",
                headers={"Content-Disposition": "attachment;filename=iptv_trial.m3u"}
            )
    except Exception:
        pass
    
    # Fallback: redirecionar directamente
    from flask import redirect
    return redirect(m3u_url)


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint para serviços como Render / UptimeRobot."""
    return jsonify({
        "status": "online",
        "service": "IPTV Trial Generator Web",
        "gmail_configured": bool(PERSONAL_GMAIL and GMAIL_APP_PASSWORD),
        "diagnostics": "degraded" if history_initialization_error or (history and history.storage_error) else "ready"
    })


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f"  ⚡ IPTV Access Portal em execução:")
    print(f"  📱 Abre no teu browser: http://localhost:{port}")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)

