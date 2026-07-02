# TTB Label Verifier

**Project Overview: Approach, Tools, and Deployment**

**Live site:** https://label-verifier-aisx.onrender.com
**Source:** https://github.com/amarsolek/label-verifier

---

## 1. What This Is

The TTB Label Verifier is a prototype web application that checks an alcohol beverage label image against the data submitted on a COLA application. An agent enters (or batch-uploads) the application fields, drops in a label image, and gets a field-by-field verdict in a few seconds: brand name, class/type designation, alcohol content, net contents, and the mandatory government health warning. The goal is to automate the routine "does the label match the form?" portion of label review — the work agents described as data-entry verification — while explicitly routing judgment calls to humans rather than deciding them automatically.

## 2. Approach

The central design decision is a strict separation between perception and verification. Reading the label (perception) is done by an interchangeable extraction engine that transcribes exactly what is printed into structured JSON. Deciding pass or fail (verification) is done by plain, deterministic Python with no AI involved. For a compliance tool this split matters: every verdict is reproducible, unit-testable, and auditable, and a wrong result can be debugged by looking at exactly two things — what the engine read, and what the rules did with it. The raw transcription is returned with every result for that reason.

Verification is deliberately field-specific rather than a single text comparison:

- **Brand name and class/type** — a capitalization-only difference (STONE'S THROW on the label vs. Stone's Throw on the form) counts as a match with a note, since labels stylize capitalization. Punctuation differences and near-misses (a possible typo) are flagged "needs review" for agent judgment — never silently passed or failed.
- **Alcohol content** — parsed numerically, so a form that says "45" matches a label that says "45% Alc./Vol. (90 Proof)". Proof is cross-checked against ABV, so an internally inconsistent label (45% but 80 proof) is caught.
- **Net contents** — parsed with unit conversion, so "1 L" matches "1000 mL".
- **Government warning** — checked word-for-word against the statutory text in 27 CFR Part 16, with "GOVERNMENT WARNING:" required in capital letters. A title-case prefix or any rewording is rejected, and the result includes a word-level diff pinpointing exactly what deviates. This check runs on every label automatically; it is never user input.

Each field gets one of four statuses (match, needs review, mismatch, missing), and the label's overall verdict rolls up from them. The "needs review" tier exists because label review requires nuance — the tool's job is to clear the obvious cases quickly and put the ambiguous ones in front of a person.

## 3. Tools Used

| Layer | Tool | Why |
|---|---|---|
| Backend | Python 3, FastAPI, Uvicorn | Small, fast, easy to run and review; one file of routes |
| Frontend | Single HTML page, vanilla JS | No build step, no framework; loads instantly and stays simple |
| AI extraction | Claude vision API | Best accuracy on photos, glare, angles, stylized fonts (optional) |
| Free extraction | Tesseract OCR (pytesseract) | Zero-cost, fully offline fallback; default engine |
| Imaging | Pillow | Image downscaling; also generates all synthetic test labels |
| Testing | pytest (26 tests) | Full coverage of the verification rules |
| Packaging | Docker | Reproducible image that bundles Tesseract for cloud hosting |
| Hosting | GitHub + Render (free tier) | Public code, auto-deploy on every commit, free public URL |

## 4. Assumptions

- This is a standalone proof of concept — no integration with the COLA system, its authentication, or its data. Application fields are typed in (or supplied as a CSV in batch mode) rather than pulled from filings.
- Nothing is stored. The server is stateless: images are processed in memory, never written to disk, and no database exists. This keeps the prototype clear of PII and retention obligations.
- Labels are in English, one image per application (a front label). Multi-image front/back review is a next step.
- The statutory warning text is a fixed reference constant; bold-type detection from a photo is best-effort and marked as such rather than guessed.
- Batch mode matches images to CSV rows by filename.
- Responses should land in roughly five seconds — the pilot-failure threshold stakeholders described — and the measured time is displayed on every result to keep that budget honest.

## 5. Keeping the Website Clean and Neat

The compliance team ranges from a 28-year veteran who prints his emails to a recent graduate, and the stated bar was "something my mother could figure out." The interface was designed to eliminate confusion rather than add capability:

- Two tabs total — Single label and Batch upload. There are no menus, no settings pages, and nothing to configure.
- One screen per task: four labeled text boxes, one drop zone (drag, click, or paste), and one large Verify button. Blank fields are simply skipped.
- Verdicts are communicated three ways at once — icon, color, and plain words ("Match", "Needs review", "Mismatch") — so nothing depends on color vision or interpretation.
- Notes are written in plain language ("Same text; differs only in capitalization"), and warning problems come with the exact differing words highlighted, so the agent immediately sees why.
- Large base fonts, high contrast, keyboard-accessible controls, and a banner that always states which extraction engine is running, so there is never a mystery about what the tool is doing.
- Batch results triage into three headline numbers — passed, needs review, failed — with expandable per-label detail and a one-click CSV export.

## 6. The API Key Problem, and the OCR Solution

The original design used Claude's vision API as the extraction engine. That is still the strongest option — it reads angled, glary, and stylized labels that OCR cannot — but it surfaced a practical problem: it requires a paid Anthropic API key. During setup this created real friction (a truncated key copied from the console produced authentication failures, and purchasing credits was not desirable for a demo), and any public deployment would put per-request costs on whoever owns the key. A related constraint came from IT: the agency network blocks outbound traffic to most ML endpoints, so a cloud-only design had a known failure mode from day one.

The resolution was to make the extraction engine swappable behind a single interface, with automatic selection. When an ANTHROPIC_API_KEY is present, the app uses Claude vision. When it is not, the app falls back to Tesseract, a free, open-source OCR engine that runs entirely on the local machine — no key, no cost, no outbound network traffic. Both engines return the same JSON structure, so the verification logic, the UI, and the API are identical either way, and the interface banner plus every API response state which engine produced the result.

The trade-off is honest and documented: local OCR performs well on clean, straight-on images (all ten bundled test labels verify correctly, including dark and multi-color designs), but it loses text under heavy glare or steep angles — one test label demonstrates exactly this failure. Claude vision handles those cases, which is why the engine can be upgraded later by setting one environment variable, with no code changes. One deployment lesson worth recording: on Render's fractional-CPU free tier, Tesseract's default multithreading caused 40-second responses; limiting it to a single thread (OMP_THREAD_LIMIT=1 in the Dockerfile) brought verification back to roughly 3–4 seconds.

## 7. The Live Website

**URL:** https://label-verifier-aisx.onrender.com

The site runs in free OCR mode — anyone can use it without any key. Because it is on Render's free tier, the service sleeps after about 15 idle minutes; the first visit afterward can take up to a minute to wake, after which it is responsive. Adding an ANTHROPIC_API_KEY environment variable in the Render dashboard would switch it to Claude vision automatically.

### Single label

Enter the application fields exactly as filed (any can be left blank), drop or paste a label image, and click Verify label. The result shows an overall banner, a row per field with the application value and the label value side by side, plain-language notes, a word-level diff for warning violations, and the processing time.

### Batch upload

Switch to the Batch upload tab, drop a CSV of applications (a template is downloadable on the page; columns are image_filename, brand_name, class_type, alcohol_content, net_contents), then drop all the label images at once. Rows are matched to images by filename, processed four at a time with a progress bar, summarized as passed / needs review / failed, and exportable as a results CSV. The repository's test_labels folder includes applications.csv covering all ten sample labels below.

| Test label | Expected result |
|---|---|
| old_tom_clean.png | Passes — all fields match |
| old_tom_wrong_abv.png | Fails — label shows 40% / 80 proof vs. 45 on the application |
| stones_throw_case.png | Passes — capitalization-only brand difference, noted |
| riverbend_bad_warning.png | Fails — warning in title case and reworded; diff shown |
| midnight_gin.png | Passes — light-on-dark modern design |
| sunset_ipa.png | Passes — colorful beer label; ABV and volume share one line |
| casa_azul_tequila.png | Fails — label shows 700 mL vs. 750 mL on the application |
| velvet_hare_wine.png | Fails — government warning missing entirely |
| old_tom_photo.png | Passes — simulated photo with slight angle, shadow, and noise |
| old_tom_photo_glare.png | Fails — glare hides the warning; demonstrates the OCR limit that Claude vision addresses |

## 8. The GitHub Repository

**URL:** https://github.com/amarsolek/label-verifier

The repository is public and contains everything needed to run or deploy the app:

| Path | Contents |
|---|---|
| app.py | FastAPI server: /api/verify, /api/health, engine selection, static hosting |
| compare.py | All verification rules (deterministic, no AI) — the heart of the tool |
| extraction.py | Claude vision extraction engine (used when an API key is set) |
| ocr_extraction.py | Tesseract OCR extraction engine (free default) |
| static/index.html | The entire web interface, one file |
| test_labels/ | Ten sample labels plus applications.csv for batch mode |
| tests/ | 26 pytest unit tests over the verification logic |
| scripts/ | Test-label generators and a pipeline checker (check_labels.py) |
| Dockerfile / render.yaml | Container build (bundles Tesseract) and Render deployment blueprint |
| README.md | Setup, run, and deployment instructions |

To run locally: install Python 3.11+, run pip install -r requirements.txt, install Tesseract (winget install UB-Mannheim.TesseractOCR on Windows; apt install tesseract-ocr on Linux), then uvicorn app:app and open http://localhost:8000. Setting ANTHROPIC_API_KEY is optional and enables the AI engine. Deployment is automatic: any commit pushed to the main branch triggers Render to rebuild the Docker image and redeploy the live site within a few minutes.

## 9. Limitations and Next Steps

Known gaps, deliberate for a prototype: bold-type detection on the warning is best-effort; type-size and legibility rules (27 CFR 16.22) are not measured; beverage-type-specific rules are not differentiated; producer address and country of origin are extracted but not yet verified; and OCR mode struggles with heavy glare or steep angles by design of the engine, not the tool. Natural next steps are an agent feedback loop to build an evaluation set, COLA form-PDF ingestion so application data never needs typing, front/back multi-image support, and — for production inside the agency firewall — routing the AI engine through a FedRAMP-authorized gateway, which the swappable-engine design already accommodates.
