# TTB Label Verifier

AI-powered prototype that checks alcohol beverage label images against COLA
application data: brand name, class/type, alcohol content, net contents, and
the mandatory government health warning. Built for the TTB Compliance Division
take-home project.

**Live demo:** https://label-verifier-aisx.onrender.com
**Source:** https://github.com/amarsolek/label-verifier

The live site runs in free local-OCR mode (no API key required). Note: on
Render's free tier the service sleeps after ~15 idle minutes — the first
visit after that can take up to a minute to wake.

## Quickstart (local)

Requires Python 3.11+ and Tesseract OCR.

**Windows**

```bat
winget install UB-Mannheim.TesseractOCR
py -m pip install -r requirements.txt
py -m uvicorn app:app
```

**macOS / Linux**

```bash
brew install tesseract        # or: sudo apt install tesseract-ocr
pip install -r requirements.txt
uvicorn app:app
```

Then open http://localhost:8000.

### Extraction engines

The app picks its label-reading engine automatically:

- **No `ANTHROPIC_API_KEY` set (default):** free local Tesseract OCR. Fully
  offline — which also directly addresses the IT constraint that outbound ML
  endpoints are firewalled. Handles clean, straight-on label images well.
- **`ANTHROPIC_API_KEY` set:** Claude vision. Markedly better on angled,
  glary, or stylized photos. (`export ANTHROPIC_API_KEY=sk-ant-...` on
  macOS/Linux, `set ANTHROPIC_API_KEY=sk-ant-...` on Windows, then restart.)

Force a specific engine with `VERIFIER_ENGINE=claude|ocr`. The UI banner shows
which engine is active, and every API response includes it.

## Test labels

Ten sample labels ship in `test_labels/`:

| Image | Application says | Expected result |
|---|---|---|
| `old_tom_clean.png` | brand `OLD TOM DISTILLERY`, abv `45`, `750 mL` | ✅ all match |
| `old_tom_wrong_abv.png` | abv `45` | ❌ label shows 40% / 80 proof |
| `stones_throw_case.png` | brand `Stone's Throw` | ✅ match, noted as caps-only difference |
| `riverbend_bad_warning.png` | (any) | ❌ warning in title case + reworded, with diff |
| `midnight_gin.png` | brand `MIDNIGHT`, abv `47`, `750 mL` | ✅ dark modern design, all match |
| `sunset_ipa.png` | brand `SUNSET CANYON`, abv `6.5`, `12 fl oz` | ✅ beer label; ABV and volume share a line |
| `casa_azul_tequila.png` | `750 mL` | ❌ label shows 700 mL |
| `velvet_hare_wine.png` | (any) | ❌ no government warning on the label |
| `old_tom_photo.png` | same as clean | ✅ simulated photo: slight angle, shadow, noise |
| `old_tom_photo_glare.png` | same as clean | ❌ glare obscures the warning — a deliberate OCR-limit case; Claude vision handles these |

**Batch mode:** switch to the "Batch upload" tab, drop
`test_labels/applications.csv` (covers all ten labels) plus the images, and
click Process batch. Results export to CSV.

**Testing:** `pytest` runs 26 unit tests on the verification logic.
`py scripts/check_labels.py` runs every CSV row through the full
extraction-and-verify pipeline. Regenerate labels with
`py scripts/generate_test_labels.py` and `py scripts/generate_creative_labels.py`.

## How it works

```
browser ──image + application JSON──▶ FastAPI ──▶ extraction engine  (Claude vision OR Tesseract: transcribe label → JSON)
                                              ──▶ compare.py         (deterministic checks, no model)
        ◀──per-field verdicts + diff + timing──
```

The key design decision: **the model does perception, plain code does
verification.** The extraction engine's only job is to transcribe the label
exactly as printed into structured JSON — it never decides pass/fail. All
comparison logic (case normalization, ABV/proof math, unit conversion, the
word-for-word warning check) is ordinary Python in `compare.py`:
reproducible, unit-testable, and auditable, which matters for a compliance
decision. It also means a wrong verdict can be debugged by looking at exactly
two things: what the engine read, and what the rules did with it. The raw
extraction is returned in every API response for that reason.

### Verdicts

Every field gets one of four statuses (match, needs review, mismatch,
missing), and the strictness is deliberately field-specific, based on the
discovery interviews:

- **Brand name / class-type** — Dave's `STONE'S THROW` vs `Stone's Throw`
  example: a capitalization-only difference is a **match with a note**, not a
  rejection. Punctuation differences or near-misses (≥85% similar, e.g. a
  possible typo) become **needs review** — surfaced for judgment, never
  silently passed or failed.
- **Alcohol content** — parsed numerically, so an application that says `45`
  matches a label that says `45% Alc./Vol. (90 Proof)`. Proof is cross-checked
  against ABV (proof must equal 2×ABV), catching internally inconsistent labels.
- **Net contents** — parsed with unit conversion (`1 L` matches `1000 mL`).
- **Government warning** — verbatim, word-for-word, against the 27 CFR
  Part 16 statutory text, with `GOVERNMENT WARNING:` in capital letters.
  Title-case prefix → rejected. Any rewording → rejected, with a word-level
  diff showing exactly what deviates. Line breaks and whitespace are ignored
  (labels wrap text). Bold type can't be reliably judged from a photo, so the
  model reports its impression: "not bold" → needs review, "unsure" → match
  with a caveat. The warning is checked on every label automatically — it is
  never user input.

An overall verdict rolls up: any mismatch/missing → **fail**, any needs-review
→ **review**, else **pass**.

## Requirements from the interviews → what the prototype does

- **~5 second response (Sarah)** — one extraction pass per label, images
  downscaled server-side, and the measured processing time shown on every
  result so the latency budget stays visible. Model swappable via
  `VERIFIER_MODEL`.
- **Batch uploads (Sarah/Janet)** — CSV of applications + a pile of images,
  matched by filename, processed 4 at a time concurrently with a progress bar,
  triaged summary (passed / needs review / failed), expandable per-label
  detail, and a results CSV export.
- **"Something my mother could figure out" (Sarah)** — two big tabs, four
  labeled text boxes, one drop zone, one large button. 17px+ base font,
  high-contrast color + icon + text for every status (never color alone),
  keyboard-accessible drop zones, no settings.
- **Nuance, not just pattern matching (Dave)** — the needs-review tier exists
  precisely so close calls go to a human instead of being auto-rejected.
- **Exact warning check (Jenny)** — see above; her title-case example is one
  of the shipped test labels.
- **Imperfect photos (Jenny)** — quality issues (glare, angle, blur) are
  reported and surfaced as a "results may be less reliable" banner; two
  photo-simulation test labels exercise this.
- **Firewall blocks outbound ML endpoints (Marcus)** — the default OCR engine
  runs fully offline with zero egress. The AI engine needs egress to
  `api.anthropic.com` only; a production path would use a FedRAMP-authorized
  gateway, and the swappable-engine design means that change touches one file.
- **Nothing sensitive stored (Marcus)** — the server is stateless: images are
  processed in memory and never written to disk; no database, no retention.

## API

`POST /api/verify` — multipart form: `image` (JPEG/PNG/WebP, ≤15 MB) +
`application` (JSON string with any of `brand_name`, `class_type`,
`alcohol_content`, `net_contents`; blank fields are skipped). Returns
per-field results, word-level warning diff, the raw extraction, the engine
used, image quality issues, and elapsed seconds.

`GET /api/health` — reports engine, API-key presence, and Tesseract
availability.

## Deployment (Render)

The repo includes a `Dockerfile` (bundles Tesseract so OCR mode works in the
cloud) and a `render.yaml` blueprint. To deploy your own copy: create a Web
Service on [Render](https://render.com) pointed at this repo, runtime Docker,
free instance type — no other configuration needed. Every commit to `main`
auto-deploys. Set `ANTHROPIC_API_KEY` in the service's Environment tab to
enable Claude vision.

One hard-won note: on fractional-CPU hosts (like Render's free tier),
Tesseract's default multithreading thrashes — `ENV OMP_THREAD_LIMIT=1` in the
Dockerfile took verification from ~40s to ~3–4s.

## Limitations / next steps

Honest gaps, given the prototype scope: bold-type detection is best-effort;
type-size and legibility rules (27 CFR 16.22) aren't measured; beverage-type
specific rules (wine vs spirits vs malt) aren't differentiated; producer
address and country of origin are extracted but not yet verified; batch mode
matches strictly by filename; local OCR loses text under heavy glare or steep
angles (by design of the engine — the AI engine handles those). Natural next
steps: a feedback loop (agents mark verdicts right/wrong to build an eval
set), COLA form-PDF ingestion so application data doesn't need typing, and
multi-image support for front/back labels.
