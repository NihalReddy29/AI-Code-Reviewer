# AI Code Reviewer

Production-oriented GitHub pull-request review service. This repository is built incrementally; **Phase 1** is the application skeleton: FastAPI, configuration, structured logging, PostgreSQL, Docker, and a health endpoint.

An earlier experiment lives in `agentic-code-reviewer/` and is not used by this codebase.

## Phase 1 scope

- FastAPI application with `GET /health`
- Pydantic Settings loaded from environment variables (no hardcoded secrets)
- JSON structured logging with secret redaction and `review_run_id` context
- SQLAlchemy models: `Repository` → `PullRequest` → `ReviewRun` → `Finding` / `Review`
- PostgreSQL via Docker Compose
- Unit tests that do not require GitHub or an LLM API key

## Phase 2 scope

- `POST /webhooks/github` with HMAC-SHA256 verification (`X-Hub-Signature-256`)
- GitHub REST client for PR metadata, changed files, and unified diffs
- GitHub App installation tokens (or a PAT via `GITHUB_TOKEN`)
- Diff parsing into structured hunks and changed line numbers
- Persist `Repository`, `PullRequest`, and `ReviewRun` (skip duplicate commit SHA)
- Manual trigger: `POST /reviews/{owner}/{repo}/{pr_number}`
- Lookup: `GET /reviews/{review_id}`, `GET /repositories`

## Phase 3 scope

- Path-based language and file-kind detection (source, test, docs, CI, lockfiles)
- GitHub git tree analysis at the PR head SHA (no clone, vendor dirs skipped)
- Project type, source roots, test directories, package managers, and test frameworks
- Manifest parsing for `pyproject.toml`, `requirements.txt`, and `package.json`
- Changed-file enrichment: language, related tests, hunk stats, sensitive-area hints
- Stored on `ReviewRun.repository_context`

## Phase 4 scope

- LangChain chat model factory (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, optional `LLM_BASE_URL`)
- Closed enums for finding category and severity (invalid values are rejected)
- Structured review output: summary plus findings with file, line, evidence, suggested fix, confidence
- Prompt built from the PR diff and repository context; secrets redacted; `.env` files omitted
- Findings persisted on the review run; GitHub comments are not posted yet
- `GET /reviews/{review_id}` includes findings; `GET /reviews/{review_id}/findings`
- If no LLM key is configured, ingestion still succeeds and the run stays `pending`

## Phase 5 scope

- AST-aware Python chunking (module / class / function) with file path, language, symbol, and line range metadata
- Heading-aware Markdown chunking and structure-aware fallbacks for other languages
- Configurable embeddings (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`); tests use a hash embedder
- Qdrant indexing of changed files, related tests, docs, and prior review findings
- Retrieval biased toward the changed function/class, then related files
- Retrieved context is stored on the review run and included in the LLM prompt
- RAG failures are recorded; the review still continues

## Phase 6 scope

- Deterministic static analysis on a temporary copy of PR files (not the host working tree)
- Allowlisted subprocesses only: Ruff, Pyright, Bandit, Semgrep — no `shell=True`, no executing repository code
- Shared `ToolIssue` format; results stored on `ReviewRun.static_analysis_results` and passed to the LLM as evidence
- Missing tools are recorded as unavailable; they do not fail the review
- Local Semgrep rules (`backend/app/tools/rules/python.yml`); no network `--config=p/...`
- Timeouts via `TOOL_TIMEOUT_SECONDS`

## Phase 7 scope

- LangGraph `StateGraph` with typed review state (errors and trace events use list reducers)
- Nodes wrap real services: fetch PR, repository analysis, RAG, static analysis, persist, LLM review
- Parallel fan-out: RAG retrieval and static analysis after repository analysis
- Conditional routing: skip LLM passes when the commit is a duplicate or no model is configured
- Parallel security and quality review agents, then merge (duplicate file/line/title dropped)
- Node trace stored on `ReviewRun.agent_trace` and returned from `GET /reviews/{id}`

## Phase 8 scope

- Deterministic verification agent after the LLM merge (not a second rubber-stamp LLM call)
- Evidence must appear in the PR diff, retrieved chunks, or static-analysis messages
- Cited lines must fall in a changed hunk (with small slack)
- Near-duplicate findings on this run (same file, nearby line, similar title) are rejected
- Duplicates of previously verified findings on the same repository are rejected
- Findings are persisted with `verified` and `verification_reason`; false positives are kept for the dashboard, not dropped silently

## Phase 9 scope

- Discover pytest files related to the PR (changed tests and `related_paths` from repository analysis)
- Copy those files plus likely sources into a temp workspace (path-confined, no host working tree)
- Run allowlisted `pytest` with a timeout; JUnit XML is parsed into a shared result schema
- Subprocess environment is stripped of API secrets; repository `addopts` are cleared
- Missing pytest or no related tests are recorded, not fatal
- Results stored on `ReviewRun.test_results` and included in the LLM prompt and verification corpus

## Phase 10 scope

- After findings are persisted, post a GitHub **COMMENT** review (does not approve or request changes)
- Only **verified** findings at CRITICAL / HIGH / MEDIUM are posted as inline comments
- Comments are anchored to a line in the PR diff; unanchored findings are summarized in the review body
- Secrets in comment text are redacted; posting failures are recorded and do not fail the review run
- `GITHUB_POST_REVIEWS` can disable posting; `Review.posted_to_github` and `github_review_id` are stored

## Phase 11 scope

- React + Vite dashboard for review runs (not a mock UI)
- `GET /reviews` lists runs with finding counts, verification counts, and GitHub post status
- CORS via `CORS_ORIGINS` (defaults to the Vite origin)
- Dashboard can trigger `POST /reviews/{owner}/{repo}/{number}`, poll pending runs, and filter findings
- Detail view shows findings, diffs, static analysis, tests, RAG chunks, and the LangGraph trace

Later phases add evaluation and production Docker docs.

## Local setup

1. Copy environment defaults:

   ```bash
   cp .env.example .env
   ```

2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Start PostgreSQL (and optionally the API) with Docker:

   ```bash
   docker compose up --build
   ```

   Or run the API locally from this folder (Postgres and Qdrant still need to be up):

   ```bash
   .venv\Scripts\activate
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

   From `backend/` you can also use `uvicorn app.main:app --reload --port 8000`.

4. Check health:

   ```bash
   curl http://localhost:8000/health
   ```

5. Run the dashboard (API on port 8000):

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Open http://localhost:5173. Vite proxies `/reviews`, `/repositories`, and `/health` to the API. Set `VITE_API_BASE=http://localhost:8000` if you skip the proxy.

## Tests

Tests use an in-memory SQLite database.

```bash
cd backend
pytest
cd ../frontend
npm test
```

## Configuration

All secrets and provider settings come from environment variables. See `.env.example`. Never commit `.env`.
