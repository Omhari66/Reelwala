You are the lead engineer building the MVP "Reelwala" (codename CreatorOps) in this repository.

This repo already contains the full specification. Your operating rules are in GEMINI.md (also AGENTS.md). Read these files fully, in this order, before writing any code:
1. GEMINI.md
2. docs/PRD.md
3. docs/ARCHITECTURE.md
4. docs/TASKS.md
5. docs/QUALITY_GATES.md
6. docs/CONVERSATION_FLOW.md
7. templates/*.yaml and app/llm/prompts/*.md

Then:
1. Reply with a 10-line summary of what you will build and any assumptions (also record assumptions in docs/DECISIONS.md). Do not ask more than 3 questions, and only if truly blocking.
2. Start at the first unticked task in docs/TASKS.md (T1.1).
3. Work ONE task at a time. For each task: give a 5-line plan, implement, run the "Done when" checks, show real command output, tick the box in docs/TASKS.md, append a line to docs/PROGRESS.md, then continue to the next task.
4. Stop and wait for me at T2.8 (video review) and at the end of each milestone. Show me what I can run to verify it myself.
5. Follow the out-of-scope list in docs/PRD.md strictly. Do not add features, publishing, dashboards, or AI-generated video.
6. Use facts only from the business profile or owner message in any generated ad text. Price validation and all measurements must be done by code, never by the LLM.
7. If you hit the same error twice, stop and report: what you tried, exact error, hypothesis. Do not rewrite unrelated files.

Start now with step 1.
