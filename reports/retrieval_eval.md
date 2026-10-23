# Retrieval evaluation (Day 6)

45 queries scored (0 skipped: no relevant review found). Labels: top-10 from each of 4 methods pooled, judged by `gemini-3.5-flash-lite`. Every scored result has a real label.

## Overall

| Method | Hit@5 | MRR@10 | P@5 | ms/query |
|---|---|---|---|---|
| vector | 0.800 | 0.767 | 0.591 | 82 |
| bm25 | **0.978** | 0.741 | 0.640 | 83 |
| hybrid | 0.911 | 0.817 | 0.653 | 124 |
| hybrid_rerank | **0.978** | **0.844** | **0.738** | 1675 |

## By query type (MRR@10)

| Type (n) | vector | bm25 | hybrid | hybrid_rerank |
|---|---|---|---|---|
| category (15) | 0.692 | 0.802 | 0.741 | 0.830 |
| issue (15) | 0.867 | 0.708 | 0.867 | 0.902 |
| theme (8) | 0.893 | 0.713 | 1.000 | 0.875 |
| hard (7) | 0.571 | 0.711 | 0.667 | 0.714 |

## Head-to-head vs vector (MRR per query)

| Method | Wins | Ties | Losses |
|---|---|---|---|
| bm25 | 9 | 27 | 9 |
| hybrid | 9 | 32 | 4 |
| hybrid_rerank | 10 | 30 | 5 |

## Judge reliability

- **Human spot-check:** agreed on 34/39 labels (87%), Cohen's kappa 0.73.
  - c02 · review `HM6_G1erWZ3Vf7y-GmBEQw`: judge Y, human N
  - c15 · review `VSruHkhux64y4gBVCmJDbw`: judge N, human Y
  - i03 · review `ZO-SnqeJU6mpGpN0VJEbhg`: judge N, human Y
  - h03 · review `KwAxCBMf56v-IucdnsZeXA`: judge Y, human N
  - h03 · review `6snxP_pPUWrLXxEQjFwp0g`: judge N, human Y
- **Strong vs Lite judge:** 338 labels on 16 queries, agreement 70%, kappa 0.44. Relevant rate: strong 30% vs Lite 58%.
