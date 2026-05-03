# ShotLoom Frontend

ShotLoom 前端基于 React + TypeScript + Vite 构建，支持视频上传、镜头检测、AI 分析和导出功能。

## 功能特性

- 🎬 视频上传与管理
- 🔍 自动镜头检测
- 🤖 AI 智能分析（镜头内容、连贯性、节奏）
- 👥 用户认证系统（邮箱/密码 + 微信登录）
- 💰 积分系统
- 👨‍💼 管理后台
- 📊 实时进度显示
- 📄 多格式导出（Excel、PDF）

## 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **路由**: React Router v6
- **UI 组件**: Ant Design + Ant Design Pro Components
- **样式**: Tailwind CSS
- **HTTP 客户端**: Axios
- **表单**: React Hook Form + Zod

## 环境变量配置

### 本地开发

创建 `.env.development` 文件（可选，已有默认配置）：

```env
# API 基础地址（本地开发通过 Vite proxy 转发，留空即可）
VITE_API_BASE_URL=

# 应用标题
VITE_APP_TITLE=ShotLoom Dev
```

### 生产部署

在 Vercel 或其他部署平台设置以下环境变量：

```env
# 后端 API 地址（必填）
VITE_API_BASE_URL=https://your-backend-api.com

# 应用标题
VITE_APP_TITLE=ShotLoom
```

## 快速开始

### 安装依赖

```bash
npm install
```

### 本地开发

```bash
npm run dev
```

应用将在 http://localhost:5173 启动。

**注意**：本地开发需要后端服务运行在 http://localhost:8000，或修改 `vite.config.ts` 中的 proxy 配置。

### 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist` 目录。

### 预览生产构建

```bash
npm run preview
```

## Vercel 部署指南

### 1. 导入项目

1. 登录 [Vercel](https://vercel.com)
2. 点击 "New Project"
3. 导入 GitHub 仓库：`Supreme-Ultimate/frontend-video-analysis`

### 2. 配置构建设置

Vercel 会自动检测 Vite 项目，使用以下默认配置：

- **Framework Preset**: Vite
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Install Command**: `npm install`

### 3. 配置环境变量

在 Vercel 项目设置中添加环境变量：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `VITE_API_BASE_URL` | `https://your-backend-api.com` | 后端 API 地址（必填） |
| `VITE_APP_TITLE` | `ShotLoom` | 应用标题（可选） |

**重要**：`VITE_API_BASE_URL` 必须是完整的 URL，包括协议（http:// 或 https://），不要以斜杠结尾。

### 4. 部署

点击 "Deploy" 按钮，Vercel 将自动构建并部署应用。

### 5. 自定义域名（可选）

在 Vercel 项目设置中可以添加自定义域名。

## 项目结构

```
frontend/
├── src/
│   ├── components/          # 可复用组件
│   │   ├── VideoUploader.tsx
│   │   ├── ShotList.tsx
│   │   ├── ShotTimeline.tsx
│   │   ├── ShotDetailPanel.tsx
│   │   ├── ContinuityReport.tsx
│   │   └── CreditsDisplay.tsx
│   ├── pages/               # 页面组件
│   │   ├── HomePage.tsx
│   │   ├── LoginPage.tsx
│   │   ├── RegisterPage.tsx
│   │   ├── AnalysisPage.tsx
│   │   └── admin/           # 管理后台页面
│   │       ├── AdminLayout.tsx
│   │       ├── AdminUsers.tsx
│   │       └── AdminUserDetail.tsx
│   ├── contexts/            # React Context
│   │   └── AuthContext.tsx
│   ├── hooks/               # 自定义 Hooks
│   │   └── useSSEProgress.ts
│   ├── utils/               # 工具函数
│   │   └── api.ts           # Axios 实例配置
│   ├── types/               # TypeScript 类型定义
│   │   └── analysis.ts
│   ├── config.ts            # 应用配置
│   ├── App.tsx              # 根组件
│   ├── main.tsx             # 入口文件
│   └── index.css            # 全局样式
├── public/                  # 静态资源
├── .env.example             # 环境变量示例
├── .env.development         # 开发环境配置
├── .env.production          # 生产环境配置
├── vite.config.ts           # Vite 配置
├── vercel.json              # Vercel 部署配置
└── package.json             # 项目依赖
```

## API 配置说明

前端通过 `src/utils/api.ts` 中的 Axios 实例与后端通信：

- **开发环境**：通过 Vite proxy 转发到 `http://localhost:8000`
- **生产环境**：使用 `VITE_API_BASE_URL` 环境变量指定的后端地址

所有 API 请求会自动：
- 添加 JWT token（从 localStorage 读取）
- 处理 401 错误（自动跳转登录页）
- 设置统一的超时时间（30 秒）

## 常见问题

### 1. 本地开发时 API 请求失败

确保后端服务运行在 `http://localhost:8000`，或修改 `vite.config.ts` 中的 proxy 配置。

### 2. Vercel 部署后 API 请求失败

检查 `VITE_API_BASE_URL` 环境变量是否正确配置，确保：
- 包含完整的协议（http:// 或 https://）
- 不以斜杠结尾
- 后端服务已启动且可访问

### 3. 微信登录回调失败

确保后端配置的 `FRONTEND_URL` 与实际部署的前端地址一致。

## 开发指南

### 添加新页面

1. 在 `src/pages/` 创建新组件
2. 在 `src/App.tsx` 中添加路由
3. 如需认证，使用 `<RequireAuth>` 包裹
4. 如需管理员权限，使用 `<RequireAdmin>` 包裹

### 调用 API

```typescript
import api from '../utils/api'

// GET 请求
const response = await api.get('/api/videos')

// POST 请求
const response = await api.post('/api/upload', formData)

// 带参数的请求
const response = await api.get('/api/videos', {
  params: { page: 1, pageSize: 20 }
})
```

### 使用认证状态

```typescript
import { useAuth } from '../contexts/AuthContext'

function MyComponent() {
  const { user, token, loading, login, logout } = useAuth()

  if (loading) return <div>加载中...</div>
  if (!user) return <div>未登录</div>

  return <div>欢迎，{user.display_name}</div>
}
```

## License

MIT

## 相关链接

- [后端仓库](https://github.com/Supreme-Ultimate/video-analysis)
- [Vercel 文档](https://vercel.com/docs)
- [Vite 文档](https://vitejs.dev/)
- [React Router 文档](https://reactrouter.com/)
