# GEMINI.md: Standing rules for the coding agent (read this first, every session)

Project: **Reelwala** (internal codename: CreatorOps). A WhatsApp-first service that turns raw phone clips from a small food business into a short vertical ad Reel.

## Read order (always)
1. `docs/PRD.md`: what and why
2. `docs/ARCHITECTURE.md`: how, stack, data model, pipeline
3. `docs/TASKS.md`: the ONLY source of what to do next
4. Reference when touching those areas: `docs/QUALITY_GATES.md`, `docs/CONVERSATION_FLOW.md`, `templates/*.yaml`, `app/llm/prompts/*.md`

## How you must work
- Work on **ONE task at a time** from `docs/TASKS.md`, in order. Never start the next task until the current task's "Done when" checks pass.
- Before coding a task: write a 5-line plan. After coding: run the tests/commands listed in the task, show the real output, tick the checkbox in `docs/TASKS.md`, and add a one-line note to `docs/PROGRESS.md`.
- If a requirement is ambiguous, **make the simplest assumption, write it in `docs/DECISIONS.md`, and continue**. Ask the human only if blocked, or if the choice affects cost, privacy, or security.
- Do not add features, libraries, or abstractions that are not in the docs. The out-of-scope list in PRD section 4 is binding.
- Prefer boring, small, readable code. Max ~300 lines per file. Type hints everywhere. Pydantic for every structured data shape.
- Never claim something works without running it. If you cannot run it, say so explicitly.
- Never hardcode secrets or model names. Use `app/config.py` + env vars (`.env.example` lists them).
- Never trust an LLM for measurable facts (duration, resolution, file size, blur, loudness, price equality). Use code (ffprobe/OpenCV/regex).
- Never invent prices, offers, timings, or claims in generated ads. Only use facts from the business profile or the owner's message.
- Every external call (LLM, messaging, storage) goes behind an interface so it can be mocked in tests.
- After each task, summarise files changed and how to run/test.

## Definition of done (every task)
1. Code runs. 2. Listed tests pass (`pytest -q`). 3. No dead code or unused files. 4. TASKS.md ticked, PROGRESS.md updated. 5. Short summary given.

## When you get stuck
Stop after 2 failed attempts at the same error. Write: what you tried, the exact error, your best hypothesis, and ask the human. Do not loop or rewrite unrelated files.

## Tech
Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, Redis + RQ, FFmpeg via `subprocess` with argument lists (never `shell=True` with user-derived input), OpenCV for blur metric, pytest, ruff.
