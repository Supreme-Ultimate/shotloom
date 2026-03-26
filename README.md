# 视频拉片工具

一个基于 AI 的视频分析工具，支持自动镜头检测、AI 分析和整体连贯性分析。

## 功能特点

### 核心功能
- 🎬 **自动镜头检测**：使用 PySceneDetect 自动识别视频中的镜头切换
- 🤖 **AI 镜头分析**：使用 Qwen3.5-Flash 多模态模型分析每个镜头的内容
- 📊 **整体分析**：基于选中的镜头生成整体连贯性分析报告
- 📤 **导出功能**：支持导出为 Excel 和 PDF 格式

### 用户系统
- 👤 **用户认证**：支持邮箱/密码注册和微信扫码登录
- 💰 **积分系统**：按镜头数量消耗积分，新用户默认 100 积分
- 🔐 **权限管理**：管理员可查看所有用户数据和重置积分

### 高级特性
- ⚡ **异步分析**：支持并发分析多个镜头，提高处理速度
- 🔄 **任务恢复**：刷新页面后自动恢复正在进行的分析任务
- ✅ **选择性分析**：可以选择特定镜头进行分析或整体分析
- 📝 **实时进度**：使用 SSE 实时显示分析进度

## 技术栈

### 后端
- **框架**：FastAPI
- **数据库**：SQLite + SQLAlchemy
- **AI 模型**：Qwen3.5-Flash (通义千问多模态模型)
- **视频处理**：PyAV, PySceneDetect
- **认证**：JWT + fastapi-users
- **导出**：openpyxl, WeasyPrint

### 前端
- **框架**：React 18 + TypeScript
- **构建工具**：Vite
- **UI 组件**：shadcn/ui + Ant Design Pro Components
- **样式**：Tailwind CSS
- **状态管理**：React Hooks
- **HTTP 客户端**：Axios

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- FFmpeg (用于视频处理)

### 安装步骤

1. **克隆仓库**
```bash
git clone <repository-url>
cd 视频
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置
```

必需的环境变量：
- `DASHSCOPE_API_KEY`: 阿里云 DashScope API 密钥
- `SECRET_KEY`: JWT 签名密钥（生产环境必须设置）

3. **启动服务**
```bash
chmod +x start.sh
./start.sh
```

4. **访问应用**
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 默认管理员账号
- 邮箱：admin@example.com
- 密码：admin123

## 使用指南

### 基本工作流程

1. **上传视频** → 登录后上传视频文件
2. **镜头检测** → 自动识别镜头切换点
3. **AI 分析** → 选择镜头进行 AI 分析
4. **整体分析** → 选择镜头生成整体分析报告
5. **导出结果** → 导出为 Excel 或 PDF

## 项目结构

```
视频/
├── backend/                 # 后端代码
│   ├── routers/            # API 路由
│   ├── services/           # 业务逻辑
│   ├── database.py         # 数据库模型
│   ├── auth.py            # 认证配置
│   └── main.py            # 应用入口
├── frontend/               # 前端代码
│   ├── src/
│   │   ├── pages/         # 页面组件
│   │   ├── components/    # UI 组件
│   │   └── hooks/         # 自定义 Hooks
│   └── package.json
├── .gitignore
├── .env.example
├── start.sh
└── README.md
```

## 配置说明

### 后端配置
- `DASHSCOPE_API_KEY`: 阿里云 DashScope API 密钥
- `MODEL_NAME`: AI 模型名称（默认：qwen3.5-flash）
- `SCENE_THRESHOLD`: 镜头检测阈值（默认：27）
- `AI_CONCURRENCY`: AI 分析并发数（默认：500）
- `INITIAL_CREDITS`: 新用户默认积分（默认：100）

## 许可证

MIT License

---

🤖 Built with Claude Code