# Sales-Agent Storyline Test — Results (2026-06-09)

Live multi-turn conversation driven through the full app (`web :3100` → Rasa → SSE
`/answer/stream`), single session, against the whole KB (`documentIds: []`). Model:
`llama3.2:3b` on CPU. Driver: `scripts/storyline_test.py`.

## Transcript

**[1] CUSTOMER: Hi there!**
> AURA: Hi, I'm Aura — your solutions architect. Ask me a technical question about the product, or say you'd like to open a support ticket. *(0s)*

**[2] CUSTOMER: I'm shopping for a new smartwatch, what have you got?**
> AURA: I'm not sure I understood. Could you rephrase your technical question? *(0s)*

**[3] CUSTOMER: Tell me about the Galaxy Watch 8**
> AURA: You're interested in learning more about the Samsung Galaxy Watch 8? Well, let me tell you - this watch is a game-changer! ... new "cushion" case ... up to 3000 nits ... antioxidant index and vascular load ... Wear OS 6/One UI 8 ... three options: 40mm, 44mm, classic 46mm. Shall I show you some of our Galaxy Watch 8 models? *(282s)*

**[4] CUSTOMER: How is it different from the Watch 7?**
> AURA: ... new "cushion" case (Watch 7 had a traditional round case) ... Watch 8 up to 3000 nits vs Watch 7 2000 nits ... Antioxidant Index and Vascular Load ... Wear OS 6/One UI 8 ... three models incl. premium Classic with rotating bezel. So which one would you like to try? *(297s)*

**[5] CUSTOMER: What size displays does the 44mm have?**
> AURA: The Samsung Galaxy Watch **7** series is available in two sizes... For the 44mm, display is 1.5 inches (480 x 480) ... 44.4 x 46.0 x 9.7 mm, ~33.8 g, 425mAh. *(150s)*

**[6] CUSTOMER: Does the Classic have a rotating bezel?**
> AURA: The Samsung Galaxy Watch 8 Classic has a rotating physical bezel! ... 46mm ... game-changer for you ... *(134s)*

**[7] CUSTOMER: Which one would you recommend for everyday use?**
> AURA: I'd recommend the Galaxy Watch 8 Classic (46mm) with rotating bezel ... 1.34" (438x438) ... up to 3000 nits ... antioxidant index and vascular load ... black and white ... if I had to pick just one, go with the Galaxy Watch 8 Classic. Shall we discuss pricing and availability? *(188s)*

**[8] CUSTOMER: Great, how do I place an order?**
> AURA: ... *[HALLUCINATION — answered about a NEWS-CMS product]* "custom publish date & time ... manual ordering for latest headline, trending now, breaking news ... drag-and-drop ordering ... articles tab ... breaking news auto-scroll, multi-language content..." *(139s)*

## Findings

1. **Sales persona works (turns 3,4,6,7).** Enthusiastic, benefit-led, real specs only, ends
   with a closing nudge. No "according to the context" leakage. Goal met.

2. **Rasa canned replies still old persona (turns 1,2).** Greeting + NLU fallback come from
   Rasa `domain.yml` `utter_` templates ("solutions architect", "rephrase your technical
   question") — untouched by the `answer.py` persona change. Fix: update domain responses.

3. **Routing gap (turn 2).** Casual sales opener ("what have you got?") doesn't match a
   tech-query intent → fallback, never reaches RAG. Broaden Rasa NLU / intents for
   shopping-style phrasing.

4. **Product drift on ambiguous query (turn 5).** "the 44mm" with no model name retrieved
   **Watch 7** chunks, so the agent answered for Watch 7 (1.5"/480) instead of Watch 8.
   Retrieval has no conversation-context carry-over; pronoun/implicit-subject queries pull
   whichever doc scores highest.

5. **Cross-document hallucination (turn 8) — most serious.** "how do I place an order?"
   matched "manual **ordering** / article ordering / publish date" chunks from a *different
   document in the KB* (a news-CMS product spec) and the agent confidently pitched that
   product. With `documentIds: []` retrieval spans the whole KB; the word "order" out-scored
   anything watch-related. Mitigations: scope retrieval to the watch doc via `documentIds`,
   raise `RETRIEVAL_MIN_SCORE`, or add an off-topic guard.

## Environment notes
- `llama3.2:3b` CPU-only: ~130–300s per uncached answer (turn 3 cold = 282s).
- rtk hook mangles streaming `curl`; this test used Python over the SSE stream.
