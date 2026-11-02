# Progress log
- Format: `YYYY-MM-DD | task id | one-line result`
2026-10-22 | T1.1 | Project skeleton created, config loads .env, /health returns ok, pytest passes, ruff clean.
2026-10-22 | T1.2 | Dockerfile and docker-compose.yml created for api, worker, redis, postgres with ffmpeg; verified docker not on host.
2026-10-22 | T1.3 | SQLAlchemy models for all 10 tables created, Alembic initial migration generated and applied, relationship tests passing.
2026-10-22 | T1.4 | Created interfaces and test fakes for LLMClient, MessagingProvider, and LocalStorage with comprehensive test coverage.
2026-10-22 | T2.1 | Created tests/make_fixtures.py generating 3 synthetic vertical test clips (1080x1920, h264/aac) and real clip importer.
2026-10-22 | T2.2 | Implemented pipeline/analyse.py local metrics (OpenCV blur/brightness, 1fps sampler, FFmpeg volumedetect).
2026-10-22 | T2.3 | Vision analysis with analyse_v1.md, retry on invalid JSON, safe fallback (score 5), and thread pool parallel execution.
2026-10-22 | T2.4 | Implemented pipeline/plan.py with PlanResult validation, retry logic, footage sufficiency checks, and deterministic fallback plan.
2026-10-22 | T2.5 | Implemented template loader, ASS subtitle styling, and pipeline/render.py for offer template with H.264/AAC, ducked music, and faststart.
2026-10-22 | T2.6 | Implemented all 10 quality gates in pipeline/quality.py and auto-fix loop; verified unverified prices block delivery.
2026-10-22 | T2.7 | Built scripts/run_local.py CLI executing download->analyse->plan->render->quality with timings, cost, and artifact exports.
2026-10-22 | T2.8 | Video review checkpoint: generated out/preview.mp4 passing all 10 quality gates in 7.31s total execution.
2026-10-22 | T3.1 | Added template-driven ASS styling and verified new_dish (14s) and behind_the_scenes (16s) rendering passing all gates.
2026-10-22 | T3.2 | Implemented pipeline/revise.py with minimal re-run (price, text, duration +/-25%, hook), 3-revision limit, and full test suite.
2026-10-22 | T4.1 | Built TwilioProvider, webhook POST /webhooks/twilio with signature validation, message deduplication, and full test suite.
2026-10-22 | T4.2 | Implemented conversation state machine, onboarding, typed menu parsing, global commands, and scripted test suite.
2026-10-22 | T4.3 | Implemented menu photo extraction via menu_extract_v1.md with owner confirmation and full test coverage.
2026-10-22 | T4.4 | Implemented campaign trigger, 60s media grouping, orchestrator pipeline, preview/revisions, and full conversation loop test.
2026-10-22 | T4.5 | Implemented signed expiring video URLs under PUBLIC_BASE_URL, GET /videos/{id} endpoint, and full test suite.
2026-10-22 | T4.6 | Added optional voice-note transcription guarded behind ENABLE_VOICE_NOTES with text-only fallback.
2026-11-02 | T5.1 | Implemented persistent job orchestrator with CampaignStep persistence, 3x exponential backoff, mid-step resume, and owner failure notification.
2026-11-02 | T5.2 | Implemented monthly usage limits (UsageCounter), per-business sequential locking, and media size (<50MB) and duration (<60s) validation.
2026-11-02 | T5.3 | Implemented CostLog persistence, INR token/compute cost estimation, and token-secured GET /admin/jobs dashboard HTML table.
2026-11-02 | T5.4 | Implemented scripts/delete_business.py for privacy/GDPR wipe and SensitiveDataFilter for phone/secret log masking.
2026-11-02 | T6.1 | Authored comprehensive README.md covering setup, env vars, Twilio sandbox + ngrok, CLI usage, ops, and test commands.
2026-11-02 | T6.2 | Full test suite passed (77/77 tests), ruff clean, and compiled final hand-off verification summary.













