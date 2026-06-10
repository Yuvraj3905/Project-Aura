# Sales-Agent Storyline Test — Results

Live multi-turn conversation driven through the full app (`web :3100` → Rasa → SSE
`/answer/stream`), single session, whole-KB retrieval (no manual doc selection).
Model: `llama3.2:3b` on CPU. Driver: `scripts/storyline_test.py` (asserting
regression suite — exit 1 on any failed check).

## 2026-06-10 — Phase 1 fixes: PASS (8/8 turns)

After: sticky per-session doc scope (lock to strongly-cited docs, relock bar 0.60),
salesy Rasa persona, shopping/buy intents routed to RAG.

**[1] Hi there!** → "Hey there! Welcome — I'm Aura, your personal product specialist…" *(0s — new persona ✓)*

**[2] I'm shopping for a new smartwatch, what have you got?** → full Watch 8 vs 7 sales
pitch with real specs, closes with "Which of these options sounds most appealing…"
*(218s — shopping intent routed to RAG ✓, no fallback)*

**[3] Tell me about the Galaxy Watch 8** → cushion design, 3000 nits, health sensors,
Wear OS 6 + Gemini, size question close. *(141s)*

**[4] How is it different from the Watch 7?** → 3000 vs 2000 nits, round vs cushion
case, Classic bezel, Wear OS 6 vs 5. *(139s)*

**[5] What size display does the 44mm Watch 8 have?** → **"1.47 inches (480 x 480)"**
*(85s — correct Watch 8 spec; pre-fix this drifted to the Watch 7's 1.5" ✓ sticky scope)*

**[6] Does the Classic have a rotating bezel?** → "…has a rotating physical bezel!
…46mm size…" *(91s)*

**[7] Which one would you recommend for everyday use?** → recommends Watch 8 Classic
46mm with reasons, invites next step. *(117s)*

**[8] Great, how do I place an order?** → "Great question! I don't have those exact
details on hand right this second, but I'd love to track them down for you…"
*(0s — guardrail fired, NO LLM call; pre-fix this pitched the news-CMS doc ✓)*

Post-run Redis scope for the session: `["fc775c7a…"]` — the watch PDF only.
Unit tests: 30/30 pass (`docker compose run --rm --no-deps --entrypoint pytest ml-service tests/`).

### Assertions enforced per turn
- No meta phrases anywhere ("according to the context", "knowledge base", "the document"…).
- Turn 1 not the old "solutions architect" greeting; turn 2 not the old fallback.
- Turn 5 must contain "1.47" (Watch 8 44mm), catching Watch-7 drift.
- Turn 8 must not contain news-CMS terms (article/headline/publish/breaking news).

## History

### 2026-06-09 — initial run (pre-fix): 4 defects found
1. Rasa canned replies used the old "solutions architect" persona (turns 1–2).
2. "what have you got?" hit the NLU fallback — shopping openers unrouted.
3. "the 44mm" drifted to Watch 7 specs (no conversation scope).
4. "how do I place an order?" answered from an unrelated news-CMS document
   (cross-doc hallucination — most serious).

### 2026-06-10 — first fix attempt: FAIL (3 assertions, turn 8)
Scope locked to ALL cited docs; a 0.546 tail chunk smuggled the news-CMS doc into
scope, so turn 8 still pitched it. Fixed by restricting the lock to docs with a chunk
≥ relock score (0.60), top doc always kept (`_lock_docs` in `app/rag/answer.py`).

## Environment notes
- `llama3.2:3b` CPU-only: ~85–220s per uncached answer; guardrail/cached turns ~0s.
- rtk hook mangles streaming `curl`; drive SSE tests with Python.
