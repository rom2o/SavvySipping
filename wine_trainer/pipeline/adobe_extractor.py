"""
adobe_extractor.py
──────────────────
Extracts text from a wine-list PDF using the Adobe PDF Services REST API
with OAuth 2.0 credentials (client_id + client_secret).

This replaces the old SDK-based approach which required a private key.
"""

import os
import json
import time
import zipfile
import tempfile
import logging
import requests

logger = logging.getLogger(__name__)

# Adobe API endpoints
TOKEN_URL    = "https://ims-na1.adobelogin.com/ims/token/v3"
API_BASE     = "https://pdf-services.adobe.io"


def extract_wine_list(pdf_path: str, credentials_path: str) -> str:
    """
    Extract all text from a wine-list PDF using Adobe PDF Services REST API.

    Args:
        pdf_path:         Absolute path to the uploaded PDF.
        credentials_path: Path to pdfservices-api-credentials.json.

    Returns:
        Clean text string of the entire wine list.
    """
    # ── 1. Load credentials ───────────────────────────────────────────────
    # Priority: individual env vars → JSON env var → credentials file
    client_id     = os.environ.get("ADOBE_CLIENT_ID")
    client_secret = os.environ.get("ADOBE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raw_json = os.environ.get("ADOBE_CREDENTIALS_JSON")
        if raw_json:
            try:
                creds = _load_credentials_from_dict(json.loads(raw_json))
                client_id     = creds.get("client_id") or creds.get("CLIENT_ID")
                client_secret = creds.get("client_secret") or creds.get("CLIENT_SECRET")
            except json.JSONDecodeError as e:
                raise ValueError(f"ADOBE_CREDENTIALS_JSON is not valid JSON: {e}")

    if not client_id or not client_secret:
        try:
            creds = _load_credentials(credentials_path)
            client_id     = creds.get("client_id") or creds.get("CLIENT_ID")
            client_secret = creds.get("client_secret") or creds.get("CLIENT_SECRET")
        except FileNotFoundError:
            pass

    if not client_id or not client_secret:
        raise ValueError(
            "Adobe credentials not found. In Railway, set either:\n"
            "  ADOBE_CLIENT_ID + ADOBE_CLIENT_SECRET  (two separate vars)\n"
            "  ADOBE_CREDENTIALS_JSON  (full contents of pdfservices-api-credentials.json)"
        )

    # ── 2. Get OAuth access token ─────────────────────────────────────────
    logger.info("Getting Adobe OAuth token...")
    token = _get_access_token(client_id, client_secret)

    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key":     client_id,
    }

    # ── 3. Upload PDF to Adobe ────────────────────────────────────────────
    logger.info("Uploading PDF to Adobe...")
    asset_id, upload_uri = _create_asset(headers, pdf_path)
    _upload_file(upload_uri, pdf_path)
    logger.info(f"PDF uploaded. Asset ID: {asset_id}")

    # ── 4. Start extraction job ───────────────────────────────────────────
    logger.info("Starting Adobe extraction job...")
    job_url = _start_extract_job(headers, asset_id)

    # ── 5. Poll until done ────────────────────────────────────────────────
    logger.info("Waiting for extraction to complete...")
    result_url = _poll_job(headers, job_url)

    # ── 6. Download result ZIP and parse ─────────────────────────────────
    logger.info("Downloading and parsing result...")
    text = _download_and_parse(result_url)
    logger.info(f"Extracted {len(text):,} characters.")
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_credentials_from_dict(data: dict) -> dict:
    """Resolve nested or flat credentials dict."""
    if "client_id" in data or "CLIENT_ID" in data:
        return data
    for key in ("client_credentials", "credentials", "oauth"):
        if key in data and isinstance(data[key], dict):
            return data[key]
    return data


def _load_credentials(path: str) -> dict:
    """Load credentials JSON — handles nested or flat formats."""
    with open(path, "r") as f:
        data = json.load(f)
    return _load_credentials_from_dict(data)


def _get_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(TOKEN_URL, data={
        "client_id":     client_id,
        "client_secret": client_secret,
        "grant_type":    "client_credentials",
        "scope":         "openid,AdobeID,DCAPI",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def _create_asset(headers: dict, pdf_path: str) -> tuple:
    """Create an upload asset slot. Returns (asset_id, upload_uri)."""
    resp = requests.post(
        f"{API_BASE}/assets",
        headers={**headers, "Content-Type": "application/json"},
        json={"mediaType": "application/pdf"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["assetID"], data["uploadUri"]


def _upload_file(upload_uri: str, pdf_path: str) -> None:
    """PUT the PDF bytes to the pre-signed Adobe upload URL."""
    with open(pdf_path, "rb") as f:
        resp = requests.put(
            upload_uri,
            data=f,
            headers={"Content-Type": "application/pdf"},
        )
    resp.raise_for_status()


def _start_extract_job(headers: dict, asset_id: str) -> str:
    """Start a PDF Extract job. Returns the job polling URL."""
    resp = requests.post(
        f"{API_BASE}/operation/extractpdf",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "assetID": asset_id,
            "elementsToExtract": ["text"],
        },
    )
    resp.raise_for_status()
    # Job URL is in the Location header
    return resp.headers["Location"]


def _poll_job(headers: dict, job_url: str, timeout: int = 120) -> str:
    start = time.time()
    while True:
        resp = requests.get(job_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        logger.info(f"  Adobe response keys: {list(data.keys())}")

        if status == "done":
            logger.info(f"  Full done response: {json.dumps(data, indent=2)}")
            # Try multiple possible response structures
            if "content" in data and "downloadUri" in data["content"]:
                return data["content"]["downloadUri"]
            elif "resource" in data and "downloadUri" in data["resource"]:
                return data["resource"]["downloadUri"]
            elif "outputs" in data and len(data["outputs"]) > 0:
                return data["outputs"][0]["downloadUri"]
            else:
                raise RuntimeError(f"Cannot find downloadUri in response: {data}")
        elif status == "failed":
            raise RuntimeError(f"Adobe extraction failed: {data.get('error')}")
        elif time.time() - start > timeout:
            raise TimeoutError("Adobe extraction timed out.")

        time.sleep(3)


def _download_and_parse(result_url: str) -> str:
    """Download Adobe's structuredData.json directly and parse it."""
    resp = requests.get(result_url)
    resp.raise_for_status()
    data = resp.json()
    return _parse_adobe_json(data)


def _parse_adobe_json(data: dict) -> str:
    """Parse Adobe structuredData JSON → clean ordered text string."""
    elements = data.get("elements", [])
    parts = []

    for el in elements:
        text = el.get("Text", "").strip()
        path = el.get("Path", "")

        if not text:
            continue

        if "H1" in path or "Title" in path:
            parts.append(f"\n## {text}")
        elif "H2" in path or "H3" in path:
            parts.append(f"\n### {text}")
        else:
            parts.append(text)

    return "\n".join(parts)
