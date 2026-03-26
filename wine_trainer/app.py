"""
app.py
──────
Flask web application for the Wine Training Generator.

Routes:
  GET  /            → Upload form
  POST /process     → Run pipeline, return ZIP of 4 PDFs
  GET  /health      → Simple health check

Run locally:
  python app.py

Deploy to production (Gunicorn):
  gunicorn app:app --workers 2 --timeout 300
"""

import os
import uuid
import shutil
import logging
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime

from flask import (
    Flask, request, render_template,
    send_file, jsonify, redirect, url_for, flash
)
from dotenv import load_dotenv

from pipeline.adobe_extractor import extract_wine_list
from pipeline.claude_analyzer import analyze_wine_list
from pipeline.doc_generator import generate_all_pdfs

# ─── Bootstrap ───────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB hard limit

# ─── Startup diagnostics ──────────────────────────────────────────────────────
logger.info("=== SavvySipping startup ===")
logger.info(f"ANTHROPIC_API_KEY set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
logger.info(f"ADOBE_CLIENT_ID set:   {bool(os.environ.get('ADOBE_CLIENT_ID'))}")
logger.info(f"ADOBE_CLIENT_SECRET set: {bool(os.environ.get('ADOBE_CLIENT_SECRET'))}")
logger.info(f"FLASK_SECRET_KEY set:  {bool(os.environ.get('FLASK_SECRET_KEY'))}")
logger.info(f"PORT: {os.environ.get('PORT', '(not set, using 5001)')}")

# ─── Config ───────────────────────────────────────────────────────────────────
UPLOAD_FOLDER    = Path("uploads")
GENERATED_FOLDER = Path("generated")
ALLOWED_EXT      = {"pdf"}
MAX_FILE_MB      = 50

UPLOAD_FOLDER.mkdir(exist_ok=True)
GENERATED_FOLDER.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/process", methods=["POST"])
def process():
    """
    Main pipeline endpoint.
    Accepts multipart form with:
      - wine_list       : PDF file
      - restaurant_name : str
      - cuisine_style   : str
      - staff_description: str

    Returns a ZIP file containing the 4 training PDFs.
    """
    # ── Validate form inputs ──────────────────────────────────────────────
    restaurant_name   = request.form.get("restaurant_name", "").strip()
    cuisine_style     = request.form.get("cuisine_style", "").strip()
    staff_description = request.form.get("staff_description", "").strip()
    wine_pdf          = request.files.get("wine_list")

    if not restaurant_name:
        return _error("Please enter the restaurant name.", 400)
    if not wine_pdf or wine_pdf.filename == "":
        return _error("Please upload a wine list PDF.", 400)
    if not _allowed_file(wine_pdf.filename):
        return _error("Only PDF files are accepted.", 400)

    # ── Save uploaded PDF ─────────────────────────────────────────────────
    job_id   = uuid.uuid4().hex[:10]
    job_dir  = GENERATED_FOLDER / job_id
    job_dir.mkdir(parents=True)

    pdf_path = UPLOAD_FOLDER / f"{job_id}_wine_list.pdf"
    wine_pdf.save(str(pdf_path))
    logger.info(f"[{job_id}] Saved PDF: {pdf_path.name}  ({pdf_path.stat().st_size // 1024} KB)")

    try:
        # ── Step 1: Adobe PDF Extract ──────────────────────────────────────
        logger.info(f"[{job_id}] Step 1/3 – Adobe PDF extraction...")
        credentials_path = os.environ.get("ADOBE_CREDENTIALS_PATH", "pdfservices-api-credentials.json")
        wine_list_text = extract_wine_list(str(pdf_path), credentials_path)
        logger.info(f"[{job_id}] Extracted {len(wine_list_text):,} characters.")

        # ── Step 2: Claude Analysis ────────────────────────────────────────
        logger.info(f"[{job_id}] Step 2/3 – Claude analysis (3 API calls)...")
        content = analyze_wine_list(
            wine_list_text   = wine_list_text,
            restaurant_name  = restaurant_name,
            cuisine_style    = cuisine_style or "Contemporary",
            staff_description= staff_description or "Mixed experience levels",
        )

        # ── Step 3: Generate 4 PDFs ────────────────────────────────────────
        logger.info(f"[{job_id}] Step 3/3 – Generating PDFs...")
        pdf_paths = generate_all_pdfs(
            content         = content,
            restaurant_name = restaurant_name,
            output_dir      = str(job_dir),
        )

        # ── Bundle into ZIP ────────────────────────────────────────────────
        zip_path = GENERATED_FOLDER / f"{job_id}_training_pack.zip"
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for doc_type, path in pdf_paths.items():
                zf.write(path, arcname=Path(path).name)

        logger.info(f"[{job_id}] Done. ZIP: {zip_path.name}")

        # ── Return ZIP to browser ─────────────────────────────────────────
        safe = _safe_name(restaurant_name)
        download_name = f"{safe}_Wine_Training_Pack.zip"

        return send_file(
            str(zip_path),
            as_attachment=True,
            download_name=download_name,
            mimetype="application/zip",
        )

    except Exception as e:
        logger.exception(f"[{job_id}] Pipeline failed: {e}")
        return _error(
            f"Something went wrong during processing: {str(e)}\n"
            "Please check your API credentials and try again.",
            500,
        )

    finally:
        # Cleanup uploaded PDF (keep generated ZIP for audit trail)
        if pdf_path.exists():
            pdf_path.unlink()


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _safe_name(name: str) -> str:
    import re
    return re.sub(r"[^\w\-]", "_", name).strip("_")


def _error(message: str, status: int = 400):
    """Return JSON error for API clients, HTML for browsers."""
    if request.accept_mimetypes.accept_json:
        return jsonify({"error": message}), status
    return render_template("upload.html", error=message), status


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=debug)
