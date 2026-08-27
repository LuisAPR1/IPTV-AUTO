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
from typing import Dict, Any
from flask import Flask, render_template, jsonify, request, Response

# Assegurar que o directório actual está no path de importação
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import PERSONAL_GMAIL, GMAIL_APP_PASSWORD, ERROR_LOG_FILE
from email_service import TempMailService
from scraper import IPTVScraper

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=os.path.join(current_dir, "templates"))

# Estado dos Jobs em memória
jobs: Dict[str, Dict[str, Any]] = {}
LATEST_TRIAL_FILE = os.path.join(current_dir, "latest_trial.json")


def save_latest_trial(creds: Dict[str, str]):
    """Guarda as últimas credenciais geradas em ficheiro para consulta rápida."""
    try:
        with open(LATEST_TRIAL_FILE, "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erro ao guardar último trial: {e}")


def load_latest_trial() -> Dict[str, str]:
    """Carrega as últimas credenciais geradas."""
    if os.path.exists(LATEST_TRIAL_FILE):
        try:
            with open(LATEST_TRIAL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def run_scraper_task(job_id: str):
    """Executa a automação IPTV em segundo plano."""
    job = jobs[job_id]

    def on_progress(step_index: int, message: str):
        percent = min(100, int((step_index / 8.0) * 100))
        job["step"] = step_index
        job["percent"] = percent
        job["message"] = message
        job["logs"].append(f"[Passo {step_index}] {message}")

    try:
        on_progress(1, "Inicializando serviço de email e parâmetros...")
        
        email_service = TempMailService(
            personal_gmail=PERSONAL_GMAIL,
            app_password=GMAIL_APP_PASSWORD
        )

        scraper = IPTVScraper(
            email_service=email_service,
            progress_callback=on_progress
        )

        # Executar automação
        credentials = scraper.run_automation()

        if credentials and credentials.get("username") and credentials.get("password"):
            job["status"] = "completed"
            job["percent"] = 100
            job["message"] = "Trial de 48h gerado com sucesso!"
            job["credentials"] = credentials
            save_latest_trial(credentials)
            logger.info(f"Job {job_id} concluído com sucesso.")
        else:
            job["status"] = "error"
            job["error"] = "Não foi possível extrair todas as credenciais. Consulta erros_automacao.log para mais detalhes."
            logger.warning(f"Job {job_id} falhou na extração de credenciais.")

    except Exception as e:
        logger.error(f"Job {job_id} falhou com erro: {e}")
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        try:
            email_service.cleanup()
        except Exception:
            pass


@app.route("/")
def index():
    """Página principal (Mobile-First Web App)."""
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def generate_trial():
    """Inicia um novo processo de geração de trial IPTV."""
    # Verificar se já existe algum job a correr
    for j_id, j_data in jobs.items():
        if j_data.get("status") == "running":
            return jsonify({
                "success": True,
                "job_id": j_id,
                "message": "Já existe uma automação em curso. A acompanhar progresso..."
            })

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "status": "running",
        "step": 1,
        "percent": 5,
        "message": "Iniciando sessão de automação...",
        "logs": [],
        "credentials": None,
        "error": None
    }

    # Iniciar worker thread
    thread = threading.Thread(target=run_scraper_task, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "Automação iniciada."
    })


@app.route("/api/progress/<job_id>", methods=["GET"])
def get_progress(job_id: str):
    """Retorna o estado e progresso actual de um job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "message": "Job não encontrado"}), 404
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
        "gmail_configured": bool(PERSONAL_GMAIL and GMAIL_APP_PASSWORD)
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f"  ⚡ IPTV Trial Web App em execução:")
    print(f"  📱 Abre no teu browser: http://localhost:{port}")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)
