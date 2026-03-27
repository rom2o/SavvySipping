"""
app.py
──────
Flask web application for SavvySipping Wine Training Generator.

Routes (production — token-gated):
  POST /webhook            → Stripe webhook: creates token, emails upload link
  GET  /upload/<token>     → Upload form (token-validated)
  POST /process/<token>    → Run pipeline, mark token used, return ZIP

Routes (kept for local testing):
  GET  /                   → Upload form (no token)
  POST /process            → Async pipeline, emails ZIP via SendGrid
  GET  /health             → Health check
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

import stripe
from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv

from pipeline.adobe_extractor import extract_wine_list
from pipeline.claude_analyzer import analyze_wine_list
from pipeline.doc_generator import generate_all_pdfs
from tokens import init_db, create_token, validate_token, mark_used

# ─── Bootstrap ───────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-prod")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

# ─── Startup ─────────────────────────────────────────────────────────────────
init_db()

logger.info("=== SavvySipping startup ===")
logger.info(f"ANTHROPIC_API_KEY set:    {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
logger.info(f"ADOBE_CLIENT_ID set:      {bool(os.environ.get('ADOBE_CLIENT_ID'))}")
logger.info(f"ADOBE_CLIENT_SECRET set:  {bool(os.environ.get('ADOBE_CLIENT_SECRET'))}")
logger.info(f"SENDGRID_API_KEY set:     {bool(os.environ.get('SENDGRID_API_KEY'))}")
logger.info(f"STRIPE_WEBHOOK_SECRET set:{bool(os.environ.get('STRIPE_WEBHOOK_SECRET'))}")
logger.info(f"PORT: {os.environ.get('PORT', '(not set, using 5001)')}")

# ─── Config ──────────────────────────────────────────────────────────────────
UPLOAD_FOLDER    = Path("uploads")
GENERATED_FOLDER = Path("generated")
ALLOWED_EXT      = {"pdf"}
BASE_URL         = os.environ.get(
    "BASE_URL", "https://savvysipping-production.up.railway.app"
).rstrip("/")

UPLOAD_FOLDER.mkdir(exist_ok=True)
GENERATED_FOLDER.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Stripe webhook
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    secret     = os.environ.get("STRIPE_WEBHOOK_SECRET")

    if secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.warning(f"Stripe signature error: {e}")
            return jsonify({"error": "Invalid signature"}), 400
    else:
        logger.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature check")
        import json
        event = json.loads(payload)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        try:
            email = session.customer_details.email
        except AttributeError:
            email = None
        if not email:
            email = getattr(session, "customer_email", None)

        if email:
            token     = create_token(email)
            upload_url = f"{BASE_URL}/upload/{token}"
            logger.info(f"Stripe payment from {email} — token created")
            _send_token_email(email, upload_url)
        else:
            logger.warning("checkout.session.completed has no customer email")

    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────────────────────────────────────
# Token-gated upload + process
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/upload/<token>", methods=["GET"])
def upload(token):
    row = validate_token(token)
    if not row:
        return render_template("invalid_token.html"), 403
    return render_template("upload.html", token=token)


@app.route("/process/<token>", methods=["POST"])
def process_with_token(token):
    row = validate_token(token)
    if not row:
        return render_template("invalid_token.html"), 403

    restaurant_name   = request.form.get("restaurant_name", "").strip()
    cuisine_style     = request.form.get("cuisine_style", "").strip()
    staff_description = request.form.get("staff_description", "").strip()
    wine_pdf          = request.files.get("wine_list")

    if not restaurant_name:
        return _error("Please enter the restaurant name.", 400, token=token)
    if not wine_pdf or wine_pdf.filename == "":
        return _error("Please upload a wine list PDF.", 400, token=token)
    if not _allowed_file(wine_pdf.filename):
        return _error("Only PDF files are accepted.", 400, token=token)

    job_id  = uuid.uuid4().hex[:10]
    job_dir = GENERATED_FOLDER / job_id
    job_dir.mkdir(parents=True)

    pdf_path = UPLOAD_FOLDER / f"{job_id}_wine_list.pdf"
    wine_pdf.save(str(pdf_path))
    logger.info(
        f"[{job_id}] Token job — PDF saved ({pdf_path.stat().st_size // 1024} KB) → {row['email']}"
    )

    thread = threading.Thread(
        target=_run_pipeline_and_email,
        args=(job_id, pdf_path, job_dir, restaurant_name,
              cuisine_style, staff_description, row["email"], token),
        daemon=True,
    )
    thread.start()

    return render_template(
        "processing.html",
        email=row["email"],
        restaurant_name=restaurant_name,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Local / open routes (no token required)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/process", methods=["POST"])
def process():
    """Async pipeline — returns confirmation page, emails ZIP when done."""
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
        f"[{job_id}] Saved PDF: {pdf_path.name} "
        f"({pdf_path.stat().st_size // 1024} KB) → {email}"
    )

    thread = threading.Thread(
        target=_run_pipeline_and_email,
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
# Background pipeline (async /process route)
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline_and_email(job_id, pdf_path, job_dir, restaurant_name,
                             cuisine_style, staff_description, to_email, token=None):
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

        if token:
            mark_used(token)
            logger.info(f"[{job_id}] Token consumed.")
        logger.info(f"[{job_id}] ZIP ready — emailing {to_email}...")
        _send_zip_email(to_email, restaurant_name, zip_path)
        logger.info(f"[{job_id}] Email sent.")

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

def _send_token_email(to_email: str, upload_url: str) -> None:
    """Send the one-time upload link after a successful Stripe payment."""
    sg_key = os.environ.get("SENDGRID_API_KEY")
    if not sg_key:
        logger.info(f"[NO SENDGRID] Upload link for {to_email}: {upload_url}")
        return

    import sendgrid
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email="noreply@savvysipping.com",
        to_emails=to_email,
        subject="Your SavvySipping upload link",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;">
          <h2 style="color:#722F37;">🍷 You're ready to generate!</h2>
          <p>Thank you for your purchase. Click the button below to upload
             your wine list and generate your training pack.</p>
          <p style="text-align:center;margin:2rem 0;">
            <a href="{upload_url}"
               style="background:#722F37;color:#fff;padding:0.75rem 2rem;
                      border-radius:6px;text-decoration:none;font-weight:600;">
              Upload Your Wine List
            </a>
          </p>
          <p>If the button doesn't work, copy and paste this link into your browser:</p>
          <p style="word-break:break-all;">
            <a href="{upload_url}">{upload_url}</a>
          </p>
          <p style="color:#888;font-size:12px;">
            This link is valid for 72 hours and can only be used once.
          </p>
          <p style="color:#888;font-size:12px;">Powered by SavvySipping</p>
        </div>
        """,
    )
    sg = sendgrid.SendGridAPIClient(api_key=sg_key)
    sg.send(message)
    logger.info(f"Token email sent to {to_email}")


def _send_zip_email(to_email: str, restaurant_name: str, zip_path: Path) -> None:
    """Send the finished ZIP as an email attachment."""
    sg_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("FROM_EMAIL", "noreply@savvysipping.com")

    if not sg_key:
        logger.error("SENDGRID_API_KEY not set — cannot send ZIP email.")
        return

    import sendgrid
    from sendgrid.helpers.mail import (
        Mail, Attachment, FileContent, FileName, FileType, Disposition,
    )

    with open(zip_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    safe = _safe_name(restaurant_name)
    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=f"Your Wine Training Pack — {restaurant_name}",
        html_content=f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;">
          <h2 style="color:#722F37;">🍷 Your Wine Training Pack is Ready!</h2>
          <p>Your training pack for <strong>{restaurant_name}</strong>
             is attached to this email.</p>
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
    message.attachment = Attachment(
        FileContent(encoded),
        FileName(f"{safe}_Wine_Training_Pack.zip"),
        FileType("application/zip"),
        Disposition("attachment"),
    )
    sg = sendgrid.SendGridAPIClient(api_key=sg_key)
    sg.send(message)


def _send_failure_email(to_email: str, restaurant_name: str) -> None:
    try:
        sg_key = os.environ.get("SENDGRID_API_KEY")
        from_email = os.environ.get("FROM_EMAIL", "noreply@savvysipping.com")
        if not sg_key:
            return
        import sendgrid
        from sendgrid.helpers.mail import Mail
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=f"Issue with your Wine Training Pack — {restaurant_name}",
            html_content=f"""
            <div style="font-family:sans-serif;max-width:600px;margin:auto;">
              <h2 style="color:#722F37;">Something went wrong</h2>
              <p>We ran into an issue generating the training pack for
                 <strong>{restaurant_name}</strong>. Please try again.</p>
            </div>
            """,
        )
        sg = sendgrid.SendGridAPIClient(api_key=sg_key)
        sg.send(message)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w\-]", "_", name).strip("_")


def _error(message: str, status: int = 400, token: str = None):
    if request.accept_mimetypes.accept_json:
        return jsonify({"error": message}), status
    return render_template("upload.html", error=message, token=token), status


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    port  = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=debug)
