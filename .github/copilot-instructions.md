# Copilot instructions for SavvySipping

Purpose
- Help AI agents make safe, high-impact code changes in this repo.

Big picture (what to know first)
- Web front-end: `wine_trainer/app.py` is a small Flask app exposing `/process` and `/health`.
- Pipeline: `wine_trainer/pipeline/` implements three sequential steps:
  - `adobe_extractor.py` — extracts text from uploaded PDF via Adobe PDF Services SDK and returns clean text.
  - `claude_analyzer.py` — runs 3 Claude/Anthropic calls that must remain in order (training, MCQ, cheat sheet). Prompts include strict `PERSONA_BLOCK` and format/accuracy rules.
  - `doc_generator.py` — converts the returned Markdown into 4 PDFs using ReportLab (training, MCQ, cheat sheet, answer key).
- Files uploaded by users go to `uploads/`; outputs and ZIPs go to `generated/`.

Key integration points & env vars
- Adobe SDK: code reads credentials from `ADOBE_CREDENTIALS_PATH` (default `pdfservices-api-credentials.json`). See `wine_trainer/pdfservices-api-credentials.json` and `PDFServicesSDK-PythonSamples/`.
- Claude/Anthropic: uses `ANTHROPIC_API_KEY` and `anthropic.Anthropic` client in `pipeline/claude_analyzer.py`.
- Flask settings: `FLASK_SECRET_KEY`, `FLASK_DEBUG`. Gunicorn recommended for production: `gunicorn app:app --workers 2 --timeout 300`.

Developer workflows (how to run & debug)
- Install deps (project uses per-folder `requirements.txt`):

  pip install -r wine_trainer/requirements.txt

- Run locally in dev:

  python wine_trainer/app.py

- Run with Gunicorn (for production-like timeout):

  cd wine_trainer && gunicorn app:app --workers 2 --timeout 300

- When debugging pipeline issues:
  - Reproduce with a real menu PDF (place in `uploads/` or upload via UI).
  - Check logs printed by `logging` in each pipeline module.
  - Validate Adobe extraction result by inspecting `extract_wine_list` return value before Claude calls.

Project-specific conventions & gotchas
- Pipeline order is important: do not reorder or parallelize the three Claude calls without adjusting `app.py` timeout and tests.
- `claude_analyzer.py` enforces strict format rules (bullet-only, short sentences, exact section order). `doc_generator.py` expects predictable headings and uses simple heuristics (`_split_mcq_and_key`) to separate test vs answer key — keep the Answer Key marker intact (`# Answer Key`).
- Markdown parser in `doc_generator.py` is lightweight: only supports simple headings, bullets, MCQ option lines (A) B) C)), and numbered lists. Avoid exotic markdown syntax.
- `adobe_extractor.py` expects the Adobe result ZIP to contain `structuredData.json`. Do not change the Adobe options unless you also update `_parse_adobe_zip`.
- Filenames use `_safe_filename` / `_safe_name` helpers to make filesystem-safe outputs — prefer these helpers when creating names.

Where to look for examples
- Upload + pipeline orchestration: `wine_trainer/app.py` (process flow, error handling, cleanup).
- Adobe extraction example: `wine_trainer/pipeline/adobe_extractor.py`.
- Prompt engineering and required structure: `wine_trainer/pipeline/claude_analyzer.py` (see `PERSONA_BLOCK`, `TRAINING_SYSTEM`, `MCQ_SYSTEM`, `CHEAT_SHEET_SYSTEM`).
- Markdown → PDF logic and style: `wine_trainer/pipeline/doc_generator.py` (colors, page layout, parsing rules).

Safety and tests
- Long-running network calls (Adobe, Claude) can time out in web requests — prefer local script runs for iteration and increase Gunicorn `--timeout` when needed.
- Unit tests are not present; when modifying parsing or prompt structure, run the pipeline end-to-end with a representative PDF to verify outputs.

If you change prompts or markdown format
- Update `claude_analyzer.py` and `doc_generator.py` together. Example: if you add a new heading level or rename "Answer Key", update `_split_mcq_and_key`.

What I cannot infer from code
- Exact dependency pins (check `wine_trainer/requirements.txt` before installing).
- Production deployment steps (CI/CD) — the repo has no workflow files; ask maintainers for build pipelines.

Questions for reviewers
- Which environments hold real API keys? (local `.env` vs CI)
- Should we add small unit tests for `_split_mcq_and_key` and `_markdown_to_story` to prevent regressions?

— End of instructions
