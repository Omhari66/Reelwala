# PRD: Reelwala (MVP)

## 1. Summary
Reelwala is a WhatsApp service. A small food-business owner sends 2-5 short phone clips plus one line of text. In about 3 minutes they get back a finished 10-20 second vertical (1080x1920) Reel preview with caption and hashtags. They reply "ok" to approve or ask for a quick change. They then post it themselves.

**One-line promise:** "Send your clips on WhatsApp, get a ready Reel back in minutes."

## 2. Problem
Owners of momo stalls, cafés, and small restaurants know Instagram can bring customers, but do not have the time or skill to film, edit, caption, and post consistently. Existing tools (CapCut, InShot, Canva) are free but still need effort and decisions. The customer is buying *convenience and consistency*, not AI.

## 3. Target user (launch niche)
Owner-operators of small food businesses near one college campus (India). Low patience for apps, uses WhatsApp all day, language: Hinglish, Hindi, or English. Phone footage is often shaky, noisy, and badly lit.

## 4. Scope
### In scope (MVP)
- WhatsApp chat interface (Twilio sandbox first; Meta Cloud API later behind the same interface)
- Chat onboarding: business name, category, language, landmark, brand colour
- Menu capture from typed list or photo (vision LLM), confirmed by owner
- Guided shot list sent before filming
- Clip analysis (low-res frames + deterministic metrics)
- One structured LLM planning call -> hook, on-screen lines, caption, hashtags, template, clip order
- 3 fixed templates: `offer`, `new_dish`, `behind_the_scenes`
- FFmpeg rendering with burned-in captions, brand accent, royalty-free music
- Deterministic quality gates (see QUALITY_GATES.md)
- Approval and revisions via chat (max 3 revisions per campaign)
- Persistent jobs with retries; simple admin page listing jobs
- Monthly usage limit per business (default 10 videos)
- Cost logging per campaign (tokens, render seconds, estimated INR)
- Local CLI to run the pipeline without WhatsApp

### Out of scope (do NOT build)
Instagram/Facebook publishing, content calendar, research/competitor agents, AI-generated video or avatars, AI voiceover/TTS, payments/billing, multi-platform support, web dashboard for owners, user accounts/passwords.

## 5. Key user stories
1. As an owner, I answer 4 setup questions in chat once and never retype business info.
2. As an owner, I send a photo of my menu; the system reads items and prices; I just confirm.
3. As an owner, if I send no clips, I get a simple shot list telling me what to film.
4. As an owner, I send clips and a line like "New momo combo Rs 99 for college students" and get a preview in ~3 minutes.
5. As an owner, I reply "ok" to approve, or "price 129", "shorter", "different hook" to revise.
6. As an owner, I never receive a video with a wrong price.
7. As an owner, if my footage is too poor, I am told honestly and given a specific filming tip.
8. As the operator (founder), I can see every campaign, its state, errors, and cost.

## 6. Engagement requirements (what "good output" means)
- Hook text visible within the first 2 seconds, over the most appetising moment (steam, cheese pull, sizzle, close-up).
- Shots change every 1-2 seconds; total 10-20 seconds (default 15).
- Large, high-contrast captions readable with sound off, inside safe margins.
- The offer or craving leads (price, discount, "only till 8 PM") but ONLY if the owner provided it.
- Exactly one call to action (e.g. "Aaj hi aao, [landmark] ke paas").
- Ending visually loops back to the opening shot.
- Real footage only. No stock footage in MVP.
- Royalty-free background music, low volume, ducked under any speech.

## 7. Success metrics (log from day one)
- Time to first preview (target <= 3 min for 3 clips of 5-10s)
- First-pass approval rate
- Revisions per approved video
- Cost per approved video (INR)
- Quality-gate failure rate by gate
- Repeat usage (second video within 7 days)

## 8. Acceptance criteria
- 3 clips sent on WhatsApp -> preview in under 3 minutes.
- Video has hook text in first 2s, burned-in captions, correct price, brand colour, plays on a phone, under 16 MB.
- A wrong price is never delivered unflagged.
- A failed pipeline step retries without restarting the job.
- "shorter" and "price 129" each produce a corrected preview.
- All tests pass; README lets a new developer run the system in under 15 minutes.

## 9. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Bad raw footage | Shot list; quality gates; honest feedback with a specific tip |
| Robotic Hinglish | Short text only; no TTS in MVP; prompts enforce simple natural Hinglish |
| Wrong facts in ad | Price/item validator in code; LLM may only use profile facts |
| Cost per video too high | Low-res frames, one planning call, cost logging, usage limits |
| WhatsApp limits (24h session window, 16 MB media) | Compress output; handle in provider layer |
| Music licensing | Only tracks in `assets/music`, each listed in `assets/music/LICENSES.md` |
