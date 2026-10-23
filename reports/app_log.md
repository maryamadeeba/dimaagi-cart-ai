# Phase 3 app log

**2026-10-23:** Renamed WinBack AI -> Dimaagi Cart in v0.3.2 (name already used by another company).

Phase 3 turns the Phase 1–2 Python code into a Windows desktop app: a React front end in an Electron window, and a local FastAPI backend that wraps the existing modules instead of copying their logic.

## Phase 3 at a glance

| Part | Setup |
|---|---|
| Backend | FastAPI on `127.0.0.1` only, one-time token per launch, data folder from `WINBACK_DATA_DIR` |
| Front end | React + Vite, rebuilt from `design/*.dc.html`; fonts bundled locally |
| Shell | Electron: free port, random token, splash screen, backend stopped on quit |
| Gemini key | Windows Credential Manager (`keyring`), never written to a file or returned by the API |
| Tests | 52 offline tests (24 from Phase 2, 28 new), no API key needed |

## Milestones 1–3: backend, front end, Electron shell

- **Store paths.** The existing modules keep their files at relative paths (`models/segments.json`, `data/vectorstore`...). The backend switches into the data folder once at launch, so every module works unchanged.
- **Chat sessions.** The assistant's tools write refs into a module-level session. The backend keeps one chat and one session per conversation and swaps the right session in for each turn, one turn at a time.
- **Security.** Requests are rejected without the token or with a foreign Host header. CORS is enabled only for the Vite dev server (`--dev`). The packaged page is served by the backend itself, so it needs no CORS at all.
- **Capture rates.** `src/train.py` now saves capture at 10/20/30% for the model, the recency rule and random. `--metrics-only` adds them to an existing `metrics.json` without touching the model (same md5 before and after).

## Review fixes, explainability and bring-your-own-data

### Bugs found

| Bug | Effect | Fix |
|---|---|---|
| `generate.theme()` guessed the theme from the segment name | High-value is 59% "visiting less" but was searched with "basket changed" queries | `theme()` reads `reason_mix` from `segments.json`; the name is only a fallback. Test added |
| `generate --segment X` and `campaign --segment X` wrote only segment X to the JSON | Rerunning one segment deleted the other segments' reasons and kits | Results are merged into the existing file by segment. Test added |
| Owners' imported data (`stores/`) was not gitignored | Customer sales files could be committed | `/stores/` added to `.gitignore` |
| A driver phrase read "0 days between visits" | Customers with several trips on one day | Phrase fixed; drivers now store the value, so wording fixes apply without rescoring |

### Numbers corrected in the README

The capture-rate table now shows the reproducible script's numbers (`models/metrics.json`): model 24% / 44% / 57% at 10/20/30%, recency rule 24% / 38% / 50%. The edge over the rule appears at 20–30%; at 10% they tie. The notebook's earlier figures (26% / 44% / 57%, rule 24% / 39% / 50%) stay in `model_log.md`.

The dashboard's basket/visiting split is now labelled "Share of at-risk customers by main reason" (61.0% / 39.0%, from the segments). It is a different measure from the README's SHAP-theme split (61.9% / 38.1%).

### Showing the ML

- **Per-customer drivers.** During scoring, `src/explain.py` turns each customer's top 3 SHAP values into fixed plain-English phrases with direction and size, saved to `models/drivers.json`. There is no LLM in this step.
- **Customers screen.** Every regular customer (2,347 in the demo) with their risk score, segment, weekly spend, revenue at risk and top reason. The list is searchable, sortable and paginated on the server. Each row opens a drawer with the 3 drivers as bars and a link to the segment's kit.
- **Model card.** Training period and households, the test-on-the-future validation, ROC-AUC against the recency rule, a capture chart, the 30 features by group (marketing features struck through when unavailable) and limitations.

### Showing the AI and RAG

- **Recorded metadata.** `generate` and `campaign` now save the model, retrieval method, search queries, number of sources retrieved, timestamp and whether the answer came from the cache. Older output files without this metadata still display, with a note to regenerate.
- **How this was made.** Panels on Why, Win them back and every chat answer show this metadata plus the code checks.
- **Regenerate.** Per-segment buttons ask for confirmation first, because they use the owner's Gemini quota. They are disabled, with a reason, when the key or a knowledge base is missing. A `--fresh` flag on the CLI skips the cached answer.

### Bring your own data

- **Import wizard.** Upload (CSV or Excel), match columns, match categories, then a data check and scoring. Conversion produces the dunnhumby-shaped tables `src/features.py` already reads: a basket is one customer at one time, staples keep the model's staple category names, and other categories keep the store's own names. Campaign, coupon and demographic tables are written empty.
- **Training minimum.** About 240 days of history, computed from `src.train.auto_cutoffs`: 61 days + three cutoffs 2 months apart + 8 weeks before the oldest cutoff. The app computes the exact figure from each file's dates.
- **Champion vs challenger.** The pre-trained model and the store's own model are scored on the same newest-period test set, and the higher ROC-AUC is kept. On a synthetic 150-customer store: own model 0.908 vs pre-trained 0.901, so the store's own model was kept.
- **Stores.** Each owner's store lives in `stores/<name>/`, and the demo store (the data folder's own `models/`) is read-only. An end-to-end test imports a synthetic store in both modes and checks that the demo store's files are byte-identical afterwards.

### Still open

- **Review quotes.** Done below: the Why screen now quotes the sentence that best matches the reason.
- **Demo customer list in the installer.** Done below: it now ships.

- Kit number check false positive: "numbers to verify: 5, 7" in the regenerated High-value kit came from in-prose
  citations "(T5)", "(T7)". R4/R8 escaped only because 4 and 8 happened to appear in source texts. Fixed by stripping
  ref tokens before extracting numbers (same rule as the chat number-grounding check); regression test added.

## Before packaging: encoding and shared refs

- **Encoding.** Every entry point now calls `src/console.py`'s `utf8_console()` first: the backend, the generate/campaign/assistant/ingest/index/train/segments CLIs, and the eval scripts. It switches stdout and stderr to UTF-8 with `errors="replace"`, and copes with missing or non-reconfigurable streams. Electron also starts the backend with `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`. Before this, piping `python -m src.rag.campaign` to a file crashed on its first ✅ after the work was done. A test runs the real CLI with a cp1252 console.
- **Shared refs.** `REF_PATTERN`, `PLACEHOLDERS`, `parse_citations`, `refs_in` and `parse_refs` moved to `src/rag/refs.py`, so `campaign.py` no longer imports the assistant module (or ChromaDB through it).

## Milestone 4: the packaged backend

| | |
|---|---|
| Build | `winback-backend.spec`, PyInstaller 6.22, one folder, about 5 minutes |
| Size | 511 MB. Largest parts: pyarrow 83 MB (Parquet, used by the reviews KB build), ChromaDB native engine 61 MB, xgboost 56 MB, scipy 70 MB with its libraries, onnxruntime 43 MB |
| Ships | Code, `churn_model.pkl`, `feature_columns.json`, `metrics.json`, `segments.json`, `config/*.yaml` and `config/*.csv` |
| Excluded | IPython, matplotlib, Jupyter and test suites. Checked first: shap and ChromaDB import and run without them |
| Verification | `packaging/verify_backend.py`: 16/16 checks |

- **`--self-check` caught a real bug.** ChromaDB's schema validation reads a grammar file (`rfc3987_syntax/syntax_rfc3987.lark`) that PyInstaller didn't collect. Without it, every call that touches ChromaDB would have failed in the installed app, including the dashboard. Fixed in the spec by collecting that package's data files and jsonschema's.
- **Frozen RAG path.** A real `build-kb` job ran on the packaged exe in a scratch folder: pypdf, fastembed downloading BGE-small into `<data folder>/cache` (65 MB, once), and a persistent ChromaDB write all worked, in 40 seconds.
- **Privacy.** ChromaDB sends anonymous usage telemetry by default; the backend now sets `ANONYMIZED_TELEMETRY=False`.
- **Personal mode reads `.env` consistently.** Frozen python-dotenv looks in the current folder, so a packaged app pointed at the repo picked up `.env` only after the RAG modules loaded: no key at startup, a key later. The data folder's `.env` (if any) is now loaded at startup in every mode. Public mode's `%APPDATA%\WinBack` has none.
- **First run.** On an empty data folder the exe copied the 7 shipped files, answered `/api/health` in about 2 seconds, rejected requests without the token, served the dashboard (469 at-risk customers from the shipped segments) and the model card, returned a setup prompt for reasons (not shipped), and served the front end.

## Milestone 5: the installer

| | |
|---|---|
| File | `desktop/dist/WinBack-AI-Setup-0.3.0.exe`, NSIS, x64, per user (no admin rights), installation folder can be changed |
| Size | about 290 MB to download, 845 MB installed (backend about 510 MB, Electron about 330 MB) |
| App | "WinBack AI" by Maryam Adeeba, v0.3.0, desktop and Start-menu shortcuts, icon from the logo mark |
| Signed | No: the installer, the app and the backend exe are unsigned, so Windows SmartScreen warns on first run |
| Build | `packaging/build.ps1`: tests, front end, PyInstaller, verification, electron-builder |

- **Packaged-app launches.** The packaged app reaches the welcome screen in public mode (an empty scratch data folder) and in personal mode (`WINBACK_DATA_DIR` = the repo), in about 6–9 seconds from launch. No processes are left after quitting.
- **Personal mode.** The packaged backend sees both knowledge bases, the reasons, the kits and all 2,347 scored customers in the repo.
- **Licensing scan of the unpacked installer.** No review text, PDFs, vector store, caches, `.env` or review-quoting outputs. The only `.parquet` files are pyarrow's own test fixtures (about 7 MB of third-party test folders in total; worth trimming in a later build).

## Before committing: four follow-ups

- **Demo customer list ships.** `scored_customers.csv` and `drivers.json` are on the ship list now (dunnhumby-derived risk scores and SHAP drivers, anonymised household keys, no review text), so the installed demo's Customers screen works. The ship list lives in one place (`src/api/config.py` `SEED_FILES`), read by the app, the PyInstaller spec and `verify_backend.py`; the verifier now checks that the packaged demo's Customers endpoint returns rows and that a customer has 3 SHAP drivers. The dunnhumby attribution is on a new **About and credits** screen and in the README.
- **Behaviour-only model for imported stores.** `python -m src.train --no-marketing` trains without the 5 campaign, coupon and discount features and saves `churn_model_behaviour.pkl`, `feature_columns_behaviour.json` and `metrics_behaviour.json`. Imported stores start with it instead of the full model fed zeros, and train their own models without those features. Champion vs challenger for an imported store compares its own model with this behaviour-only model.

  | Model (demo data, test on Nov–Dec 2017, 2,297 customers) | Features | ROC-AUC | PR-AUC | Capture 10 / 20 / 30% |
  |---|---|---|---|---|
  | Full model | 30 | 0.764 | 0.469 | 24% / 44% / 57% |
  | Behaviour-only model | 25 | 0.764 | 0.472 | 25% / 43% / 58% |
  | Days-since-last-visit rule | 1 | 0.684 | | 24% / 38% / 50% |

  A tie: dropping the marketing signals costs nothing measurable here. The model card shows both pre-trained models' scores.
- **Review quotes.** The Why screen now quotes the review sentence with the most content-word overlap with the reason it backs plus the search that found it (stop words ignored, light stemming, ties go to the earliest sentence, no overlap falls back to the first sentence). "I was unimpressed." became "the milk is always expired no matter what the date says." "Show more" still shows the full snippet.
- **`.vscode/` ignored.** It only held `python.terminal.useEnvFile: true`, a personal editor setting; the code loads `.env` itself.

- Installed-app test (personal mode): ambiguity rule worked (asked which segment); answer matched the kit checklist
  with valid citations. False positive: bullets under a cited lead-in ("complete these fixes [K_corevisiting]:") were
  flagged as ungrounded (7, 4, 7, $3, $20, all correct): the bullet-as-unit rule from the q09 fix ignored the lead-in's
  citation. Fix: uncited bullets inherit the lead-in's citations; regression tests both ways. Also: Sources panel
  labels overflowed and showed internal file paths.

## v0.3.1

- **Number check: bullets inherit the lead-in citation.** In the installed app, an answer like "complete these fixes [K_corevisiting]:" followed by bullets ("…daily at 7 AM", "…from 4 PM to 7 PM", "…the $3 discount for $20+ baskets") flagged 7, 4, 7, $3 and $20, although all are in K_corevisiting. A bullet that cites nothing now uses the citations of its list's lead-in line (the nearest non-bullet line above it); a bullet with its own citation keeps it, and bullets under an uncited lead-in are still flagged. Replaying the 12 saved chat-eval answers gives the same result before and after. The assistant prompt also asks it to cite list sources on the lead-in line or on each item. Tests: the exact answer (not flagged), a number missing from the lead-in source (flagged), a bullet with its own citation, an uncited lead-in.
- **Sources panel.** Labels wrap inside the card, and owners see "Campaign kit: Core · Visiting less", not "(models/campaign_kits.md)". The file path now appears only under "How this was made".
- **Data folder setting.** Retrain → Data folder (and "Open an existing WinBack folder" on the welcome screen) checks a folder and restarts the engine on it in place. It accepts an existing WinBack folder, an empty folder or a new one, and refuses unrelated files, files and the install folder. The choice goes in `app-config.json` in Electron's own folder. Precedence: `WINBACK_DATA_DIR` > the chosen folder > the default. Tested in the real app over DevTools: the switch restarts the engine, the new folder's stores appear, and "Use the default" switches back. `desktop/datafolder.js` has 6 Node tests (precedence, a vanished folder, reset, folder kinds, refusals).
- **Key status.** AI settings say where the key comes from: Credential Manager, the data folder's `.env`, or an environment variable. Values are compared in memory only.
- **Checklist ticks survived only one launch (fixed).** The packaged page's origin is `http://127.0.0.1:<port>`, and the port was new on every launch, so localStorage (the "Before you send" ticks) started empty each time. The app now reuses its port when it's free (saved in `app-config.json`), including across data-folder restarts.
- **`npm ci` dropped the Electron binary.** npm 11 skipped Electron's download script; `electron` is now in `allowScripts`, so `npm run dev` and `npm start` work after a clean install. The installer was never affected, since electron-builder downloads its own copy.

- Installed-app test (personal mode): ambiguity rule worked (asked which segment); answer matched the kit checklist
  with valid citations. False positive: bullets under a cited lead-in ("complete these fixes [K_corevisiting]:") were
  flagged as ungrounded (7, 4, 7, $3, $20, all correct): the bullet-as-unit rule from the q09 fix ignored the lead-in's
  citation. Fix: uncited bullets inherit the lead-in's citations; regression tests both ways. Also: Sources panel
  labels overflowed and showed internal file paths.
