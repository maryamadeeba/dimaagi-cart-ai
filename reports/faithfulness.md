# Faithfulness (automated judge)

> These are the judge's RAW verdicts. Every partial/unsupported flag was then reviewed by hand; the human-reviewed figures (e.g. 95% why / 100% kits / 100% chat in run B, 97% over 229 claims) are in reports/rag_log.md (Day 9–10). Judge precision on its flags was ~60%, so raw scores understate faithfulness where the judge is too strict.

Judge model: `gemini-3.5-flash-lite`, temperature 0. Each output is split into atomic claims and each claim is checked against the exact source text the writer saw. Faithfulness = (supported + 0.5 × partial) / claims.

## Summary

| Type | Outputs | Claims | % supported | % partial | % unsupported | Mean faithfulness |
|---|---|---|---|---|---|---|
| why | 3 | 38 | 92% | 0% | 8% | 91% |

## why

| ID | Claims | S / P / U | Faithfulness |
|---|---|---|---|
| Core · Basket changed | 12 | 12 / 0 / 0 | 100% |
| Core · Visiting less | 11 | 8 / 0 / 3 | 73% |
| High-value · at risk | 15 | 15 / 0 / 0 | 100% |
