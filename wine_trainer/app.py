"""
app.py
──────
Flask web application for the Wine Training Generator.

Routes:
  GET  /            → Upload form
  POST /process     → Start background pipeline, return confirmation page
  GET  /health      → Simple health check

Deploy to production (Gunicorn):
  gunicorn app:app --workers 1 --timeout 1020
"""

import os
import re
import uuid
import base64
import shutil
import logging
import zipfile
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, request, render_template, jsonify
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

# ─── Startup diagnostics ─────────────────────────────────────────────────────
logger.info("=== SavvySipping startup ===")
logger.info(f"ANTHROPIC_API_KEY set:   {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
logger.info(f"ADOBE_CLIENT_ID set:     {bool(os.environ.get('ADOBE_CLIENT_ID'))}")
logger.info(f"ADOBE_CLIENT_SECRET set: {bool(os.environ.get('ADOBE_CLIENT_SECRET'))}")
logger.info(f"SENDGRID_API_KEY set:    {bool(os.environ.get('SENDGRID_API_KEY'))}")
logger.info(f"FROM_EMAIL:              {os.environ.get('FROM_EMAIL', '(not set)')}")
logger.info(f"PORT: {os.environ.get('PORT', '(not set, using 5001)')}")

# ─── Config ──────────────────────────────────────────────────────────────────
UPLOAD_FOLDER    = Path("uploads")
GENERATED_FOLDER = Path("generated")
ALLOWED_EXT      = {"pdf"}

UPLOAD_FOLDER.mkdir(exist_ok=True)
GENERATED_FOLDER.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Background pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline(job_id, pdf_path, job_dir, restaurant_name,
                  cuisine_style, staff_description, to_email):
    """Run the full pipeline in a background thread and email the result."""
    zip_path = None
    try:
        credentials_path = os.environ.get(
            "ADOBE_CREDENTIALS_PATH", "pdfservices-api-credentials.json"
        )

        logger.info(f"[{job_id}] Step 1/3 – Adobe PDF extraction...")
        wine_list_text = extract_wine_list(str(pdf_path), credentials_path)
        logger.info(f"[{job_id}] Extracted {len(wine_list_text):,} characters.")

        logger.info(f"[{job_id}] Step 2/3 – Claude analysis...")
        content = analyze_wine_list(
            wine_list_text    = wine_list_text,
            restaurant_name   = restaurant_name,
            cuisine_style     = cuisine_style or "Contemporary",
            staff_description = staff_description or "Mixed experience levels",
        )

        logger.info(f"[{job_id}] Step 3/3 – Generating PDFs...")
        pdf_paths = generate_all_pdfs(
            content         = content,
            restaurant_name = restaurant_name,
            output_dir      = str(job_dir),
        )

        zip_path = GENERATED_FOLDER / f"{job_id}_training_pack.zip"
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for _, path in pdf_paths.items():
                zf.write(path, arcname=Path(path).name)

        logger.info(f"[{job_id}] ZIP ready — sending email to {to_email}...")
        _send_email(to_email, restaurant_name, zip_path)
        logger.info(f"[{job_id}] Email sent. Done.")

    except Exception as e:
        logger.exception(f"[{job_id}] Pipeline failed: {e}")
        _send_failure_email(to_email, restaurant_name)

    finally:
        if Path(pdf_path).exists():
            Path(pdf_path).unlink()
        if job_dir.exists():
            shutil.rmtree(str(job_dir), ignore_errors=True)
        if zip_path and Path(zip_path).exists():
            Path(zip_path).unlink()


# ─────────────────────────────────────────────────────────────────────────────
# Email helpers
# ─────────────────────────────────────────────────────────────────────────────

def _send_email(to_email, restaurant_name, zip_path):
    import sendgrid
    from sendgrid.helpers.mail import (
        Mail, Attachment, FileContent, FileName, FileType, Disposition
    )

    sg_key  = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("FROM_EMAIL", "noreply@savvysipping.com")

    if not sg_key:
        logger.error("SENDGRID_API_KEY not set — cannot send email.")
        return

    with open(zip_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    safe = re.sub(r"[^\w\-]", "_", restaurant_name).strip("_")

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=f"Your Wine Training Pack — {restaurant_name}",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;">
          <h2 style="color:#722F37;">🍷 Your Wine Training Pack is Ready!</h2>
          <p>Hi there,</p>
          <p>Your wine training pack for <strong>{restaurant_name}</strong>
             is attached to this email.</p>
          <p>The ZIP contains 4 documents:</p>
          <ul>
            <li>📘 Training Guide</li>
            <li>📝 Knowledge Test</li>
            <li>📋 Cheat Sheet</li>
            <li>🔑 Answer Key</li>
          </ul>
          <p style="color:#888;font-size:12px;">Powered by SavvySipping</p>
        </div>
        """,
    )

    attachment = Attachment(
        FileContent(encoded),
        FileName(f"{safe}_Wine_Training_Pack.zip"),
        FileType("application/zip"),
        Disposition("attachment"),
    )
    message.attachment = attachment

    sg = sendgrid.SendGridAPIClient(api_key=sg_key)
    sg.send(message)


def _send_failure_email(to_email, restaurant_name):
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg_key     = os.environ.get("SENDGRID_API_KEY")
        from_email = os.environ.get("FROM_EMAIL", "noreply@savvysipping.com")
        if not sg_key:
            return

        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=f"Issue with your Wine Training Pack — {restaurant_name}",
            html_content=f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto;">
              <h2 style="color:#722F37;">Something went wrong</h2>
              <p>We ran into an issue generating the training pack for
                 <strong>{restaurant_name}</strong>.</p>
              <p>Please try again or contact support.</p>
              <p style="color:#888;font-size:12px;">Powered by SavvySipping</p>
            </div>
            """,
        )
        sg = sendgrid.SendGridAPIClient(api_key=sg_key)
        sg.send(message)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/process", methods=["POST"])
def process():
    restaurant_name   = request.form.get("restaurant_name", "").strip()
    cuisine_style     = request.form.get("cuisine_style", "").strip()
    staff_description = request.form.get("staff_description", "").strip()
    email             = request.form.get("email", "").strip()
    wine_pdf          = request.files.get("wine_list")

    if not restaurant_name:
        return _error("Please enter the restaurant name.", 400)
    if not email or "@" not in email:
        return _error("Please enter a valid email address.", 400)
    if not wine_pdf or wine_pdf.filename == "":
        return _error("Please upload a wine list PDF.", 400)
    if not _allowed_file(wine_pdf.filename):
        return _error("Only PDF files are accepted.", 400)

    job_id  = uuid.uuid4().hex[:10]
    job_dir = GENERATED_FOLDER / job_id
    job_dir.mkdir(parents=True)

    pdf_path = UPLOAD_FOLDER / f"{job_id}_wine_list.pdf"
    wine_pdf.save(str(pdf_path))
    logger.info(
        f"[{job_id}] Saved PDF: {pdf_path.name}  "
        f"({pdf_path.stat().st_size // 1024} KB) → {email}"
    )

    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id, pdf_path, job_dir, restaurant_name,
              cuisine_style, staff_description, email),
        daemon=True,
    )
    thread.start()

    return render_template(
        "processing.html",
        email=email,
        restaurant_name=restaurant_name,
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _error(message: str, status: int = 400):
    if request.accept_mimetypes.accept_json:
        return jsonify({"error": message}), status
    return render_template("upload.html", error=message), status


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    port  = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=debug)
