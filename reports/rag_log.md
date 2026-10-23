# RAG experiment log

**2026-10-23:** Renamed WinBack AI -> Dimaagi Cart in v0.3.2 (name already used by another company).

## Phase 2 at a glance

| Part | Final setup |
|---|---|
| Generation (why summaries + campaign kits) | `gemini-3.8-flash`, hybrid + rerank retrieval |
| Assistant chat | `gemini-3.5-flash-lite`, hybrid retrieval |
| Judge / relevance labeller | `gemini-3.5-flash-lite` |
| Embeddings | BGE-small (local) |
| Knowledge bases | 25,000 reviews; 11 trend reports, 371 chunks |

| Headline result | Value |
|---|---|
| Retrieval (45 queries) | MRR@10 0.767 → 0.844, P@5 0.591 → 0.738 |
| Why-summary category coverage | 5/9 → 8/9 |
| Campaign kits, human review (1–5) | 3.6 → 4.2 |
| Assistant chat | Routing 100%, citation validity 100% |
| Faithfulness (human-reviewed) | 97% over 229 claims |
| Tests | 24 offline tests (`pytest`), no API key needed |

Days below are in order. Original results are kept, including grades that were later corrected; corrections are marked in place.

## Day 1: Segments

At-risk segments and lapsed categories come from Phase 1: see [findings.md](findings.md), Finding 8 (milk and bread dropped 4–10× more often by at-risk regulars than healthy ones; $8,812/week at risk; the 34 high-value customers hold 29%).

## Day 2: Reviews knowledge base and issue tagging

### Knowledge base: grocery store reviews (Yelp Open Dataset)
- Source: 6.99M Yelp reviews → 3,139 businesses in the "Grocery" category → 124,325 reviews
- Sample: 25,000 reviews (12,000 negative / 5,000 neutral / 8,000 positive), 2,915 stores, 14 states, 2005–2022
- Cleaning: removed reviews under 25 words and duplicates
- Data stays local (gitignored) per Yelp's terms

### Issue tagging
| # | Method | Tag | Precision (10 hand-checked negative reviews) | Main error |
|---|---|---|---|---|
| 1 | Keywords | price_value | 8/10 | Missed context |
| 1 | Keywords | staff_service | 7/10 | "service" matched delivery services |
| 1 | Keywords | stock_availability | 7/10 | Phrase used in passing; "stock person" |
| 1 | Keywords | freshness_quality | 6/10 | "quality of service" matched "quality" |
| 1 | Keywords | checkout_wait | 5/10 | "line" in "bottom line"; general rants |
| | **Keywords (average)** | | **6.6/10 (66%)** | Can't read context or negation; reviews mix several issues |

Gemini aspect-based tagging (see Future work).

### Complaint drivers (keyword tags, negative vs positive reviews)
| Issue | Negative | Positive | Lift | Reading |
|---|---|---|---|---|
| Stock availability | 4.3% | 1.5% | 2.8× | Complaint driver |
| Cleanliness | 7.4% | 3.0% | 2.5× | Complaint driver |
| Delivery/online | 5.5% | 2.5% | 2.2× | Complaint driver |
| Checkout/wait | 30.7% | 15.0% | 2.0× | Complaint driver |
| Staff/service | 58.2% | 42.3% | 1.4× | Mentioned both ways |
| Convenience | 21.1% | 20.3% | 1.0× | Neutral |
| Price/value | 24.8% | 29.4% | 0.8× | Praised more |
| Freshness/quality | 17.9% | 28.0% | 0.6× | Praised more |
| Selection/variety | 12.6% | 32.3% | 0.4× | Praised more |

### Notable quotes (link to Findings 8 and 9)
- "I stopped in for just milk and bread. There was literally one loaf of bread on the shelves."
- "They almost never have anything in stock that I buy… I now do most my shopping elsewhere."
- "A lot of the produce is rotten or out of stock… I go to Publix now, much happier!"
- "Just raised all the prices for no apparent reason… I guess that means less visit to Whole Foods."

## Day 3: Embeddings and first retrieval

### Embeddings
| # | Model | Reviews embedded | Notes |
|---|---|---|---|
| 1 | Gemini gemini-embedding-001 (768d), free tier | 1,000 | Hit the free-tier daily limit (~1,000 embeddings/day); 25K would take ~25 days |
| 2 | BGE-small-en-v1.5 (384d), local via fastembed | 25,000 | Free, offline, no rate limits, no PyTorch; Gemini kept for generation only |

Bug fixed: a cached batch from the 2,000-review test held only 16 embeddings and was reused in the full run (984 vs 1,000). Cache now checks batch size before reuse.

Gemini vs BGE-small retrieval comparison (see Future work).

### Retrieval: vector search (BGE-small, ChromaDB)
| Query | 2,000 indexed | 25,000 indexed | Notes |
|---|---|---|---|
| "milk and bread always out of stock" | 2/5 | 5/5 | Knowledge-base size mattered more than the method |
| "bread was stale and moldy" | — | 5/5 | |
| "waited forever, only one register open" | — | 5/5 | |
| "produce goes bad the next day" | — | 5/5 | |
| "prices went up so I shop somewhere else now" | — | 3/5 | Two-part query (cause + switching) is the weak spot |
| **Total** | | **23/25 (92%)** | Informal check; formal labelled set with Hit@5/MRR on Day 6 |

Pattern: single-concept queries near-perfect; two-part queries weaker. Motivates hybrid search (BM25) and reranking on Day 6.

## Day 4: Trend reports knowledge base

**Setup:** 10 public marketing reports (2025–2026), about 1,500-character chunks with 200 overlap, page-level citations. 396 chunks after cleaning. Local BGE-small embeddings, ChromaDB collection `trends`.

**Test queries (graded by hand: how many of the top 5 are relevant):**
1. Win-back: "win back lapsed customers re-engagement campaign"
2. Loyalty: "loyalty program rewards retention"
3. SMS: "SMS marketing text message best practices"
4. Social: "social media content that drives engagement"

| Run | Change | Win-back | Loyalty | SMS | Social | Total | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Baseline (plain vector search) | 1/5 | 5/5 | 4/5 | 5/5 | **15/20** | Most queries returned 3–5 chunks from one report. Some chunks were number-only tables or slide boilerplate ("Click to edit Master title style"). No report is mainly about win-back |
| 2 | Boilerplate cleaning + max 2 results per report | 3/5 | 5/5 | 5/5 | 4/5 | **17/20** | Slide boilerplate gone; 3–4 reports per query instead of 1–2. Trade-off: social lost 1 point when Sprout was capped. Win-back is still weak: no report is mainly about win-back (content gap → Fix 3) |
| 3 | Added win-back playbook (MailGenius 2026) + web-page cleaning (cut after "Recent Posts", drop links and site menus) | **5/5** | 5/5 | 5/5 | 4/5 | **19/20** | Playbook ranks #2 and #4 for win-back. 379 chunks (shorter pages once links were removed). The source is a vendor blog: use it for tactics, not statistics |

Final state (after the Day 7 skip-page fix): 11 reports, 371 chunks.

**Lessons so far**
- Read your chunks before trusting search: leftover slide-template text ranked high and pushed out real content.
- A source cap improves variety but can cost precision when one report really is the best source (social, run 2).
- Some gaps are about content, not the algorithm: no amount of tuning finds a win-back guide that isn't in the knowledge base.
- Distances are only comparable within one index setting: switching from L2 to cosine halved every distance with no change in ranking. Grade relevance, not distance.
- The biggest gain (win-back 3/5 → 5/5) came from adding the right content, not from tuning the algorithm.

## Day 5: First end-to-end "why" summaries

**Evidence check (dry run, before Gemini):** 12 reviews per segment from category queries (top 3 lapsed categories) + theme queries.

| Run | Change | Core · Basket | Core · Visiting | High-value | Useful overall |
|---|---|---|---|---|---|
| 1 | Category + theme queries, ≤3★ filter | 9/12 | 10/12 | 9/12 | 28/36 (78%) |
| 2 | + distance cut-off 0.48 + everyday category words ("bread", "milk") | | | | not measured separately: superseded by Day 6 hybrid retrieval |

**Observations**
- Yelp's "Grocery" category includes department stores (Target): clothing complaints slipped in, always at the highest distances (0.50+).
- All segments lapsed on milk and bread, so they share evidence. Segments are told apart by reason (visiting less vs basket changed) and by facts, not by product.

**Generation model:** `gemini-3.8-flash` (pinned version, set in .env; `gemini-2.5-flash` returned 404 even though it was still listed)

**Generation results (run 1, `gemini-3.8-flash`, temperature 0.2):**

| Segment | Reasons | Citation validity | Faithful (manual) | Latency |
|---|---|---|---|---|
| Core · Basket changed | 3 | 100% | 2/3 | 43.7s |
| Core · Visiting less | 4 | 100% | 3/4 | 19.6s |
| High-value · at risk | 4 | 100% | 3/4 | 22.9s |
| **Total** | 11 | **100%** | **8/11 (73%)** | |

- All numbers match segments.json ($8,812/week total; the 34 high-value customers hold 29%). No invented numbers.
- **Citation validity ≠ faithfulness:** all 3 unfaithful reasons cited real review IDs, but the reviews were about sandwiches, not packaged bread. The evidence was about sandwiches, and the model added a detail ("hard") the reviews didn't contain ("stale" was in one sandwich review).
- Root cause is retrieval: Yelp reviewers rarely discuss packaged bread or canned soup, so these categories pull deli and prepared-food reviews.
- Core · Basket and High-value got nearly identical reasons: High-value needs value-specific queries (service, premium quality, recognition).

**Next:** run 2 = stricter prompt (flag prepared-food evidence, no added details, no "often" without 3+ reviews). Day 6 = hybrid search + reranking to fix the retrieval gap; Day 9 = automated faithfulness judge.

**Generation run 2 (Flash, stricter prompt):**

| Segment | Reasons | Citation validity | Faithful (manual) | Categories explained | Latency |
|---|---|---|---|---|---|
| Core · Basket changed | 3 | 100% | 3/3 | 2/3 (milk, cheese; bread flagged as sandwich evidence) | 59.8s |
| Core · Visiting less | 3 | 100% | 3/3 | 2/3 (milk, cheese; bread flagged) | 65.3s |
| High-value · at risk | 3 | 100% | 2/3 (price reason rested on a single review, graded from a preview: unverified) | 1/3 (milk; bread and soup flagged as prepared food) | 89.1s |
| **Total** | 9 | **100%** | **8/9 (89%)** | **5/9** (bread and soup flagged as prepared-food evidence in evidence_gaps) | |

- The model now abstained instead of using sandwich reviews.
- The one weak reason (High-value price, single review) was graded from a 160-char preview, so it's unverified (see Day 6 grading correction).

## Day 6: Hybrid search, reranking and retrieval eval

**Goal:** fix the Day 5 retrieval gap (bread pulled sandwich reviews) and *prove* which retrieval method works best, with numbers.

### What was built
| Component | File | What it does |
|---|---|---|
| BM25 keyword search | `src/rag/hybrid.py` | Exact-word matching weighted by word rarity; index built once over 25,000 reviews and cached |
| Hybrid (RRF) | `src/rag/hybrid.py` | Merges vector + BM25 rankings: score = Σ 1/(60 + rank). Uses ranks, so no incompatible score scales |
| Reranker | `src/rag/hybrid.py` | Local cross-encoder (`ms-marco-MiniLM-L-6-v2`, ~80 MB) re-sorts the top 30 hybrid results by reading query + review together |
| Shared Gemini helper | `src/rag/gemini.py` | JSON output via Pydantic schema, disk cache, retries only on temporary errors, clean stop on daily quota |
| Eval set | `eval/queries.jsonl` | 45 queries: 15 category, 15 issue, 8 theme, 7 hard (packaged bread, canned soup...) |
| Labelling | `eval/build_labels.py` | Pools top-10 from all 4 methods (~20 reviews/query), Gemini judge labels relevance, samples 48 rows for a human spot-check (→ corrected: *up to* 48; 39 in practice, see Judge reliability) |
| Scoring | `eval/run_eval.py` | Hit@5, MRR@10, P@5, latency, by-type breakdown, head-to-head, judge agreement (Cohen's kappa) |

### Sanity check (3 queries, top 5, judged by eye)
| Query | vector | bm25 | hybrid | hybrid_rerank |
|---|---|---|---|---|
| expired milk | 3/5 | 3/5 | 5/5 | 5/5 |
| canned soup, dented cans | 1/5 | 1/5 | 1/5 | 1/5 |
| stale bread loaf (packaged) | 0/5 | 2/5 | 2/5 | 0/5 |

- BM25 found the packaged-bread reviews ("two loaves... started to mold") that vector search missed: exact words like "loaf" carry the grocery-vs-sandwich signal.
- The general-purpose reranker helped for milk but hurt for bread: it judges topic ("stale bread"), not the domain distinction (grocery vs sandwich).

### Retrieval eval (45 queries; top-10 of each method pooled; judged by `gemini-3.5-flash-lite`)
| Method | Hit@5 | MRR@10 | P@5 | ms/query |
|---|---|---|---|---|
| vector (Day 3 baseline) | 0.800 | 0.767 | 0.591 | 82 |
| bm25 | 0.978 | 0.741 | 0.640 | 83 |
| hybrid (RRF) | 0.911 | 0.817 | 0.653 | 124 |
| hybrid + rerank | **0.978** | **0.844** | **0.738** | 1,675 |

**By query type (MRR@10)**
| Type (n) | vector | bm25 | hybrid | hybrid + rerank |
|---|---|---|---|---|
| category (15) | 0.692 | 0.802 | 0.741 | 0.830 |
| issue (15) | 0.867 | 0.708 | 0.867 | 0.902 |
| theme (8) | 0.893 | 0.713 | 1.000 | 0.875 |
| hard (7) | 0.571 | 0.711 | 0.667 | 0.714 |

**Head-to-head vs vector (MRR per query)**
| Method | Wins | Ties | Losses |
|---|---|---|---|
| bm25 | 9 | 27 | 9 |
| hybrid | 9 | 32 | 4 |
| hybrid + rerank | 10 | 30 | 5 |

**Findings**
- Hybrid + rerank is best on every metric: MRR +10%, and 25% more relevant reviews in the top 5 than vector. But it's 20x slower.
- Hybrid alone gives most of the gain (+7% MRR) for almost no extra time: best value.
- BM25 wins **category** queries (exact product words); vector wins **issue** queries (many ways to describe one problem). They fail in opposite places, which is why fusion works.
- BM25 alone is unsafe: 9 wins, 9 losses against vector.
- Honest limit: 30 of 45 queries are ties. On the rest, a sign test gives p ≈ 0.3, so the result is "consistently better", not "proven significant" at n = 45.

### Judge reliability
| Check | Labels | Agreement | Cohen's kappa |
|---|---|---|---|
| Human spot-check vs Lite judge | 39 | 87% (34/39) | 0.73 (substantial) |
| Strong judge (`3.8-flash`) vs Lite | 338 on 16 queries | 70% | 0.44 (moderate) |

*Note: the spot-check sampled 8 queries, with up to 3 relevant and 3 non-relevant reviews each (48 at most). 4 of the 8 queries had fewer than 3 reviews in one group, so 39 rows were sampled, and all 39 were labelled.*

- The strong model is far stricter: it marked 30% of reviews relevant vs Lite's 58%. My hand labels sided with Lite.
- So absolute scores depend on how strict "relevant" is, but the method comparison is fair: all four methods share the same labels.
- How this came about: the first run used `3.8-flash` by accident (`JUDGE_MODEL` wasn't read from `.env`) and hit the daily quota after 16 queries. All 45 were then re-judged with Lite for consistency, and the 16 double-judged queries became a second reliability check.

### Decision
- **Generation:** hybrid + rerank (batch job, quality matters; adds ~10s against ~60s of Gemini time).
- **Assistant chat (later):** hybrid (0.12s, most of the gain).
- Configurable with `RETRIEVAL_METHOD` in `.env`.

### Plugging hybrid + rerank into generation (dry runs, before Gemini)
| Run | Change | Category evidence (useful / shown) | Notes |
|---|---|---|---|
| A | hybrid + rerank, long query template | 2/7 | Bread ✅ (first real grocery-bread review). Milk, cheese and soup got generic rants: the reranker rewards reviews matching MORE of a long query ("not fresh, poor quality, overpriced or out of stock") |
| B | + product word first and twice, + review must name the product, + rerank ≥ 1.0, + fetch 20 per query | 4/5 | Milk "always expired" and cheese "molding" back. Soup has 0 evidence, correctly (content gap) |

- Reranking won the eval on **short** queries, but generation uses **long templates**. Retrieval quality depends on query style, so future eval sets should include app-style queries.
- Trade-off: precision up, evidence volume down (1–2 strong reviews per category).

### Generation results (run 3: hybrid + rerank, `gemini-3.5-flash-lite`)
| Segment | Reasons | Citation validity | Faithful (manual) | Categories explained | Latency |
|---|---|---|---|---|---|
| Core · Basket changed | 3 | 100% | 2/3 (added detail: "smelled and tasted rotten") → corrected 3/3 (the full review says "smelled and tasted rotten"; see Grading correction) | 3/3 | 3.8s |
| Core · Visiting less | 4 | 100% | 4/4 (1 over-citation) | 3/3 | 2.9s |
| High-value · at risk | 3 | 100% | 3/3 (1 duplicate reason) | 2/3 (soup gap flagged) | 2.8s |
| **Total** | 10 | **100%** | **9/10 (90%)** → corrected 10/10, run 2: 89% | **8/9**, run 2: 5/9 | **~3s**, run 2: 60–89s |

- Day 6 retrieval lifted coverage from 5/9 to 8/9: bread now has real grocery evidence in every segment.
- Lite matched Flash on faithfulness at ~20x the speed, with much higher free-tier limits.
- Lite's weaknesses are instruction-following: misused a number ("spending $2,700.75 less" when it's revenue at risk), over-cited, padded with a duplicate reason, ignored the strongest evidence for High-value, and wrote generic gaps.
- Note: model and retrieval both changed from run 2, so this isn't a clean model comparison. A same-prompt Flash run is planned.
- Next: run 4 = stricter rules aimed at Lite's weaknesses.

- **Superseded:** **Model choice:** switched generation from `gemini-3.8-flash` (~16 free calls/day, 60–90s per call) to `gemini-3.5-flash-lite` (much higher free limits, faster). Quality to be confirmed with the same faithfulness and coverage checks; a same-prompt Flash vs Lite comparison is planned. → Final decision after the same-prompt comparison: Flash for generation, Lite for chat and judging.

### Still open
- Core · Basket and High-value get identical theme evidence (both "basket changed"). High-value needs its own queries (service, premium quality, feeling valued) → Day 7.
- Canned/packaged soup is a content gap in Yelp grocery reviews for every method.
- Robustness check to do: re-score the 16 double-judged queries with the strict labels and confirm the method ranking holds.
- Add app-style (long template) queries to the eval set.

### Lessons
1. Measure before choosing: the "expensive" method (reranking) won on average but hurt on specific queries.
2. No method wins everywhere; break results down by query type.
3. An LLM judge needs its own validation: human agreement plus a second model.
4. Check what the generator actually receives, not just retrieval metrics.
5. Free-tier quotas are per model. A cache plus a clean stop on quota makes long jobs resumable.

- Run 4 first showed 75% citation validity for Core · Basket. Root cause: a **checker bug**. Lite wrote two refs in one string ("R1, R2"), which the exact-match checker marked invalid. Fixed by extracting every `R<number>` with a regex; validity is 100% with no fabricated citations. Invalid refs now show as ⚠ lines in the report, and a single-citation count was added.

### Generation run 4: stricter rules for Lite (2+ citations, distinct reasons, strongest evidence first, "revenue at risk" defined, specific gaps)
| Segment | Reasons | Validity | Faithful | Single-citation reasons | Categories explained |
|---|---|---|---|---|---|
| Core · Basket changed | 3 | 100% | 2/3 ("tasting rotten" added again) → corrected 3/3 | 3 | 3/3 |
| Core · Visiting less | 3 | 100% | 3/3 | 0 | 3/3 |
| High-value · at risk | 3 | 100% | 3/3 | 1 | 2/3 (soup gap flagged) |
| **Total** | 9 | 100% | **8/9 (89%)** → corrected 9/9 | 4 | **8/9** |

- Fixed: revenue-at-risk misreading, duplicate reasons, over-citation; High-value now uses the out-of-stock evidence.
- Regressed: Core · Basket dropped its strongest theme (out of stock) and went all single-citation; Core · Visiting dropped checkout; gaps generic again; the "rotten" detail persisted despite an explicit rule; one malformed citation ("R1, 7"; checker updated).
- **Lesson: prompt whack-a-mole.** Four prompt rounds left faithfulness flat at 89–90%; each new rule fixed one thing and broke another. Small models can only follow so many rules at once.
- **Decision:** right model for each task. Generation needs only ~3 calls per run, so Flash's small quota is enough (Flash for quality, Lite for bulk judging and chat). Enforce rules in code and automate faithfulness scoring (Day 9) instead of adding more prompt rules.

### Model comparison: same prompt and evidence, only the model changed
| Measure | Lite (`3.5-flash-lite`) | Flash (`3.8-flash`) |
|---|---|---|
| Faithful reasons | 8/9 → corrected 9/9 | 9/10 (1 pending check) → corrected 10/10 (2 minor overstatements, 1 over-citation) |
| Single-citation reasons | 4 | 1 |
| Strongest evidence used | 1/3 segments | 3/3 |
| Specific evidence gaps | 1/3 | 3/3 |
| Categories explained | 8/9 | 8/9 |
| Citation validity | 100% | 100% |
| Latency per segment | 3–5s | 32–55s |
| Free-tier daily quota | High | ~16 calls |

- Flash's flaws: one over-citation (R9 cited for stockouts), and two overstatements ("caused illness" when the reviewer only guessed).
- Both models described the cheese review as "rotten". Grading used a 160-char preview while the models read 600 chars → verify against the full text. Lesson for Day 9: the judge must see exactly what the generator saw.
- One 503 (server overloaded) was retried automatically and succeeded: the retry policy works as designed.
- **Decision: right model for each task.** Flash for generation (quality matters, ~3 calls/run); Lite for bulk judging and chat. Prompt rules hit a ceiling with Lite; the model mattered more than more rules.

**Grading correction.** Both models described the cheese review as "rotten"; I graded it as an invented detail. The full review says "cheese that smelled and tasted rotten": the grader saw a 160-char preview, the models saw 600 chars. Corrected faithfulness: Lite run 3 = 10/10, Lite run 4 = 9/9, Flash = 10/10 (2 minor overstatements, 1 over-citation). Neither model fabricated facts; the real difference is evidence use (strongest evidence, citation depth, specific gaps). Day 5 run 2's single "unsupported" reason was also graded from a preview and is unverified.

Fixes: (1) removed a prompt rule example built on the wrong grading; (2) the report now quotes the full 600 chars the model saw. **Lesson: the grader must see exactly what the generator saw.** This becomes a hard requirement for the Day 9 automated judge.

## Day 7: Campaign kits

- **Dry run bug:** McKinsey's table of contents (p.3) and acknowledgments page (p.37) were retrieved as marketing evidence: keyword-dense, content-free pages matched the reason-specific queries. Fix: skip contents / acknowledgments / reference pages at ingest (379 → 371 chunks); replacements were real content (McKinsey p.22 private-label value, p.14 customer needs; Listrak p.22 in-store traffic).
- **Content gap:** little marketing evidence on communicating freshness or stock fixes → handled by the owner checklist (fix first, then promise).

**Kits v1 (Flash, temperature 0.4):** 100% citation validity, no unsupported numbers, cadence follows the playbook, useful owner checklists.

| Segment | Human review (1–5: relevant, specific, on-brand, actionable, honest) |
|---|---|
| Core · Basket changed | 3.4 |
| Core · Visiting less | 3.8 |
| High-value · at risk | 3.6 |
| **Average** | **3.6** |

*First-pass scores from a single reviewer (AI-assisted review during development), not an independent panel; owner/marketer scores: not yet recorded.*

Problems:
- Unflagged operational claims ("restocked daily", "baking fresh rolls every morning").
- Invented store features (artisan bakery, loyalty members, local bakers).
- High-value offer $15 off $50 against a $70.93 median (threshold below normal spend).
- A headline "guarantee" not explained.
- Creepy data use ("your basket looked lighter in dairy").
- High-value tone reused on Core.
- SMS 162 chars.

Root cause: the model had no facts about the store.

**v2 fixes (inputs and code, not more prompt rules):**
- `config/store_profile.yaml`: what is true about the store.
- Structured offer fields with a code check (min basket > median, discount ≤ 15%).
- SMS length measured with placeholders filled and [CONFIRM] removed.
- Heuristic detector for unflagged claims.
- Prompt rules: no tracking details, no claims in SMS, headline must match details.

| Check | v1 | v2 |
|---|---|---|
| Invented store features | bakery, loyalty, local bakers | none |
| Tracking details revealed | yes | no |
| Claims in SMS | 2/3 | 0/3 |
| SMS ≤ 160 chars at real length | 2/3 | 3/3 |
| Offer economics | 2/3 | 3/3 |
| Human review (1–5) | 3.6 | **4.2** (Core · Basket 4.0, Core · Visiting 4.2, High-value 4.4) |

*v2 scores are also first-pass scores from a single reviewer (AI-assisted review during development), not an independent panel; owner/marketer scores: not yet recorded.*

- High-value now leads with a "staple hold service" + $10 off $75 (13%, above the $70.93 median).

**Checker fixes:**
- Claim detector v1 precision 0/6: it flagged descriptive words like "fresh" and "daily". v2 matches operational actions only, locked in by regression tests built from real outputs.
- The number checker flagged "12.80" vs "12.8" and the 15% rule constant. Fixed by comparing numbers as values and allowing rule constants.
- The regression test caught that the number-normalisation fix hadn't been applied (old `numbers_in` still in the file), before it could reach the kits. Fixed; 3/3 tests pass.

**Still open:**
- A [CONFIRM] claim with no matching checklist action ("expanded bread selection").
- A [LINK] reservation that contradicts `online_ordering: false`.
- The two Core kits are nearly identical.
- Core · Basket's threshold is 2× its median ($20 vs $9.65): an open marketing decision.

Sample output: [sample_campaign_kits.md](sample_campaign_kits.md).

## Day 8: Assistant chat (tool routing)

**Design:** Gemini automatic function calling (`gemini-3.5-flash-lite`, hybrid retrieval) with 5 tools whose docstrings act as routing instructions: list_segments (S refs), get_segment_reasons (R + W refs), search_reviews (R), search_marketing_trends (T), get_campaign_kit (K). Every cited ref is checked in code against refs the tools actually returned.

**Bugs found and fixed while testing:**
| Problem | Cause | Fix |
|---|---|---|
| Follow-up "them" guessed as high-value | One-shot commands have no memory; model guessed instead of asking | Interactive mode keeps context; rule: ask when the segment is ambiguous |
| High-value numbers cited as [S1] = Core · Basket (checker said 100% valid) | Numbered refs (S1/S2/S3) are easy to mix up | Self-describing refs: [S_highvalue], [K_corebasket] |
| Model cited a tool name, "[get_segment_reasons]" | Evidence gaps had no legitimate source to cite | Stricter checker (any non-ref in brackets = invalid) + new W_ ref for the reasons analysis |
| 88–249s per answer | Bare call = 3.3s → transient Google-side stalls | Per-turn timing (model vs tools) + 60s timeout per call; now ~2s |
| q09 validity 67% | "[STORE NAME]" placeholder looked like a citation | Placeholders whitelisted in the checker |
| q06 "complaints are frequent" | Retrieval returns examples, not counts | Rule: search results are examples, not frequency |
| q01/q02 model did its own arithmetic | Totals and shares weren't provided | list_segments returns code-computed totals [S_all], share of revenue at risk, revenue per customer |

**Chat eval (12 questions, fresh conversation each, `gemini-3.5-flash-lite`, hybrid retrieval):**

| Metric | Result | Target |
|---|---|---|
| Routing accuracy | 100% (12/12) | ≥ 90% |
| In-scope answers with citations | 100% | 100% |
| Citation validity | 98% (1 invalid in q09) | 100% |
| Typical latency | ~2s per answer | |

- W_ ref fix worked: evidence gaps now cite [W_highvalue] instead of a tool name.
- Out-of-scope (weather) answered with no tool calls in 0.8s.
- Multi-tool question (q11) called reasons + trends (+ segments for context); one 429 rate limit was retried automatically and succeeded.

**Faithfulness review (manual, 11 in-scope answers): 10/11 (91%).**
- q06 claimed checkout complaints are "frequent": retrieval returns examples, not frequencies. → Rule: search results are examples, not counts. Future tool: count issue tags across all 25k reviews.
- q09's 67% validity was a **checker false positive**: the kit's "[STORE NAME]" placeholder looked like a citation. → Whitelisted placeholders; real validity 100%.
- q01/q02 did their own arithmetic (correct, but risky) and judged "focus first" only by total revenue at risk. → list_segments now returns code-computed totals ([S_all]), share of revenue at risk and revenue at risk per customer.
- q04 inherited an over-citation from the Day 6 why summary: errors flow downstream. → Day 9's faithfulness judge checks the whole pipeline, not only the chat.
- Minor: q05 turned a reviewer's guess ("would explain why I've gotten sick") into a fact; q07 omitted SMS consent.
**Chat eval after fixes:** routing 100%, citations 100%, citation validity 100% (placeholder false alarm fixed). Typical ~2s. A 429 at q11 in both runs = per-minute limit on Lite (~10 questions × 2–3 calls in under a minute); retry succeeded; eval pace raised from 4s to 7s between questions.

**Chat eval summary (12 questions, fresh conversation each):**
| Metric | First run | Final | Target |
|---|---|---|---|
| Routing accuracy | 100% | 100% | ≥ 90% |
| In-scope answers with citations | 100% | 100% | 100% |
| Citation validity | 98% | 100% | 100% |
| Manual faithfulness | 10/11 | 11/11 | |
| Typical latency | ~2s | ~2s | |

*Note: graded on that run's answers. A later run (judged in Day 9–10, run A) produced a q02 answer with swapped segment numbers: run-to-run variance, now caught by the number-grounding check.*

**Findings:**
- **Better inputs beat better prompts:** once list_segments returned value per customer, q02's recommendation flipped from "Core · Basket (biggest total)" to "High-value first ($75.87 per customer)".
- **New ref types get over-used:** W_ became a catch-all in q04 (12 review citations → 2 analysis citations), which loses traceability. Rule added: reasons cite their own R refs; W_ only for gaps.
- **Run-to-run variance:** q05 and q11 gave different (still faithful) answers because the model chose different search queries. A single eval run hides this; measure stability across repeated runs (→ Day 9).
- **Errors flow downstream:** q04/q11 repeated wording from the Day 6 why summaries ("compared to competitors").
- A 429 at q11 in both runs = Lite's per-minute limit; retry succeeded; eval pace raised to 7s.

## Day 9–10: Automated faithfulness judge and wrap-up

**Judge:** `eval/judge.py` (`gemini-3.5-flash-lite`, temperature 0, cached) splits each output into atomic claims and checks each against the exact text AND task the writer had (supported / partial / unsupported). Every flag was then reviewed by hand.

**Judging the judge (human review of all 16 flags):** 7 fair (real overstatements), 7 false flags, 2 real errors under-called.
- The 2 real errors: q02 swapped per-segment numbers ($12.98 attributed to the wrong segment; median labelled as per-customer value), with "100% valid" citations. Valid ≠ correct, a third time; caused by run-to-run variance.
- False flags came from the judge not knowing the writer's task: it penalised the hedged synthesis the why summary was asked to do, and our required "other stores" proxy framing.
- Judge precision on flags: 9/16 (56%). It also under-called severity (wrong numbers marked partial).
- Human-reviewed faithfulness: 95% (110 claims: 101 supported, 7 partial, 2 unsupported).
- Lesson: the grader needs the writer's sources AND task. Fixes: judge prompt gets a per-type task block and a severity rule; chat gets a code-level number-grounding check that would have caught q02.
- Number-grounding check: the spec "number must appear in a ref cited in the same sentence" passed the real q02 error, because that bullet cited all three segments. Changed to "check each number against the first citation after it" (fallback: all refs in the sentence; no citation = ungrounded). It now flags q02's swapped $12.98 and q09's uncited SMS quote ($3/$20), which is correct but uncited. Lesson: test a check against the real failure, not just the spec. 23 tests pass. *(→ The q09 flag was later found to be a checker false positive; see below.)*
- Known noise: small numbers ("day 7", "3 reasons") get flagged when no cited source contains them.

| Run | Claims | Supported | Partial | Unsupported | Faithfulness (human-reviewed) |
|---|---|---|---|---|---|
| A (judge v1) | 110 | 101 | 7 | 2 | 95% |
| B (judge v2, final) | 119 | 116 | 3 | 0 | 99% |
| **Both** | **229** | 217 | 10 | 2 | **97%** |

Run B by type: why summaries 95% (31 claims), campaign kits 100% (30), chat answers 100% (58).

**Judging the judge**
| | Judge v1 (sources only) | Judge v2 (+ writer's task, severity rule) |
|---|---|---|
| Flags that were real issues | 9/16 (56%) | 3/5 (60%) |
| False flags | 7 (hedged synthesis, proxy framing, segment facts) | 2 (uncited headline summaries) |
| Severity | Too lenient (wrong numbers = "partial") | Too strict (certainty words = "unsupported") |

- The only real unsupported claims were in run A: q02 attributed $12.98 to the wrong segment and labelled the median as per-customer value, with "100% valid" citations. Valid ≠ correct (third time). A code-level number-grounding check (each number vs the citation right after it) now catches this automatically.
- All remaining issues are one type: certainty the sources don't give ("will quickly", "will switch", "directly"). Next fix target for the why prompt.
- The judge's claim extraction varies between runs (q01: 4 → 14 claims), so scores move with how it splits text.
- **Conclusion:** the automated judge is a good flagger, not a final referee; human review of its flags gives the trustworthy number. Future: a stronger judge model, or few-shot calibration using these human-reviewed flags.
- Final chat eval: routing 100%, citation validity 100%, numbers grounded 92% (1 answer), mean latency 2.9s.
- The q09 "ungrounded" numbers ($3/$20) were a **checker false positive**: a quoted SMS with its own full stops was split away from the bullet's trailing [K_corevisiting]. Fixed by treating each bullet as one unit. Re-scoring the saved `models/chat_eval_results.json` offline with the current check (no Gemini calls): **numbers grounded 100% (12/12)**. `reports/chat_eval.md` still shows 92% until the chat eval is re-run.
- **Clean-install test:** `requirements.txt` was UTF-16 and missing 6 Phase 2 libraries (chromadb, fastembed, google-genai, pydantic, pypdf, python-dotenv); `pillow==13.0.0` conflicted with fastembed (needs pillow<13 on Python 3.13). Fixed and verified in a throwaway venv: fresh install, all imports, and all 24 tests pass. `.env.example` now lists all 6 settings (`JUDGE_MODEL` also drives relevance labelling; the labels were made and human-validated with Flash-Lite).

**Phase 2 status: done.** Next: Phase 3, the desktop app (Electron UI + FastAPI backend).

- Theme bug fixed: generate.theme() now reads reason_mix from segments.json. High-value (59% visiting less) was
  previously generated with "basket changed" queries. Regenerated High-value why summary + kit with the correct theme:
  reasons now checkout delays, pricing, stockouts, bread (was stockouts, bread, milk); offer perk now "priority
  checkout service" + $10 off $75. Judge (raw): 15/15 supported (was 8 claims, 81%). Segment-only regenerate now
  merges into the existing files (Claude Code caught that it previously deleted the other segments' outputs).
- Open: High-value and Core · Visiting less now share "visiting less" queries and similar reasons; value-specific
  queries remain future work.

## Future work (not done in Phase 2)

| Item | Status |
|---|---|
| Gemini aspect-based tagging (complaint vs praise), compared with the 66% keyword baseline on the same hand-checked reviews | Not done |
| Gemini vs BGE-small embedding comparison on the same 1,000 reviews | Not done |
| Re-score the 16 double-judged queries with the strict labels (robustness of the method ranking) | Not done |
| App-style (long template) queries in the retrieval eval | Not done |
| Chat stability across repeated runs (`run_chat_eval --repeats`: built, not yet run) | Not done |
| Complaint-frequency tool that counts issue tags across all 25k reviews | Not done |
| High-value-specific why queries (service, premium quality, recognition) | Not done |
| Stricter why prompt for certainty words ("will", "directly") | Not done |
| Stronger or few-shot-calibrated judge | Not done |
| Day 7: [CONFIRM] claim with no matching checklist action ("expanded bread selection") | Not done |
| Day 7: [LINK] reservation that contradicts `online_ordering: false` | Not done |
| Day 7: the two Core kits are nearly identical | Not done |
| Day 7: Core · Basket's threshold is 2× its median ($20 vs $9.65), an open marketing decision | Not done |

