# Contributing

Thanks for your interest in contributing.

## Development Setup

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Copy environment variables from the root example file:

```bash
cp ../.env.example ../.env
```

At minimum, set `DASHSCOPE_API_KEY` and `SECRET_KEY`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
cp .env.docker.example .env
docker compose up -d --build
```

## Quality Checks

Run before opening a PR:

```bash
python3 -m py_compile backend/*.py backend/routers/*.py backend/services/*.py backend/prompts/*.py
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q test_e2e.py
cd frontend && npm run build
```

Optional:

```bash
cd frontend && npm run lint
```

## Prompt Profiles

Prompt and analysis-field definitions live in `backend/prompt_configs/default.json`.

To customize behavior, copy the file and set `PROMPT_CONFIG_PATH` to your custom JSON path. Keep custom production prompts out of commits if they contain private business logic.

## Pull Request Guidelines

- Keep changes focused and explain why they are needed.
- Add or update tests for backend behavior changes.
- Update `README.md` and `README.en.md` when configuration or deployment steps change.
- Do not commit `.env`, credentials, databases, uploaded videos, logs, generated clips, or other private data.
- For API or database changes, include migration notes.
