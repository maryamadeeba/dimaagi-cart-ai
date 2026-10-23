# Model experiment log

**2026-10-23:** Renamed WinBack AI -> Dimaagi Cart in v0.3.2 (name already used by another company).

| # | Change | Best model | ROC-AUC (5-fold CV) | Notes |
|---|---|---|---|---|
| 0 | Simple rule: recency_days | — | 0.685 | Baseline to beat |
| 1 | XGBoost depth 4, single split | XGBoost | 0.686 | Overfit, no better than the rule |
| 2 | Simpler models, 5-fold CV | Random forest / XGBoost (depth 2) | 0.765 / 0.763 | Regularisation fixed overfitting; +0.08 over the rule |
| 3 | Added 4-week trend + active_week_share features | Random forest | 0.773 | Small consistent gain (+0.008); XGBoost unchanged (0.765) |
| 4 | Rolling snapshots (Jun, Aug, Oct); train Jun+Aug, test Oct | XGBoost (simpler) | 0.760 (time-based test) | PR-AUC 0.47 vs 0.227 random; top-20% capture 44% vs rule 39% vs random 20% |
| 7 | Final model choice (demographics OFF, time-based test) | XGBoost (simpler) | 0.767 | RF 0.770 / PR-AUC 0.498 vs XGB 0.767 / 0.478, a tie within noise. Chose XGBoost: faster SHAP, smaller file for the .exe, quicker monthly retraining |
| — | Reproduced with `src/train.py` (time-based test on Nov–Dec 2017, 2,297 customers) | XGBoost (simpler) | 0.764 | Capture at 10/20/30%: 24% / 44% / 57% (recency rule 24% / 38% / 50%). These script numbers are the ones quoted in the README and shown in the app; the notebook's earlier evaluation gave 26% / 44% / 57% (rule 24% / 39% / 50%) |
| — | **Behaviour-only model** (`src/train.py --no-marketing`): drops ever_targeted, campaigns_per_week, type_a_per_week, coupons_per_week, discount_share (25 features); same time-based test | XGBoost (simpler) | 0.764 | PR-AUC 0.472 (full model 0.469). Capture at 10/20/30%: 25% / 43% / 58% (full model 24% / 44% / 57%; recency rule 24% / 38% / 50%). A tie: the marketing signals add nothing measurable on this test. Used as the pre-trained model for imported stores, which have no campaign, coupon or discount data |
