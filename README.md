# ShotLoom

[English](./README.en.md) | 中文

ShotLoom 是一个 AI 驱动的镜头语言分析与拉片工作台。它可以上传视频、自动检测镜头边界、切割镜头片段、调用通义千问多模态模型生成镜头语言分析，并导出 Excel/PDF 报告。

ShotLoom = Shot + Loom，寓意把分散的镜头编织成可阅读、可复盘、可导出的叙事脉络。

## 功能特性

- 自动镜头检测：基于 PySceneDetect 的 ContentDetector + AdaptiveDetector 检测硬切、渐变和溶解。
- AI 镜头分析：调用 DashScope/Qwen 多模态能力，分析景别、运镜、构图、光影、节奏、叙事功能等。
- 整体连贯性分析：基于已分析镜头生成全片结构、节奏和叙事报告。
- 实时进度：使用 SSE 展示切片和 AI 分析进度，刷新页面后可恢复任务状态。
- 用户与积分：支持邮箱密码登录、微信扫码登录、积分扣减、管理员设置积分。
- 导出报告：支持 Excel 和 PDF 导出。
- 管理后台：管理员可查看用户、视频、积分流水并启用/禁用用户。

## 技术栈

### 后端

- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- PyAV + PySceneDetect
- DashScope/Qwen 多模态模型
- JWT + bcrypt
- openpyxl + WeasyPrint

### 前端

- React 18 + TypeScript
- Vite
- Ant Design / Ant Design Pro Components
- Tailwind CSS v4
- Axios
- React Router
- React Hook Form + Zod

## 项目结构

```text
.
├── backend/
│   ├── routers/              # API 路由
│   ├── services/             # 镜头检测、切片、AI 分析、导出等业务逻辑
│   ├── prompts/              # AI 分析提示词
│   ├── auth.py               # JWT、密码哈希、当前用户依赖
│   ├── config.py             # 后端配置
│   ├── database.py           # SQLAlchemy 模型和数据库初始化
│   ├── main.py               # FastAPI 入口
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # 镜头列表、时间线、详情面板等组件
│   │   ├── contexts/         # 认证上下文
│   │   ├── hooks/            # SSE 进度 Hook
│   │   ├── pages/            # 首页、登录、分析页、管理后台
│   │   ├── types/            # TypeScript 类型
│   │   └── utils/            # API 客户端
│   ├── package.json
│   └── vite.config.ts
├── .env.example              # 环境变量示例
├── LICENSE                   # MIT License
├── README.md                 # 中文说明
├── README.en.md              # English README
└── start.sh                  # 本地一键启动脚本
```

## 环境要求

- Python 3.10+
- Node.js 18+（建议 20+）
- npm
- FFmpeg/系统编解码环境（PyAV、WeasyPrint 在不同系统上可能需要额外系统依赖）
- DashScope API Key

## 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd 视频
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
SECRET_KEY=replace-with-a-random-strong-secret
ENV=development
```

常用可选配置：

```env
MODEL_NAME=qwen3.5-omni-flash
CONTINUITY_MODEL_NAME=qwen-max
PROMPT_CONFIG_PATH=backend/prompt_configs/default.json
MIN_MODEL_VIDEO_DURATION=2.0
SCENE_THRESHOLD=27
AI_CONCURRENCY=2
MAX_UPLOAD_SIZE_MB=1024
INITIAL_CREDITS=100
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```


### 自定义 Prompt 与分析字段

默认配置在 `backend/prompt_configs/default.json`。你可以复制一份 JSON 后通过 `PROMPT_CONFIG_PATH` 指向它，用来调整：

- 单镜头分析的角色设定、提示词和输出字段：`shot_fields`
- 整体分析的提示词和输出字段：`continuity_fields`
- 整体分析汇总每个镜头时使用哪些字段：`continuity_summary_fields`

字段支持嵌套结构和数组类型。修改后重启 `backend` 和 `worker` 生效；Docker 部署时如果配置文件不在镜像内，需要额外挂载到容器中。

微信登录可选配置：

```env
WECHAT_APP_ID=wx_your_app_id
WECHAT_APP_SECRET=your_wechat_app_secret
WECHAT_CALLBACK_URL=http://localhost:8000/api/auth/wechat/callback
```

### 3. 一键启动

```bash
chmod +x start.sh
./start.sh
```

启动后访问：

- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- OpenAPI 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

> `start.sh` 会创建后端虚拟环境、安装 Python 依赖，并在前端 `node_modules` 不存在时执行 `npm install`。


## Docker Compose 一键部署

复制 Docker 环境变量模板：

```bash
cp .env.docker.example .env
```

编辑 `.env`，至少替换：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
SECRET_KEY=replace-with-a-random-strong-secret-at-least-32-chars
POSTGRES_PASSWORD=replace-with-a-random-db-password
FRONTEND_URL=http://localhost:8080
CORS_ORIGINS=http://localhost:8080
```

启动整套服务：

```bash
docker compose up -d --build
```

默认服务：

- 前端/Nginx：http://localhost:8080
- 后端 API：容器内 `backend:8000`，由前端 Nginx 代理 `/api`
- PostgreSQL：持久化到 `postgres_data` volume
- Redis/RQ：用于分析任务队列和限流
- Worker：后台执行视频切片和 AI 分析


#### Docker 挂载自定义 Prompt 配置

如果你想把 prompt/字段配置放在仓库外部，可以新建 `docker-compose.override.yml`：

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

然后复制默认配置并修改：

```bash
mkdir -p prompt_configs
cp backend/prompt_configs/default.json prompt_configs/custom.json
docker compose up -d --build backend worker
```

常用命令：

```bash
docker compose logs -f backend worker
docker compose ps
docker compose down
```


### 管理员账号

首次部署后创建管理员：

```bash
docker compose exec backend python manage.py create-admin admin@example.com --password 'change-me-now'
```

重置密码：

```bash
docker compose exec backend python manage.py reset-password admin@example.com --password 'new-password'
```

### 数据库迁移

容器启动时默认执行：

```bash
alembic upgrade head
```

手动执行：

```bash
docker compose exec backend alembic upgrade head
```

### 备份与恢复

备份 Postgres 和媒体 volume：

```bash
scripts/backup.sh
```

恢复：

```bash
scripts/restore.sh backups/YYYYmmdd-HHMMSS
```

### Docker 冒烟测试

```bash
scripts/smoke_docker.sh
```

生产建议：

- 使用 HTTPS 反向代理后设置 `COOKIE_SECURE=true`。
- 将 `FRONTEND_URL` / `CORS_ORIGINS` 改为你的真实域名。
- 不要使用模板里的 `SECRET_KEY` 和 `POSTGRES_PASSWORD`。
- 大文件上传限制同时受 `MAX_UPLOAD_SIZE_MB` 和 Nginx `client_max_body_size` 影响。

## 手动开发

### 后端

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

如果直接在 `backend/` 目录启动，请确保环境变量已经导出，或在 `backend/.env` 中提供配置。

### 前端

```bash
cd frontend
npm install
npm run dev
```

本地开发时，Vite 会把 `/api` 代理到 `http://localhost:8000`。

## 构建与检查

```bash
# 前端类型检查和生产构建
cd frontend
npm run build

# 前端 lint
npm run lint

# 后端测试
cd ../backend
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

如果测试环境没有安装全部视频/系统依赖，部分后端测试可能需要先补齐依赖或改用内存测试替身。

## 使用流程

1. 注册或登录账号。
2. 上传视频文件。
3. 点击镜头检测，生成镜头列表和缩略图。
4. 选择全部或部分镜头进行 AI 分析。
5. 根据需要选择镜头生成整体连贯性报告。
6. 导出 Excel 或 PDF 报告。
7. 管理员可以进入管理后台查看用户和积分。

## API 概览

主要接口前缀为 `/api`：

- `POST /api/auth/register`：邮箱注册
- `POST /api/auth/login`：邮箱登录
- `GET /api/auth/me`：当前用户
- `GET /api/auth/wechat/login`：微信登录入口
- `POST /api/upload`：上传视频
- `GET /api/videos`：视频列表
- `POST /api/detect/{video_id}`：镜头检测
- `POST /api/analyze/{video_id}`：启动 AI 分析
- `GET /api/progress/{task_id}`：SSE 任务进度
- `GET /api/results/{video_id}`：分析结果
- `POST /api/reanalyze-continuity/{video_id}`：生成/重生成整体分析
- `GET /api/export/{video_id}?format=excel|pdf`：导出报告
- `GET /api/admin/users`：管理员用户列表

完整接口以本地 `/docs` 为准。

## 安全与部署建议

- 所有视频读写、检测、分析、导出接口都要求登录并校验资源归属。
- 生产环境会拒绝默认或过短的 `SECRET_KEY`。
- 上传文件使用 UUID 存储名并限制大小；公网部署时仍建议在反向代理层设置请求体上限。
- CORS 白名单、数据库地址等已支持环境变量配置。
- 不要提交 `.env`、数据库、上传视频、日志、管理员凭据和生成产物。

## 贡献

欢迎提交 Issue 和 Pull Request。建议在 PR 中说明：

- 修改动机和用户影响
- 是否涉及数据库结构或环境变量
- 本地执行过的测试命令
- 截图或录屏（如果修改了前端界面）

## 许可证

本项目采用 [MIT License](./LICENSE) 开源。
