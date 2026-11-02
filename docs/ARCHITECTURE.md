# Architecture

## 1. Components
```
WhatsApp (owner) <-> Twilio/Meta <-> FastAPI webhook --enqueue--> Redis/RQ worker
                                         |                            |
                                      Postgres  <---------------------+
                                         |                            |
                                   Storage (local/S3)           FFmpeg / ffprobe / OpenCV
                                                                LLM API (vision + planning)
```
- **Webhook (FastAPI):** verify signature, dedupe by provider message id, store message, call conversation handler, reply fast. Never render inside a request.
- **Worker:** runs pipeline steps as RQ jobs.
- **Interfaces (all mockable):** `MessagingProvider`, `LLMClient`, `Storage`.

## 2. Folder structure
```
app/
  main.py  config.py
  api/ webhooks.py admin.py
  messaging/ base.py twilio_provider.py cloud_api_provider.py(stub)
  conversation/ state_machine.py handlers.py intents.py copy.py
  pipeline/ download.py analyse.py plan.py render.py quality.py revise.py orchestrator.py
  llm/ client.py schemas.py prompts/*.md
  models/ (SQLAlchemy)   db/ (alembic)
  storage/ base.py local.py s3.py
  workers/ tasks.py
templates/ offer.yaml new_dish.yaml behind_the_scenes.yaml
assets/ music/ fonts/
scripts/ run_local.py
tests/ fixtures/
docker-compose.yml Dockerfile .env.example README.md
```

## 3. Data model (minimum)
- `businesses`: id, phone_e164 (unique), name, category, language (`hinglish|hindi|english`), landmark, brand_hex, plan, created_at
- `menu_items`: id, business_id, name, price_inr (int), is_active
- `conversations`: id, business_id, state, last_message_at
- `messages`: id, conversation_id, direction (`in|out`), type, body, media_id, provider_msg_id (unique), created_at
- `media_assets`: id, business_id, campaign_id nullable, kind (`video|image|audio|menu_photo`), path, duration_s, width, height, created_at
- `campaigns`: id, business_id, state, request_text, template, plan_json, revision_count, created_at
- `campaign_steps`: id, campaign_id, name, status (`pending|running|done|failed`), output_json, attempts, error, started_at, finished_at
- `videos`: id, campaign_id, version, path, quality_report_json, size_bytes, duration_s
- `usage_counters`: business_id, month (YYYY-MM), count
- `cost_log`: campaign_id, step, input_tokens, output_tokens, render_seconds, est_cost_inr

## 4. Campaign states
`CREATED -> DOWNLOADING -> ANALYSING -> PLANNING -> RENDERING -> QUALITY_CHECK -> AWAITING_APPROVAL -> APPROVED`
Side states: `REVISING` (returns to PLANNING or RENDERING), `FAILED`, `CANCELLED`.
Rules: each step idempotent; outputs saved in `campaign_steps.output_json`; max 3 retries with exponential backoff; resume from the last incomplete step, never restart the job.

## 5. Pipeline step contracts
### 5.1 download
In: provider media URLs. Out: `media_assets` rows with local paths. Convert images to a 3-second still clip (Ken Burns zoom) so everything is a clip.

### 5.2 analyse
- Local (OpenCV/ffmpeg): per clip duration, fps, resolution, per-second blur score (Laplacian variance), brightness, audio mean/peak loudness.
- Vision LLM: ~1 frame per second, width 360px, batched per clip. Prompt: `prompts/analyse_v1.md`. Returns `ClipAnalysis` (schema below).
- Run clips in parallel (thread pool).

### 5.3 plan (ONE LLM call)
Prompt: `prompts/plan_v1.md`. Input: business profile + menu items, owner message, clip analyses, template catalogue. Output validated against `Plan` schema. On validation failure: retry once with the error message appended; then fall back to a deterministic default plan built from the highest scored moments.

### 5.4 render
Pure FFmpeg driven by `Plan` + template YAML. Steps: cut segments -> scale/crop to 1080x1920 -> concat -> burn text (ASS subtitles) -> brand accent bar + business name -> music mix with ducking -> encode H.264 (CRF ~23, preset veryfast), AAC 128k, `-movflags +faststart`, target < 16 MB (re-encode with lower bitrate if over).

### 5.5 quality
Runs gates in `docs/QUALITY_GATES.md`. Returns a `QualityReport`. Auto-fix loop (max 2) calls back into plan/render with a specific fix instruction.

### 5.6 revise
Owner text -> LLM -> `RevisionRequest` (schema below). Apply minimal re-run: price/text change -> re-plan text only + render; "shorter" -> reduce target duration by ~25% + render; "different hook" -> regenerate hook only + render. Max 3 revisions.

## 6. Pydantic schemas (authoritative)
```python
class Moment(BaseModel):
    t_start: float; t_end: float
    appeal: int          # 1-10, how appetising/engaging
    sharpness: int       # 1-10
    lighting: int        # 1-10
    has_food: bool; has_person: bool
    tag: str             # e.g. "steam close-up", "cheese pull", "plating"
class ClipAnalysis(BaseModel):
    clip_id: int
    moments: list[Moment]
    overall_note: str    # one sentence, e.g. "dark and shaky"

class Segment(BaseModel):
    clip_id: int; start: float; end: float   # seconds in source clip
class Plan(BaseModel):
    template: Literal["offer","new_dish","behind_the_scenes"]
    target_duration_s: float                 # 10-20
    segments: list[Segment]                  # ordered
    hook_text: str                           # max 6 words
    on_screen_lines: list[str]               # max 4 lines, each max 7 words
    offer_text: str | None                   # only if owner gave an offer
    price_inr: int | None
    call_to_action: str                      # max 8 words
    caption: str                             # max 300 chars
    hashtags: list[str]                      # 5-8
    language: Literal["hinglish","hindi","english"]

class RevisionRequest(BaseModel):
    price_inr: int | None = None
    shorter: bool = False
    longer: bool = False
    regenerate_hook: bool = False
    text_change: str | None = None
    approve: bool = False
    cancel: bool = False
    unclear: bool = False

class MenuExtraction(BaseModel):
    items: list[dict]   # {"name": str, "price_inr": int|None}
    uncertain: list[str]
```

## 7. Config / env (see .env.example)
`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL_VISION`, `LLM_MODEL_TEXT`, `DATABASE_URL`, `REDIS_URL`, `STORAGE_BACKEND`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `PUBLIC_BASE_URL`, `ADMIN_TOKEN`, `MONTHLY_VIDEO_LIMIT=10`, `USD_INR=85`.
The LLM client must be provider-agnostic (interface with `generate_json(prompt, schema, images=None)`), with one implementation to start. Keep model names in env only.

## 8. Security & privacy
- Verify Twilio/Meta webhook signatures. Admin page protected by `ADMIN_TOKEN`.
- Store only: phone number, business info, uploaded media. Provide a `scripts/delete_business.py`.
- Never log full phone numbers (mask to last 4 digits) or API keys.
- Reject media larger than 50 MB or longer than 60 s per clip with a friendly message.

## 9. Performance targets
- Webhook response < 1 s.
- Analyse 3 clips < 40 s; plan < 15 s; render < 60 s; total < 3 min on a 2-vCPU server.
- Log timings per step in `cost_log`.
