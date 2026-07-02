"""Label reading via local OCR (Tesseract) — free, offline fallback.

Same output contract as extraction.py, so compare.py doesn't care which
engine produced the transcription. Used automatically when no
ANTHROPIC_API_KEY is configured (or when VERIFIER_ENGINE=ocr).

Trade-off vs Claude vision: works well on clean, straight-on label images
(like scans or the bundled test labels); struggles with glare, angles, and
stylized fonts. Field identification is heuristic — OCR gives text and
geometry, not meaning.
"""

from __future__ import annotations

import io
import re
import shutil
import statistics
import sys
from pathlib import Path

from PIL import Image

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

# Windows installers usually don't add tesseract.exe to PATH.
_WIN_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def tesseract_available() -> bool:
    if pytesseract is None:
        return False
    if shutil.which("tesseract"):
        return True
    if sys.platform == "win32":
        for p in _WIN_CANDIDATES:
            if Path(p).exists():
                pytesseract.pytesseract.tesseract_cmd = p
                return True
    return False


_ABV_RE = re.compile(r"\d+(?:\.\d+)?\s*%|(?<![\d.])\d+(?:\.\d+)?\s*proof", re.I)
_VOL_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:m\s?l|fl\.?\s*oz\.?|litre?s?|liters?|cl)\b", re.I)
_WARN_RE = re.compile(r"government\s+warning", re.I)
_PRODUCER_RE = re.compile(
    r"(bottled|produced|distilled|brewed|imported)\s+(&\s+\w+\s+)?by", re.I)
_ORIGIN_RE = re.compile(r"product\s+of\s+([A-Za-z .]+)", re.I)
_DECOR_RE = re.compile(r"^[\W_]+$")  # ornaments like "* * *"


def _ocr_lines(img: Image.Image) -> tuple[list[dict], list[float]]:
    """Run Tesseract and reconstruct physical lines with mean word height
    and confidence."""
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    lines: dict[tuple, dict] = {}
    confs: list[float] = []
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word:
            continue
        # ornaments/borders often OCR as runs of one letter ("HHHHHHH") — drop
        if (len(word) >= 3 and word.isalpha()
                and max(word.lower().count(c) for c in set(word.lower())) / len(word) > 0.7):
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        ln = lines.setdefault(key, {"words": [], "heights": [], "top": data["top"][i]})
        ln["words"].append(word)
        ln["heights"].append(data["height"][i])
    out = []
    for key in sorted(lines):
        ln = lines[key]
        out.append({
            "text": " ".join(ln["words"]),
            "height": statistics.mean(ln["heights"]),
            "top": ln["top"],
        })
    return out, confs


def extract_label_fields(image_bytes: bytes) -> dict:
    if not tesseract_available():
        raise RuntimeError(
            "Local OCR mode needs Tesseract installed "
            "(https://github.com/UB-Mannheim/tesseract/wiki on Windows, "
            "`apt install tesseract-ocr` on Linux) — or set "
            "ANTHROPIC_API_KEY to use Claude vision instead.")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if max(img.size) < 1200:  # upscale small images; Tesseract likes big text
        scale = 1200 / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)),
                         Image.LANCZOS)
    lines, confs = _ocr_lines(img)

    issues = []
    mean_conf = statistics.mean(confs) if confs else 0
    if not lines:
        issues.append("OCR could not read any text from the image")
    elif mean_conf < 60:
        issues.append(f"low OCR confidence ({mean_conf:.0f}/100) — image may "
                      "be blurry, angled, or low-contrast")

    # ---- government warning: from 'GOVERNMENT WARNING' to the end of label
    warning_text = None
    warn_idx = next((i for i, ln in enumerate(lines)
                     if _WARN_RE.search(ln["text"])), None)
    if warn_idx is not None:
        chunk = " ".join(ln["text"] for ln in lines[warn_idx:])
        m = _WARN_RE.search(chunk)
        warning_text = chunk[m.start():].strip()
    body_lines = lines[:warn_idx] if warn_idx is not None else lines

    # ---- pattern-matched fields
    def first_match(regex):
        for ln in body_lines:
            if regex.search(ln["text"]):
                return ln
        return None

    abv_line = first_match(_ABV_RE)
    # net contents may share a line with ABV (common on beer: "6.5% ALC/VOL - 12 FL OZ")
    vol_line = next((ln for ln in body_lines if _VOL_RE.search(ln["text"])), None)
    producer_line = first_match(_PRODUCER_RE)
    origin_m = next((m for ln in body_lines
                     if (m := _ORIGIN_RE.search(ln["text"]))), None)

    # ---- brand name: tallest text line that isn't a data/decoration line
    special = {id(abv_line), id(vol_line), id(producer_line)}
    candidates = [ln for ln in body_lines
                  if id(ln) not in special
                  and not _DECOR_RE.match(ln["text"])
                  and re.search(r"[A-Za-z]{2,}", ln["text"])]
    brand_line = max(candidates, key=lambda ln: ln["height"], default=None)

    # ---- class/type: prominent text lines after the brand, before ABV
    class_type = None
    if brand_line is not None:
        between = [ln for ln in candidates
                   if ln["top"] > brand_line["top"]
                   and (abv_line is None or ln["top"] < abv_line["top"])
                   and not _ORIGIN_RE.search(ln["text"])]
        if between:
            # keep the taller lines (drops small print), preserve order
            tallest = max(ln["height"] for ln in between)
            kept = [ln for ln in between if ln["height"] >= 0.75 * tallest]
            class_type = " ".join(ln["text"] for ln in kept) or None

    return {
        "brand_name": brand_line["text"] if brand_line else None,
        "class_type": class_type,
        "alcohol_content": abv_line["text"] if abv_line else None,
        "net_contents": (_VOL_RE.search(vol_line["text"]).group(0)
                         if vol_line else None),
        "producer": producer_line["text"] if producer_line else None,
        "country_of_origin": origin_m.group(0) if origin_m else None,
        "government_warning": {
            "text": warning_text,
            "prefix_bold": None,  # OCR can't judge font weight reliably
        },
        "image_quality_issues": issues,
    }


