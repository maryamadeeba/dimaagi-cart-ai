# RAG experiment log

## Knowledge base: grocery store reviews (Yelp Open Dataset)
- Source: 6.99M Yelp reviews → 3,139 businesses in the "Grocery" category → 124,325 reviews
- Sample: 25,000 reviews (12,000 negative / 5,000 neutral / 8,000 positive), 2,915 stores, 14 states, 2005–2022
- Cleaning: removed reviews under 25 words and duplicates
- Data stays local (gitignored) per Yelp's terms

## Issue tagging
| # | Method | Tag | Precision (10 hand-checked negative reviews) | Main error |
|---|---|---|---|---|
| 1 | Keywords | price_value | 8/10 | Missed context |
| 1 | Keywords | staff_service | 7/10 | "service" matched delivery services |
| 1 | Keywords | stock_availability | 7/10 | Phrase used in passing; "stock person" |
| 1 | Keywords | freshness_quality | 6/10 | "quality of service" matched "quality" |
| 1 | Keywords | checkout_wait | 5/10 | "line" in "bottom line"; general rants |
| | **Keywords (average)** | | **6.6/10 (66%)** | Can't read context or negation; reviews mix several issues |

Planned: Gemini aspect-based tagging (complaint vs praise), compared on the same hand-checked reviews (Day 6).

## Complaint drivers (keyword tags, negative vs positive reviews)
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

## Embeddings
| # | Model | Reviews embedded | Notes |
|---|---|---|---|
| 1 | Gemini gemini-embedding-001 (768d), free tier | 1,000 | Hit the free-tier daily limit (~1,000 embeddings/day); 25K would take ~25 days |
| 2 | BGE-small-en-v1.5 (384d), local via fastembed | 25,000 | Free, offline, no rate limits, no PyTorch; Gemini kept for generation only |

Bug fixed: a cached batch from the 2,000-review test held only 16 embeddings and was reused in the full run (984 vs 1,000). Cache now checks batch size before reuse.

Planned: compare Gemini vs BGE-small retrieval quality on the same 1,000 reviews (Day 6).

## Retrieval: vector search (BGE-small, ChromaDB)
| Query | 2,000 indexed | 25,000 indexed | Notes |
|---|---|---|---|
| "milk and bread always out of stock" | 2/5 | 5/5 | Knowledge-base size mattered more than the method |
| "bread was stale and moldy" | — | 5/5 | |
| "waited forever, only one register open" | — | 5/5 | |
| "produce goes bad the next day" | — | 5/5 | |
| "prices went up so I shop somewhere else now" | — | 3/5 | Two-part query (cause + switching) is the weak spot |
| **Total** | | **23/25 (92%)** | Informal check; formal labelled set with Hit@5/MRR on Day 6 |

Pattern: single-concept queries near-perfect; two-part queries weaker. Motivates hybrid search (BM25) and reranking on Day 6.

## Notable quotes (link to Findings 8 and 9)
- "I stopped in for just milk and bread. There was literally one loaf of bread on the shelves."
- "They almost never have anything in stock that I buy… I now do most my shopping elsewhere."
- "A lot of the produce is rotten or out of stock… I go to Publix now, much happier!"
- "Just raised all the prices for no apparent reason… I guess that means less visit to Whole Foods."

## Trend reports knowledge base

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
| 2 | + distance cut-off 0.48 + everyday category words ("bread", "milk") | | | | *pending* |

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

**Run 2: stricter prompt** (flag prepared-food evidence, no added details, no "often" without 3+ reviews)

| Segment | Reasons | Citation validity | Faithful (manual) | Categories explained | Latency |
|---|---|---|---|---|---|
| Core · Basket changed | 3 | 100% | 3/3 | 2/3 | 59.8s |
| Core · Visiting less | 3 | 100% | 3/3 | 2/3 | 65.3s |
| High-value · at risk | 3 | 100% | 2/3 (1 reason on a single review) | 1/3 | 89.1s |
| **Total** | 9 | **100%** | **8/9 (89%)**, up from 73% | 5/9 | |

- The model now abstains: bread and soup evidence is flagged as prepared food in evidence_gaps instead of being used.
- Trade-off: faithfulness up, category coverage down (5/9). Bread and soup are now a retrieval problem → Day 6 (hybrid search + rerank).
- Latency roughly doubled with the stricter rules. The cache makes reruns instant.
- To consider: require 2+ citations per reason (the High-value price reason rested on 1 review).

- All numbers match segments.json ($8,812/week total; the 34 high-value customers hold 29%). No invented numbers.
- **Citation validity ≠ faithfulness:** all 3 unfaithful reasons cited real review IDs, but the reviews were about sandwiches, not packaged bread. The model then added details ("hard, stale") the reviews didn't contain.
- Root cause is retrieval: Yelp reviewers rarely discuss packaged bread or canned soup, so these categories pull deli and prepared-food reviews.
- Core · Basket and High-value got nearly identical reasons: High-value needs value-specific queries (service, premium quality, recognition).

**Next:** run 2 = stricter prompt (flag prepared-food evidence, no added details, no "often" without 3+ reviews). Day 6 = hybrid search + reranking to fix the retrieval gap; Day 9 = automated faithfulness judge.
