"""Label reading via Claude vision.

The model's only job is transcription: read the label exactly as printed and
return structured JSON. All pass/fail logic lives in compare.py.
"""

from __future__ import annotations

import base64
import io
import json
import os

import anthropic
from PIL import Image

# Swappable via env var — e.g. drop to a smaller/faster model, or point the
# base URL at an internal gateway on a locked-down network.
MODEL = os.environ.get("VERIFIER_MODEL", "claude-sonnet-5")
MAX_DIMENSION = 1568  # Claude vision's effective max; larger just adds latency

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it before starting "
                "the server: export ANTHROPIC_API_KEY=sk-ant-...")
        _client = anthropic.Anthropic()
    return _client


def prepare_image(data: bytes) -> tuple[str, str]:
    """Downscale + re-encode so we never upload a 12 MP phone photo.
    Returns (base64_data, media_type)."""
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


EXTRACTION_PROMPT = """\
You are reading a photograph or scan of an alcohol beverage label for a \
regulatory compliance check.

Transcribe what is printed on the label EXACTLY as it appears — preserve \
capitalization, punctuation, and spelling, including any errors. Do not \
correct, normalize, or complete anything.

Return ONLY a JSON object with this shape (no markdown, no commentary):
{
  "brand_name": string|null,          // the brand name as printed
  "class_type": string|null,          // e.g. "Kentucky Straight Bourbon Whiskey"
  "alcohol_content": string|null,     // e.g. "45% Alc./Vol. (90 Proof)"
  "net_contents": string|null,        // e.g. "750 mL"
  "producer": string|null,            // bottler/producer name & address if shown
  "country_of_origin": string|null,   // if shown
  "government_warning": {
    "text": string|null,              // the FULL warning verbatim, exact capitalization
    "prefix_bold": true|false|null    // is 'GOVERNMENT WARNING:' visibly bolder
                                      // than the body text? null if unsure
  },
  "image_quality_issues": [string]    // e.g. "glare over warning text",
                                      // "photographed at an angle", "blurry";
                                      // empty list if the image is clean
}

Use null for anything not visible or not present. If part of the label is \
unreadable, transcribe what you can and report the problem in \
image_quality_issues."""


def extract_label_fields(image_bytes: bytes) -> dict:
    """One round trip to the model per label. Raises RuntimeError with a
    user-facing message on failure."""
    b64, media_type = prepare_image(image_bytes)
    client = _get_client()

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type,
                            "data": b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )

    text = "".join(b.text for b in response.content if b.type == "text").strip()
    # Tolerate accidental code fences.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.index("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("Model did not return JSON. Raw response: "
                           + text[:200])
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse extraction JSON: {e}") from e
