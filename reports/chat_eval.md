# Assistant chat eval (Day 8)

Model `gemini-3.5-flash-lite`, retrieval `hybrid`, 12 questions, each in a fresh conversation.

| Metric | Result | Target |
|---|---|---|
| Routing accuracy | 100% | ≥ 90% |
| In-scope answers with citations | 100% | 100% |
| Citation validity | 100% | 100% |
| Numbers grounded (answers with no ungrounded numbers) | 92% | 100% |
| Mean latency | 2.9s | |

| ID | Type | Expected | Called | Routed | Citations | Model s | Tools s |
|---|---|---|---|---|---|---|---|
| q01 | overview | list_segments | list_segments | ✅ | 4 | 2.2 | 0.0 |
| q02 | overview | list_segments | list_segments | ✅ | 4 | 2.2 | 0.0 |
| q03 | why | get_segment_reasons | get_segment_reasons | ✅ | 8 | 2.5 | 0.0 |
| q04 | why | get_segment_reasons | get_segment_reasons | ✅ | 12 | 5.5 | 0.0 |
| q05 | reviews | search_reviews | search_reviews | ✅ | 4 | 1.8 | 1.68 |
| q06 | reviews | search_reviews | search_reviews | ✅ | 5 | 1.8 | 0.09 |
| q07 | trends | search_marketing_trends | search_marketing_trends | ✅ | 2 | 7.0 | 0.18 |
| q08 | trends | search_marketing_trends | search_marketing_trends | ✅ | 1 | 1.8 | 0.04 |
| q09 | campaign | get_campaign_kit | get_campaign_kit, list_segments | ✅ | 2 | 2.7 | 0.01 |
| q10 | campaign | get_campaign_kit | get_campaign_kit | ✅ | 2 | 2.2 | 0.0 |
| q11 | multi | get_segment_reasons, search_marketing_trends | get_segment_reasons, search_marketing_trends | ✅ | 5 | 2.2 | 0.06 |
| q12 | out_of_scope | none | none | ✅ | 0 | 1.1 | 0.0 |
