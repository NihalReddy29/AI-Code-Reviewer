# Agentic Code Reviewer

Agentic Code Reviewer is a full-stack application for automated code review workflows using GitHub webhooks, review agents, and code analysis tooling.

## Structure

- `backend/`: FastAPI backend and review engine
- `frontend/`: React frontend UI
- `.github/workflows/ci.yml`: CI pipeline

## Quick start

1. Create a Python virtual environment for the backend.
2. Install dependencies from `backend/requirements.txt`.
3. Copy `backend/.env.example` to `backend/.env` and configure values.
4. Start the app with Docker Compose.

## Notes

This project skeleton is intentionally minimal and intended to be expanded with actual review logic, agent orchestration, and GitHub integration.
