<p align="center">
  <img src="docs/assets/shotloom-logo.svg" alt="ShotLoom logo" width="520" />
</p>

<p align="center">
  English | <a href="./README.md">中文</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img alt="React" src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=0f172a" />
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white" />
  <img alt="Docker" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
  <img alt="Qwen" src="https://img.shields.io/badge/Qwen3.7%20%2B%20Qwen--ASR-7C3AED?style=for-the-badge" />
  <img alt="License" src="https://img.shields.io/badge/License-MIT-D6A24D?style=for-the-badge" />
</p>


ShotLoom is AI-powered shot intelligence for film and video breakdowns. It uploads videos, detects shot boundaries, extracts clips, asks a Qwen multimodal model to analyze each shot, and exports Excel/PDF reports.

ShotLoom combines "shot" and "loom": it weaves individual cuts into a readable, reviewable, exportable narrative thread.

## Features

- Automatic shot detection: uses PySceneDetect ContentDetector + AdaptiveDetector for hard cuts, fades, and dissolves.
- AI shot analysis: uses DashScope/Qwen multimodal models to analyze shot scale, camera movement, composition, lighting, rhythm, narrative intent, and more.
- Continuity report: summarizes selected analyzed shots into a whole-video narrative and rhythm report.
- Real-time progress: streams analysis progress through SSE and can recover active task state after page refresh.
- Users and credits: email/password login, optional WeChat login, credit deduction, and admin credit setting. Built-in email registration does not verify email addresses yet.
- Report export: exports Excel and PDF reports.
- Admin console: lets admins inspect users, videos, credit transactions, and account status.

## Tech Stack

### Backend

- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- PyAV + PySceneDetect
- DashScope/Qwen multimodal models
- JWT + bcrypt
- openpyxl + WeasyPrint

### Frontend

- React 18 + TypeScript
- Vite
- Ant Design / Ant Design Pro Components
- Tailwind CSS v4
- Axios
- React Router
- React Hook Form + Zod

## Repository Layout

```text
.
├── backend/
│   ├── routers/              # API routers
│   ├── services/             # Shot detection, clip extraction, AI analysis, export logic
│   ├── prompts/              # AI prompts
│   ├── auth.py               # JWT, password hashing, current-user dependencies
│   ├── config.py             # Backend configuration
│   ├── database.py           # SQLAlchemy models and DB initialization
│   ├── main.py               # FastAPI entrypoint
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # Shot list, timeline, detail panel, etc.
│   │   ├── contexts/         # Auth context
│   │   ├── hooks/            # SSE progress hook
│   │   ├── pages/            # Home, auth, analysis, admin pages
│   │   ├── types/            # TypeScript types
│   │   └── utils/            # API client
│   ├── package.json
│   └── vite.config.ts
├── .env.example              # Example environment variables
├── LICENSE                   # MIT License
├── README.md                 # Chinese README
├── README.en.md              # English README
└── start.sh                  # Local startup script
```

## Requirements

- Python 3.10+
- Node.js 18+ (20+ recommended)
- npm
- FFmpeg/system codec support (PyAV and WeasyPrint may require additional system packages depending on your OS)
- DashScope API Key

## Quick Start

### 1. Clone

```bash
git clone <repository-url>
cd 视频
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Minimum required variables:

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
SECRET_KEY=replace-with-a-random-strong-secret
ENV=development
PUBLIC_VIDEO_BASE_URL=https://your-public-shotloom-domain.example.com
```

The default preset contains Qwen ASR fields, so `PUBLIC_VIDEO_BASE_URL` must be reachable by Alibaba Cloud before analysis can start. If it is missing, the backend rejects the task without deleting previous results.

Common optional variables:

```env
VISION_MODEL_NAME=qwen3.7-plus
ASR_MODEL_NAME=qwen3-asr-flash-filetrans
CONTINUITY_MODEL_NAME=qwen3.7-plus
PROMPT_CONFIG_PATH=backend/prompt_configs/default.json
MIN_MODEL_VIDEO_DURATION=2.0
SAFE_MODEL_VIDEO_DURATION=3.0
SHORT_SHOT_MERGE_MAX_SHOTS=5
MODEL_TRANSIENT_RETRIES=2
SCENE_THRESHOLD=27
AI_CONCURRENCY=2
MAX_UPLOAD_SIZE_MB=1024
MAX_VIDEO_DURATION_SECONDS=3600
VITE_MAX_UPLOAD_SIZE_MB=1024
VITE_MAX_VIDEO_DURATION_SECONDS=3600
NGINX_CLIENT_MAX_BODY_SIZE=1024m
COS_UPLOAD_ENABLED=false
COS_BUCKET=your-bucket-appid
COS_REGION=ap-singapore
COS_ROLE_NAME=your-cvm-role
COS_ACCELERATE=true
COS_PART_SIZE_MB=16
INITIAL_CREDITS=100
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```



Short-shot handling: original shot boundaries are preserved. When a shot is shorter than `SAFE_MODEL_VIDEO_DURATION`, ShotLoom automatically merges neighboring shots into a stable analysis clip and marks the result with `analysis_mode=merged_context`, merge bounds, and context-shot summaries.

### Context Analysis Router

ShotLoom can derive shot-level analysis from whole-video context for short videos, chunked segment context for longer videos, and shot-level fallback for selected reanalysis or missing context results.

| Variable | Default | Description |
| --- | --- | --- |
| `ANALYSIS_ROUTER_MODE` | `auto` | Analysis router mode: `auto`, `whole_video`, `chunk_segment`, or `shot_fallback`. |
| `WHOLE_VIDEO_MAX_DURATION` | `180` | Max duration in seconds for whole-video context analysis. |
| `WHOLE_VIDEO_MAX_SHOTS` | `60` | Max shot count for whole-video context analysis. |
| `CHUNK_SEGMENT_DURATION` | `300` | Max seconds per chunk for chunked segment analysis. |
| `CHUNK_SEGMENT_MAX_SHOTS` | `80` | Max shots per chunk for chunked segment analysis. |
| `CHUNK_SEGMENT_OVERLAP_SHOTS` | `2` | Overlapping shots between adjacent chunks. |
| `SHOT_FALLBACK_ENABLED` | `true` | Fall back to shot-level analysis when context analysis misses shots. |
| `QWEN_VIDEO_INPUT_MODE` | `auto` | Qwen video input mode: `auto` uses Base64 for small files and signed URLs for large files; force with `base64` or `url`. |
| `VISION_MODEL_NAME` | `qwen3.7-plus` | Model for visual, shot, segment, and content-operation analysis. |
| `ASR_MODEL_NAME` | `qwen3-asr-flash-filetrans` | Model for full-video speech transcription and timestamps. |
| `ASR_API_BASE_URL` | Singapore async endpoint | Must match the region of the API key. |
| `PUBLIC_VIDEO_BASE_URL` | empty | Public base URL reachable by Qwen, for example `https://your-domain.com/shotloom`. |
| `SIGNED_VIDEO_URL_EXPIRE_SECONDS` | `1800` | Signed video URL TTL in seconds. |
| `SIGNED_VIDEO_URL_SECRET` | empty | Dedicated signing secret; use a random production value. Falls back to `SECRET_KEY` if empty. |
| `CONTEXT_BASE64_MAX_MB` | `8` | Whole-video Base64 safety limit for OpenAI-compatible local file input. |

When `PUBLIC_VIDEO_BASE_URL` is configured and the source video exceeds `CONTEXT_BASE64_MAX_MB`, ShotLoom gives Qwen a short-lived signed URL (`/api/public/video/{token}`) instead of Base64. The endpoint does not use user login state, but the token is HMAC-signed and expires automatically.



### Custom Prompts And Analysis Fields

The default profile lives at `backend/prompt_configs/default.json`. Signed-in users can edit it visually for each video and save reusable private presets:

- `scopes.shot`: per-shot fields
- `scopes.segment`: segment fields
- `scopes.overall`: whole-video fields
- `prompts`: role and instruction prompts for all three scopes

Fields support nested objects and arrays. Each analysis stores an immutable config snapshot, so draft edits do not alter historical reports. Applying a changed config requires a full reanalysis. Excel and PDF columns are generated from the same snapshot.

Database migration note: this release adds the `analysis_presets`, `video_analysis_configs`, `video_transcripts`, and `analysis_task_snapshots` tables. Back up production databases, then run `cd backend && alembic upgrade head`; local development startup still creates missing tables through SQLAlchemy. Existing results retain their legacy format until a full reanalysis activates the v2 schema.

Optional WeChat login variables:

```env
WECHAT_APP_ID=wx_your_app_id
WECHAT_APP_SECRET=your_wechat_app_secret
WECHAT_CALLBACK_URL=http://localhost:8000/api/auth/wechat/callback
```

### 3. Start Locally

```bash
chmod +x start.sh
./start.sh
```

Open:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- OpenAPI docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

> `start.sh` creates the backend virtual environment, installs Python dependencies, and runs `npm install` when `frontend/node_modules` is missing.


## One-Command Docker Compose Deployment

Copy the Docker environment template:

```bash
cp .env.docker.example .env
```

Edit `.env` and at least replace:

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
SECRET_KEY=replace-with-a-random-strong-secret-at-least-32-chars
POSTGRES_PASSWORD=replace-with-a-random-db-password
FRONTEND_URL=http://localhost:8080
CORS_ORIGINS=http://localhost:8080
```

Start the full stack:

```bash
docker compose up -d --build
```

Default services:

- Frontend/Nginx: http://localhost:8080
- Backend API: container-internal `backend:8000`, proxied by frontend Nginx under `/api`
- PostgreSQL: persisted in the `postgres_data` volume
- Redis/RQ: used for analysis jobs and rate limiting
- Worker: runs video clipping and AI analysis in the background


#### Mount A Custom Prompt Config In Docker

If you want to keep prompt/field profiles outside the repository, create `docker-compose.override.yml`:

```yaml
services:
  backend:
    environment:
      PROMPT_CONFIG_PATH: /app/prompt_configs/custom.json
    volumes:
      - ./prompt_configs/custom.json:/app/prompt_configs/custom.json:ro
  worker:
    environment:
      PROMPT_CONFIG_PATH: /app/prompt_configs/custom.json
    volumes:
      - ./prompt_configs/custom.json:/app/prompt_configs/custom.json:ro
```

Then copy and edit the default profile:

```bash
mkdir -p prompt_configs
cp backend/prompt_configs/default.json prompt_configs/custom.json
docker compose up -d --build backend worker
```

Useful commands:

```bash
docker compose logs -f backend worker
docker compose ps
docker compose down
```


### Admin User

Create the first admin after deployment:

```bash
docker compose exec backend python manage.py create-admin admin@example.com --password 'change-me-now'
```

Reset a password:

```bash
docker compose exec backend python manage.py reset-password admin@example.com --password 'new-password'
```

### Database Migrations

Containers run this on startup by default:

```bash
alembic upgrade head
```

Manual run:

```bash
docker compose exec backend alembic upgrade head
```

### Backup and Restore

Back up Postgres and media volumes:

```bash
scripts/backup.sh
```

Restore:

```bash
scripts/restore.sh backups/YYYYmmdd-HHMMSS
```

### Docker Smoke Test

```bash
scripts/smoke_docker.sh
```

Production notes:

- Set `COOKIE_SECURE=true` behind HTTPS.
- Set `FRONTEND_URL` / `CORS_ORIGINS` to your real domain.
- Never use the template `SECRET_KEY` or `POSTGRES_PASSWORD`.
- With `COS_UPLOAD_ENABLED=true`, the browser uploads 16 MB parts to COS with four concurrent requests and the same-region server materializes the object, bypassing Cloudflare's 100 MB request-body limit. The bucket CORS rule must allow `PUT` from the site origin and expose the `ETag` response header.
- Without COS, upload limits are controlled by backend `MAX_UPLOAD_SIZE_MB`, frontend `VITE_MAX_UPLOAD_SIZE_MB`, and Nginx `client_max_body_size` / `NGINX_CLIENT_MAX_BODY_SIZE`.
- Single-video duration defaults to 3600 seconds (1 hour); keep backend `MAX_VIDEO_DURATION_SECONDS` and frontend `VITE_MAX_VIDEO_DURATION_SECONDS` aligned if you change it.

## Manual Development

### Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If you start the backend directly from `backend/`, make sure environment variables are exported or available in `backend/.env`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

During local development, Vite proxies `/api` to `http://localhost:8000`.

## Build and Checks

```bash
# Frontend type check and production build
cd frontend
npm run build

# Frontend lint
npm run lint

# Backend tests
cd ../backend
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Some backend tests may require additional video/system dependencies, depending on your local environment.

## Workflow

1. Register or log in.
2. Upload a video file.
3. Run shot detection to generate shot boundaries and thumbnails.
4. Analyze all or selected shots with AI.
5. Generate a continuity report from selected analyzed shots.
6. Export an Excel or PDF report.
7. Admins can inspect users and credits in the admin console.

## API Overview

Main endpoints use the `/api` prefix:

- `POST /api/auth/register`: register with email/password
- `POST /api/auth/login`: log in with email/password
- `GET /api/auth/me`: current user
- `GET /api/auth/wechat/login`: WeChat login entry
- `POST /api/upload`: upload video
- `GET /api/videos`: list videos
- `POST /api/detect/{video_id}`: detect shots
- `POST /api/analyze/{video_id}`: start AI analysis
- `GET /api/progress/{task_id}`: SSE progress stream
- `GET /api/results/{video_id}`: analysis results
- `POST /api/reanalyze-continuity/{video_id}`: generate/regenerate continuity report
- `GET /api/export/{video_id}?format=excel|pdf`: export report
- `GET /api/admin/users`: admin user list

Use `/docs` for the full OpenAPI reference.

## Security And Deployment Notes

- Video read/write, detection, analysis, and export endpoints require login and enforce resource ownership.
- Built-in email registration does not include email verification, password recovery, MFA, abuse protection, or login rate limiting; configure an email provider and add the auth features your deployment needs before opening the service to external users.
- Production rejects the default or too-short `SECRET_KEY`.
- Uploads use UUID storage names and enforce an application-level size limit; public deployments should still set reverse-proxy body limits.
- CORS allowlists and database URLs are configurable through environment variables.
- Never commit `.env`, databases, uploaded videos, logs, admin credentials, or generated artifacts.

## Contributing

Issues and Pull Requests are welcome. In PRs, please include:

- Motivation and user impact
- Any database or environment-variable changes
- Local test commands you ran
- Screenshots or recordings for frontend changes

## License

This project is open-sourced under the [MIT License](./LICENSE).
