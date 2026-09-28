# AI Code Reviewer

An intelligent, production-ready GitHub pull request review service powered by AI agents, deterministic static analysis, and automated test verification.

AI Code Reviewer analyzes incoming pull requests, runs linting and security scans, executes relevant tests, verifies findings with ground-truth diff evidence, and posts clean, actionable comments directly to GitHub.

---

## Features

- **Automated & On-Demand Reviews**: Trigger reviews automatically via GitHub webhooks (`pull_request.opened`, `synchronize`) or manually through the web UI and REST API.
- **Agentic Multi-Stage Analysis**: Uses a LangGraph-orchestrated review pipeline that executes parallel security and quality analysis agents with full execution traces.
- **Deterministic Tool Scans**: Integrates Ruff, Pyright, Bandit, and Semgrep to catch bugs, type errors, and vulnerabilities without running untrusted code.
- **RAG & Context Enrichment**: Indexes code chunks with AST awareness and vector retrieval (Qdrant) to understand surrounding repository context.
- **Automated Test Validation**: Discovers and runs relevant pytest suites in an isolated temporary environment to verify regressions.
- **Hallucination Verification**: Deterministic verification agent checks diff hunks and tool outputs before commenting, filtering false positives and duplicate findings.
- **Repository Configuration**: Customizable review rules, tool toggles, and ignore paths via `.codereviewer.yml`.
- **Modern Web Dashboard**: React + Vite UI with review history, quality health scoring, analytics trends, and detailed run inspection.

---

## System Design & Architecture

The service coordinates deterministic static analysis, test execution, vector retrieval, and LLM reasoning using a **LangGraph** review pipeline.

### Architectural Workflow

```mermaid
flowchart TD
    A[GitHub Webhook / Manual Trigger] --> B[Fetch PR Snapshot & Diffs]
    B --> C[Load .codereviewer.yml Config]
    C --> D[Analyze Repository & Changed Files]

    D --> E1[RAG Context Retrieval\nQdrant Vector Search]
    D --> E2[Static Analysis\nRuff, Pyright, Bandit, Semgrep]
    D --> E3[Test Execution\nIsolated pytest Subprocess]

    E1 --> F[Join Analysis Results]
    E2 --> F
    E3 --> F

    F --> G[(Persist Review Run)]
    G --> H{Eligible for Review?}
    H -- No (Duplicate SHA / No LLM Key) --> H1[Skip Review & Mark Complete]
    H -- Yes --> I[Parallel Review Agents]

    I --> J1[Security Reviewer Agent]
    I --> J2[Quality Reviewer Agent]

    J1 --> K[Synthesize & Deduplicate Findings]
    J2 --> K

    K --> L[Deterministic Verification Agent\nDiff Hunk & Evidence Validation]
    L --> M[(Persist Verified & False-Positive Findings)]
    M --> N[Post GitHub Comments & Review Summary]
    M --> O[React Dashboard / Metrics API]
```

### Core Architecture Components

1. **Ingestion & Webhook Service (`app.api.github`, `app.api.reviews`)**:
   - Validates incoming GitHub webhook payloads with HMAC-SHA256 signatures (`X-Hub-Signature-256`).
   - Normalizes pull request metadata, commits, unified diffs, and changed hunk line mappings.

2. **LangGraph Review State Machine (`app.agents.graph`)**:
   - Orchestrates the full review lifecycle through an asynchronous, typed `StateGraph`.
   - Records an immutable step-by-step trace of each node's inputs, timing, and errors for auditing and debugging.

3. **Deterministic Tool & Test Sandbox (`app.analyzers`, `app.services`)**:
   - Executes Ruff, Pyright, Bandit, and Semgrep as path-restricted subprocesses on temporary file copies.
   - Clears environment secrets and test runner overrides (`addopts`) before executing pytest suites.

4. **AST-Aware RAG Engine (`app.rag`)**:
   - Parses Python files into AST symbols (classes, functions, methods) and Markdown into heading trees.
   - Embeds code chunks and indexes them into Qdrant to retrieve surrounding architectural context for changed files.

5. **Deterministic Verification Engine (`app.agents.nodes`)**:
   - Inspects candidate LLM findings to verify that cited lines and code snippets physically exist in the PR diff or tool outputs.
   - Drops hallucinations and suppresses duplicate findings from past review runs on the same repository.

6. **Persistence & Presentation Layer (`app.database`, `frontend/`)**:
   - Stores repositories, PRs, review runs, findings, and reviews in PostgreSQL or local SQLite.
   - Powers the React + Vite dashboard for real-time analytics, issue exploration, and review history.

---

## File Structure

```text
AI Code Reviewer/
├── .codereviewer.example.yml     # Reference per-repository configuration file
├── .env.example                  # Environment variable template
├── docker-compose.yml            # Docker orchestration (PostgreSQL, Qdrant, API)
├── Dockerfile                    # Container definition for the backend
├── requirements.txt              # Backend Python dependencies
├── main.py                       # Top-level entrypoint for running the backend
│
├── backend/                      # FastAPI Backend & Agent Service
│   ├── app/
│   │   ├── agents/               # LangGraph workflow, agent nodes, prompts & state
│   │   │   ├── graph.py          # StateGraph construction & compilation
│   │   │   ├── nodes.py          # Node handlers (fetch, analyze, review, verify)
│   │   │   ├── prompts.py        # System & agent prompts for LLM reviewers
│   │   │   ├── review_agent.py   # LLM review execution & structured output parsing
│   │   │   └── state.py          # TypedDict schema for the review pipeline state
│   │   ├── analyzers/            # Deterministic code analyzers & path filters
│   │   │   ├── path_filter.py    # Glob pattern exclusion (.codereviewer.yml)
│   │   │   └── static.py         # Subprocess runners for Ruff, Pyright, Bandit, Semgrep
│   │   ├── api/                  # FastAPI router endpoints
│   │   │   ├── analytics.py      # Aggregated metrics, overview & quality scoring
│   │   │   ├── github.py         # Webhook receiver & event dispatching
│   │   │   ├── health.py         # Service & database health checks
│   │   │   └── reviews.py        # Review triggers, status & finding endpoints
│   │   ├── core/                 # Application configuration & logging
│   │   │   ├── config.py         # Pydantic BaseSettings & env variable loading
│   │   │   └── logging.py        # Structured JSON logging & secret redaction
│   │   ├── database/             # SQLAlchemy ORM & session management
│   │   │   ├── models.py         # Repository, PullRequest, ReviewRun, Finding models
│   │   │   └── session.py        # Engine creation, get_db dependency & auto-migrations
│   │   ├── rag/                  # Code chunking, embeddings & vector retrieval
│   │   │   ├── chunking.py       # AST-based Python & Markdown code chunkers
│   │   │   ├── embeddings.py     # OpenAI / hash embedding provider abstractions
│   │   │   └── qdrant.py         # Qdrant client & vector collection indexing
│   │   ├── schemas/              # Pydantic schemas for requests, responses & findings
│   │   │   ├── analytics.py      # Trend & overview response schemas
│   │   │   ├── findings.py       # Finding, Category, Severity & ToolIssue schemas
│   │   │   ├── repo_config.py    # .codereviewer.yml validation schema
│   │   │   └── review.py         # ReviewRun, ReviewSummary & request models
│   │   ├── services/             # Core business logic services
│   │   │   ├── github_client.py  # GitHub REST API client (App tokens & PAT)
│   │   │   ├── github_comments.py# PR inline review & comment formatting
│   │   │   ├── repo_config_service.py # Fetches & validates .codereviewer.yml
│   │   │   ├── scoring.py        # Code health scoring algorithm (0-100)
│   │   │   └── static_analysis.py# Orchestrates static analyzer execution
│   │   └── tools/                # Static analysis rule definitions (e.g. Semgrep)
│   └── tests/                    # Comprehensive backend unit & integration tests
│
└── frontend/                     # React + Vite Dashboard
    ├── src/
    │   ├── api.ts                # REST client for backend API communication
    │   ├── App.tsx               # Application routing & page navigation
    │   ├── index.css             # Design system tokens, utilities & responsive styling
    │   ├── types.ts              # TypeScript interfaces for reviews, findings & metrics
    │   ├── components/
    │   │   ├── common/           # Reusable UI widgets (ScoreRing, Card, Badges, States)
    │   │   └── layout/           # Global header, navigation & page wrappers
    │   ├── pages/                # Dashboard views
    │   │   ├── DashboardPage.tsx # Quality score hero, trends & quick review form
    │   │   ├── HistoryPage.tsx   # Paginated review history table with score gauges
    │   │   ├── IssuesPage.tsx    # Filterable findings repository with code snippets
    │   │   ├── MetricsPage.tsx   # Detailed charts & severity/category breakdowns
    │   │   ├── ReviewPage.tsx    # In-depth run inspector (traces, diffs, findings)
    │   │   └── SettingsPage.tsx  # Repository configuration inspector & how-to guide
    │   └── test/                 # Frontend component tests (Vitest + Testing Library)
```

---

## Quick Start

### 1. Prerequisites
- **Python 3.11+**
- **Node.js 18+** & npm
- (Optional) **Docker Desktop** (if using PostgreSQL and Qdrant container services)

### 2. Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```
> **Tip:** By default, the app runs with **local SQLite** (`./local.db`), so Docker is not required for local development. Add your LLM provider key (`OPENAI_API_KEY` or `NVIDIA_API_KEY`) and optional `GITHUB_TOKEN` in `.env`.

### 3. Backend Setup
Create a virtual environment and install Python dependencies:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Start the API server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Verify the backend is healthy:
```bash
curl http://127.0.0.1:8000/health
```

### 4. Frontend Dashboard Setup
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser.

---

## Docker Compose (Optional)

To run with PostgreSQL and Qdrant services in Docker:
```bash
docker compose up -d
```
Then update `DATABASE_URL` in your `.env`:
```env
DATABASE_URL=postgresql+psycopg://reviewer:reviewer@localhost:5432/ai_code_reviewer
```

---

## Repository Configuration (`.codereviewer.yml`)

Repositories can customize review behavior by adding a `.codereviewer.yml` file to the root of their default branch:

```yaml
version: 1

paths:
  ignore:
    - "docs/**"
    - "**/migrations/**"
    - "*.lock"

tools:
  ruff: true
  pyright: true
  bandit: true
  semgrep: true
  pytest: false

review:
  min_severity: HIGH
  max_comments: 10
  categories:
    - SECURITY
    - BUG
    - PERFORMANCE
  guidelines: |
    - All public API functions must include docstrings.
    - SQL queries must strictly use bound parameters.
```

### Configuration Options

| Option | Type | Default | Description |
|---|---|---|---|
| `version` | `int` | `1` | Schema version. |
| `paths.ignore` | `list[str]` | `[]` | Glob patterns of files to exclude from diffs and scans. |
| `tools.ruff` | `bool` | `true` | Enable Ruff linter. |
| `tools.pyright` | `bool` | `true` | Enable Pyright type checker. |
| `tools.bandit` | `bool` | `true` | Enable Bandit security scanner. |
| `tools.semgrep` | `bool` | `true` | Enable Semgrep security rules. |
| `tools.pytest` | `bool` | `true` | Enable running tests on changed or related test files. |
| `review.min_severity` | `enum` | `MEDIUM` | Minimum severity for inline comments (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`). |
| `review.max_comments` | `int` | `20` | Maximum number of inline comments posted to the PR. |
| `review.categories` | `list[enum]` | `null` (all) | Filter allowed categories (`SECURITY`, `BUG`, `PERFORMANCE`, `CODE_QUALITY`, etc.). |
| `review.guidelines` | `str` | `""` | Custom maintainer instructions injected into review prompts. |

---

## Running Tests

### Backend Tests
```bash
cd backend
pytest
```

### Frontend Tests
```bash
cd frontend
npm test
```
