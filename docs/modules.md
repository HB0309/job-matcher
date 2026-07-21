# Modules / Agents

| Module | Responsibility |
|---|---|
| `orchestrator.py` | Coordinates full fetch-match pipeline: load profile → parallel fetch → normalize → security filter → title filter → dedupe → score → persist |
| `resume_parser.py` | Parses PDF/DOCX resume into structured profile fields (headline, years_experience, skills). `SKILL_KEYWORDS` (~200 canonical terms across languages, frameworks, databases, cloud, DevOps, ML, security). `SKILL_ALIASES` (104 mappings: variant → canonical, e.g. `k8s`→`kubernetes`, `golang`→`go`, `sklearn`→`scikit-learn`). Both resume and job-description extraction share the same function so intersection matching is symmetric. |
| `connectors/base.py` | Shared interfaces and DTOs: `JobQuery`, `SourceTargetDTO`, `RawJobPosting`, `BaseConnector` |
| `connectors/linkedin.py` | LinkedIn Voyager API via `linkedin-api` package; email+password auth; 5-thread detail fetch; ~500 jobs/run |
| `connectors/remoteok.py` | RemoteOK public JSON API; remote-only jobs; tag-based search |
| `connectors/themuse.py` | The Muse public REST API; Software Engineering category filter; level mapping |
| `connectors/adzuna.py` | Adzuna aggregator REST API; requires `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`; 500-char description cap |
| `connectors/jobright.py` | JobRight Next.js internal data API; full descriptions |
| `connectors/remotive.py` | Remotive public REST API; remote tech jobs; full HTML descriptions stripped to text |
| `connectors/dice.py` | Playwright headless Chromium scraper; DOM extraction from rendered SPA; stealth mode to bypass bot detection |
| `connectors/hiringcafe.py` | Hiring Café (currently 403 blocked) |
| `connectors/indeed.py` | Indeed (RSS feed gone, currently unavailable) |
| `registry.py` | Resolves connector name → connector instance at runtime |
| `target_loader.py` | Loads enabled `SourceTarget` rows from DB, filtered by connector name or target IDs |
| `normalizer.py` | Maps `RawJobPosting` → `NormalizedJob`; detects `normalized_level`; extracts skill tags from description |
| `security_filter.py` | Drops jobs requiring US security clearance or citizenship (keyword scan of title + description) |
| `matcher.py` | `extract_domain_keywords()` — builds domain keyword set from preferred_titles; `passes_title_filter()` — whole-word regex match; `score_jobs()` — skills 35%, level 50%, location 15% |
| `deduper.py` | 3-pass deduplication: (1) within-batch fingerprint collapse, (2) exact `(connector_id, source_target_id, external_id)` DB match, (3) fuzzy fingerprint match against existing DB rows for same companies |
| `scheduler.py` | APScheduler `BackgroundScheduler`; loads enabled `ScheduledFetch` rows on startup; `register()`/`unregister()` called by schedules router |
| `intent_engine.py` | Deterministic state-rule classifier; `assess(state)` → `{intent, confidence, reasons, recommended_action}`; intents: `prepare_draft`, `review_draft`, `refresh_draft`, `start_apply`, `manual_only` |
| `application_drafter.py` | `DraftingProvider` interface; `DeterministicProvider` (default, no network); `HuggingFaceProvider` (opt-in via `DRAFTING_PROVIDER=huggingface`); `generate_draft()`; `mark_stale_for_profile()` |
