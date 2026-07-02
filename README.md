# TTB Label Verifier

AI-powered prototype that checks alcohol beverage label images against COLA
application data: brand name, class/type, alcohol content, net contents, and
the mandatory government health warning. Built for the TTB Compliance Division
take-home project.

## Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # Windows: set ANTHROPIC_API_KEY=...
uvicorn app:app
```

Open http://localhost:8000.

**No API key? It still works.** With no `ANTHROPIC_API_KEY` set, the app
automatically falls back to a free local OCR engine (Tesseract — install via
`apt install tesseract-ocr` on Linux or the UB-Mannheim installer/winget on
Windows). Local OCR runs fully offline — which also directly addresses the
IT constraint that outbound ML endpoints are firewalled — and handles clean,
straight-on label images well; Claude vision is markedly better on angled,
glary, or stylized photos. Force an engine with `VERIFIER_ENGINE=claude|ocr`.
The UI shows which engine is active, and each API response includes it. Try it with the images in `test_labels/`:

| Image | Application says | Expected result |
|---|---|---|
| `old_tom_clean.png` | brand `OLD TOM DISTILLERY`, abv `45`, `750 mL` | ✅ all match |
| `old_tom_wrong_abv.png` | abv `45` | ❌ label shows 40% / 80 proof |
| `stones_throw_case.png` | brand `Stone's Throw` | ✅ match, noted as caps-only difference |
| `riverbend_bad_warning.png` | (any) | ❌ warning in title case + reworded, with diff |
| `midnight_gin.png` | brand `MIDNIGHT`, abv `47`, `750 mL` | ✅ dark modern design, all match |
| `sunset_ipa.png` | brand `SUNSET CANYON`, abv `6.5`, `12 fl oz` | ✅ colorful beer label; ABV and volume share a line |
| `casa_azul_tequila.png` | `750 mL` | ❌ label shows 700 mL |
| `velvet_hare_wine.png` | (any) | ❌ no government warning on the label |
| `old_tom_photo.png` | same as clean | ✅ simulated photo: slight angle, shadow, noise |
| `old_tom_photo_glare.png` | same as clean | ❌ glare obscures the warning — a deliberate OCR-limit case; Claude vision handles these |

**Batch mode:** switch to the "Batch upload" tab, drop `test_labels/applications.csv`
plus all four images, and click Process batch. Results export to CSV.

Run tests with `pytest` (26 tests on the verification logic).
Regenerate test labels with `python scripts/generate_test_labels.py`.

## How it works

```
browser ──image + application JSON──▶ FastAPI ──▶ extraction.py   (Claude vision: transcribe label → JSON)
                                              ──▶ compare.py      (deterministic checks, no model)
        ◀──per-field verdicts + diff + timing──
```

The key design decision: **the model does perception, plain code does
verification.** Claude's only job is to transcribe the label exactly as
printed into structured JSON — it never decides pass/fail. All comparison
logic (case normalization, ABV/proof math, unit conversion, the word-for-word
warning check) is ordinary Python in `compare.py`: reproducible, unit-testable,
and auditable, which matters for a compliance decision. It also means a wrong
verdict can be debugged by looking at exactly two things: what the model read,
and what the rules did with it. The raw extraction is returned in every API
response for that reason.

### Verdicts

Every field gets one of four statuses, and the strictness is deliberately
field-specific, based on the discovery interviews:

- **Brand name / class-type** — Dave's `STONE'S THROW` vs `Stone's Throw`
  example: a capitalization-only difference is a **match with a note**, not a
  rejection. Punctuation differences or near-misses (≥85% similar, e.g. a
  possible typo) become **needs review** — surfaced for judgment, never
  silently passed or failed.
- **Alcohol content** — parsed numerically, so an application that says `45`
  matches a label that says `45% Alc./Vol. (90 Proof)`. Proof is cross-checked
  against ABV (proof must equal 2×ABV), catching internally inconsistent labels.
- **Net contents** — parsed with unit conversion (`1 L` matches `1000 mL`).
- **Government warning** — Jenny's requirement: verbatim, word-for-word,
  against the 27 CFR Part 16 statutory text, with `GOVERNMENT WARNING:` in
  capital letters. Title-case prefix → rejected. Any rewording → rejected,
  with a word-level diff showing exactly what deviates. Line breaks and
  whitespace are ignored (labels wrap text). Bold type can't be reliably
  judged from a photo, so the model reports its impression: "not bold" →
  needs review, "unsure" → match with a caveat. The warning is checked on
  every label automatically — it is never user input.

An overall verdict rolls up: any mismatch/missing → **fail**, any needs-review
→ **review**, else **pass**.

## Requirements from the interviews → what the prototype does

- **~5 second response (Sarah)** — one model round-trip per label, images
  downscaled server-side to 1568px before upload, and the measured processing
  time is shown on every result so the latency budget stays visible. Model is
  swappable via `VERIFIER_MODEL` env var if a smaller/faster model is preferred.
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
- **Imperfect photos (Jenny)** — the extraction prompt asks the model to
  report glare/angle/blur; the UI surfaces a "results may be less reliable"
  banner suggesting a re-shoot rather than failing silently.
- **Firewall blocks outbound ML endpoints (Marcus)** — a real constraint for
  production, acknowledged rather than solved here: this prototype needs
  egress to `api.anthropic.com` only. A production path would use a
  FedRAMP-authorized gateway (e.g. Claude in AWS GovCloud/Bedrock) or an
  internal proxy — the extraction layer is a single function behind an
  interface, so swapping the transport touches one file.
- **Nothing sensitive stored (Marcus)** — the server is stateless: images are
  processed in memory and never written to disk; no database, no retention.

## API

`POST /api/verify` — multipart form: `image` (JPEG/PNG/WebP, ≤15 MB) +
`application` (JSON string with any of `brand_name`, `class_type`,
`alcohol_content`, `net_contents`; blank fields are skipped). Returns
per-field results, word-level warning diff, the raw extraction, image quality
issues, and elapsed seconds. `GET /api/health` reports whether an API key is
configured.

## Limitations / next steps

Honest gaps, given the prototype scope: bold-type detection is best-effort;
type-size and legibility rules (27 CFR 16.22) aren't measured; beverage-type
specific rules (wine vs spirits vs malt) aren't differentiated; producer
address and country of origin are extracted but not yet verified; batch mode
matches strictly by filename. The natural next steps are a feedback loop
(agents mark verdicts right/wrong to build an eval set), COLA form-PDF
ingestion so application data doesn't need typing, and multi-image support
for front/back labels.

