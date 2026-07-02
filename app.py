"""TTB Label Verifier — FastAPI server.

Run:  uvicorn app:app --reload
Then open http://localhost:8000
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import extraction
import ocr_extraction
from compare import verify

app = FastAPI(title="TTB Label Verifier", version="0.2.0")


def active_engine() -> str:
    """'claude' when an API key is available, 'ocr' otherwise.
    Override with VERIFIER_ENGINE=claude|ocr."""
    forced = os.environ.get("VERIFIER_ENGINE", "").lower()
    if forced in ("claude", "ocr"):
        return forced
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "ocr"


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

APPLICATION_FIELDS = ("brand_name", "class_type", "alcohol_content",
                      "net_contents")


@app.post("/api/verify")
def verify_label(image: UploadFile = File(...), application: str = Form(...)):
    """Verify one label image against one application's data.

    `application` is a JSON string: {"brand_name": ..., "class_type": ...,
    "alcohol_content": ..., "net_contents": ...}. The government warning is
    always checked against the statutory text — it is never user input.

    Sync endpoint on purpose: FastAPI runs it in a threadpool, so batch-mode
    concurrent requests from the browser overlap their model calls.
    """
    t0 = time.perf_counter()

    try:
        app_fields = json.loads(application)
        if not isinstance(app_fields, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "`application` must be a JSON object.")
    app_fields = {k: app_fields.get(k) for k in APPLICATION_FIELDS}

    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type "
                                 f"'{image.content_type}'. Use JPEG/PNG/WebP.")
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Image larger than 15 MB.")
    if not data:
        raise HTTPException(400, "Empty image upload.")

    engine = active_engine()
    extract = (extraction.extract_label_fields if engine == "claude"
               else ocr_extraction.extract_label_fields)
    try:
        extracted = extract(data)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:  # API/network failures → readable message
        raise HTTPException(502, f"Label extraction failed: {e}")

    report = verify(app_fields, extracted)
    report["engine"] = engine
    report["extracted"] = extracted
    report["image_quality_issues"] = extracted.get("image_quality_issues") or []
    report["elapsed_seconds"] = round(time.perf_counter() - t0, 2)
    report["filename"] = image.filename
    return JSONResponse(report)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "engine": active_engine(),
        "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "tesseract_available": ocr_extraction.tesseract_available(),
    }


# Serve the UI last so /api/* wins routing.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static",
                           html=True), name="static")
