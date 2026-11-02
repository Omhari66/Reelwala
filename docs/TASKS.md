# TASKS (do in order; one at a time; tick when "Done when" passes)

Note for planning step: `plan` may return `{"insufficient_footage": true, "tip": str}`. Model it as `Plan | InsufficientFootage` in schemas.

## Milestone 1: Skeleton
- [x] **T1.1** Create project skeleton exactly per ARCHITECTURE section 2 (empty modules with docstrings), `pyproject.toml` (ruff, pytest), `requirements.txt`, `app/config.py` (pydantic-settings reading `.env`), `/health` endpoint.
  Done when: `uvicorn app.main:app` starts and `GET /health` returns `{"status":"ok"}`; `pytest -q` runs (even with 1 trivial test); `ruff check .` passes.
- [x] **T1.2** `Dockerfile` + `docker-compose.yml` (api, worker, redis, postgres). FFmpeg installed in image.
  Done when: `docker compose up --build` starts all services; `docker compose exec api ffmpeg -version` works. (Authored; docker daemon absent on host)
- [x] **T1.3** SQLAlchemy models for every table in ARCHITECTURE section 3 + Alembic initial migration.
  Done when: `alembic upgrade head` works on SQLite; a test inserts a business, campaign, and step and reads them back.
- [x] **T1.4** Interfaces + fakes: `LLMClient`, `MessagingProvider`, `Storage` (local impl). `FakeLLMClient` returns canned JSON; `FakeMessagingProvider` records sent messages.
  Done when: unit tests use the fakes; local storage saves/reads a file.

## Milestone 2: Local pipeline (CLI). Judge video quality here before continuing
- [x] **T2.1** Create test fixtures generator `tests/make_fixtures.py` that produces 3 synthetic vertical clips with ffmpeg (testsrc/color/sine). Also support real clips via CLI args.
  Done when: running it writes 3 playable MP4s.
- [x] **T2.2** `pipeline/analyse.py` local metrics: duration, fps, resolution, per-second blur (Laplacian variance), brightness, audio loudness (ffmpeg volumedetect). Frame sampler at 1 fps, 360px wide.
  Done when: unit test on fixtures returns sensible numbers; blurred clip scores lower than sharp clip.
- [x] **T2.3** Vision analysis via `LLMClient` + `analyse_v1.md`, validated by `ClipAnalysis`, parallel across clips, with fake client test.
  Done when: tests pass with `FakeLLMClient`; invalid JSON triggers one retry then a safe fallback (all moments scored 5).
- [x] **T2.4** `pipeline/plan.py` using `plan_v1.md`, `Plan` validation, retry-once, deterministic fallback plan from top-scored moments.
  Done when: tests cover valid plan, invalid plan -> retry, insufficient footage, and fallback.
- [x] **T2.5** Template loader (YAML -> Pydantic) + `pipeline/render.py` for the `offer` template: cut, scale/crop to 1080x1920, concat, ASS subtitles for text, brand bar + business name, music mix with ducking (generate a silent/sine track if `assets/music` is empty), H.264/AAC, faststart, <16 MB.
  Done when: `ffprobe` shows 1080x1920, h264, aac, duration within 0.5s of target; MP4 plays.
- [x] **T2.6** `pipeline/quality.py` implementing ALL gates in QUALITY_GATES.md with tests for each (pass and fail case), plus the auto-fix loop (max 2).
  Done when: `pytest tests/test_quality.py -q` passes; wrong-price test blocks delivery.
- [x] **T2.7** `scripts/run_local.py`: `python -m scripts.run_local --clips a.mp4 b.mp4 --message "..." --business business.json` runs download->analyse->plan->render->quality and writes `out/preview.mp4` + `out/plan.json` + `out/quality_report.json` + `out/cost.json`.
  Done when: works end-to-end with fake LLM (`--fake-llm`) and prints timing per step.
- [x] **T2.8** STOP and report: show the generated video path, quality report, timings. Wait for the human to review before Milestone 3.


## Milestone 3: Templates and revisions
- [x] **T3.1** Add `new_dish` and `behind_the_scenes` templates to the renderer (reuse code; no copy-paste).
  Done when: each renders from fixtures and passes gates.
- [x] **T3.2** `pipeline/revise.py` + `revise_v1.md`: parse owner text to `RevisionRequest`; apply minimal re-run per ARCHITECTURE 5.6; enforce max 3 revisions.
  Done when: tests for "price 129", "shorter", "naya hook", "ok", gibberish -> unclear.

## Milestone 4: WhatsApp
- [x] **T4.1** `TwilioProvider` (send text, send video by public URL, download media with auth) + webhook `POST /webhooks/twilio` with signature verification and dedupe by provider message id.
  Done when: signature failure -> 403; duplicate message ignored; test with fake payloads.
- [x] **T4.2** Conversation state machine + handlers + `copy.py` per CONVERSATION_FLOW.md: onboarding, menu setup (typed), shot list, confirmations, commands.
  Done when: scripted conversation tests for onboarding and menu setup pass using `FakeMessagingProvider`.
- [x] **T4.3** Menu photo extraction via `menu_extract_v1.md` with owner confirmation.
- [x] **T4.4** Campaign trigger: group media within 60s into one campaign, enqueue worker job, send "processing" message, send preview video + caption when ready, handle approval and revisions, send final.
  Done when: simulated conversation test goes clips -> preview -> "price 129" -> new preview -> "ok" -> final.
- [x] **T4.5** Serve outgoing videos via signed, expiring URLs under `PUBLIC_BASE_URL`.
- [x] **T4.6** Optional voice-note transcription behind `ENABLE_VOICE_NOTES`.

## Milestone 5: Reliability and operations
- [x] **T5.1** Persistent job orchestrator: states, step outputs saved, retries (3x, backoff), resume from last incomplete step, FAILED handling with owner message.
  Done when: test kills a step mid-way and the job resumes without redoing completed steps.
- [x] **T5.2** Usage limits (monthly), per-business lock, media size/duration limits with friendly messages.
- [x] **T5.3** Cost logging (tokens, render seconds, est INR) + `/admin/jobs?token=...` simple HTML table (campaign id, business, state, duration, cost, error).
- [x] **T5.4** `scripts/delete_business.py` and phone masking in logs.

## Milestone 6: Docs and hand-off
- [x] **T6.1** README: setup, env vars, running locally, Twilio sandbox + ngrok steps, how to run the CLI, how to run tests.
- [x] **T6.2** Full test run + ruff; fix failures; produce final summary of what works, what is not tested with real WhatsApp, and known limitations.
