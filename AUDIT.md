# ShotLoom 技术审计报告

审计日期：2026-05-02  
范围：`backend/`、`frontend/`、根目录启动与部署配置  
结论：已修复主要 P0/P1 安全与部署阻塞项；ShotLoom 适合作为自托管的镜头分析工作台使用。面向公网生产环境时，建议继续补充反向代理限流、持久化任务队列和更完整的移动端/可访问性 QA。

## 总体评分

| 维度 | 分数 | 关键发现 |
|---|---:|---|
| 后端安全 | 3/4 | 已强制登录并校验资源归属；公网部署仍需反向代理限流和更细审计。 |
| 后端可靠性 | 2/4 | 全局内存任务进度和 SQLite 仍更适合单进程本地运行，不适合多实例部署。 |
| 前端可访问性 | 2/4 | 多处图标按钮、拖拽上传和自定义交互缺少完整键盘/ARIA 支持。 |
| 前端响应式 | 2/4 | 首页较好，分析工作台三栏和拖拽 resize 在移动端风险较高。 |
| 项目完备度 | 4/4 | 已补齐 README、英文 README、MIT License、审计报告和基础安全修复。 |
| 合计 | 14/20 | Good：可自托管使用，生产环境继续补强可靠性和可访问性。 |

## 已修复的 P0/P1 问题

### 1. 视频资源接口缺少强制认证和归属校验

- 位置：`backend/routers/upload.py:45`、`backend/routers/upload.py:96`、`backend/routers/upload.py:120`、`backend/routers/upload.py:138`
- 位置：`backend/routers/analysis.py:40`、`backend/routers/analysis.py:96`、`backend/routers/analysis.py:158`、`backend/routers/analysis.py:181`
- 位置：`backend/routers/results.py:14`、`backend/routers/results.py:48`、`backend/routers/results.py:113`、`backend/routers/results.py:134`、`backend/routers/export.py:11`
- 影响：未登录用户可以上传、列出历史匿名视频、读取任意 `video_id` 的视频/缩略图/分析结果，甚至触发检测、分析、删除等操作。只要猜到递增 ID，就可能访问他人视频内容。
- 状态：已修复。默认使用 `get_current_user`，并新增 `get_video_for_user(video_id, current_user, db)` 统一校验资源归属；管理员可访问全部，普通用户只能访问自己的视频。

### 2. 默认 JWT 密钥可导致生产环境令牌伪造

- 位置：`backend/config.py:31`
- 影响：如果部署者忘记配置 `SECRET_KEY`，攻击者可以用公开默认值签发任意用户 token。
- 状态：已修复。`ENV=production` 时发现默认、空或过短密钥会启动失败。

### 3. 上传缺少大小限制和文件名净化

- 位置：`backend/routers/upload.py:51`、`backend/routers/upload.py:57`
- 影响：攻击者可上传超大文件耗尽磁盘；原始文件名直接参与路径和响应，存在路径/特殊字符/覆盖管理风险。
- 状态：已部分修复。已使用 UUID 存储文件名并增加应用层大小限制；公网部署仍建议增加 MIME/文件头校验和反向代理请求体限制。

## P1 主要问题

### 4. 删除接口在未登录时可删除匿名视频

- 位置：`backend/routers/upload.py:138`
- 影响：`current_user` 为 `None` 时权限分支不会拦截；匿名上传的视频可以被任意未登录请求删除。
- 状态：已修复。删除接口必须登录并通过资源归属校验。

### 5. AI 并发默认值过高

- 位置：`backend/config.py:28`
- 影响：`AI_CONCURRENCY=500` 容易触发 API 限流、内存压力和成本失控；`.env.example` 写的是 2，代码默认是 500，文档和实现不一致。
- 状态：已部分修复。默认并发已改为 2；队列/限流/取消任务仍建议后续加入。

### 6. 任务进度只存在进程内存

- 位置：`backend/routers/analysis.py:24`
- 影响：服务重启、多 worker、多实例部署后 SSE 进度丢失；`task_id = task_{video_id}` 也不支持同视频并行任务。
- 状态：已部分修复。task id 已改为 UUID；Redis/数据库任务表仍建议后续加入。

### 7. 微信 OAuth state 固定且 token 进入 URL 查询串

- 位置：`backend/routers/wechat.py:26`、`backend/routers/wechat.py:88`
- 影响：固定 `state` 不能防 CSRF；一次性登录 code 出现在 URL 中会进入浏览器历史、代理日志和 Referer。
- 状态：已部分修复。已生成一次性 state 并服务端校验；已改为一次性 code 换 token；后续生产环境仍建议使用 HttpOnly Secure Cookie。

### 8. CORS 白名单硬编码

- 位置：`backend/main.py:28`
- 影响：生产域名需要改代码；预览环境、多域名部署不方便。
- 状态：已修复。新增 `CORS_ORIGINS` 环境变量并解析为列表。

### 9. 前端生产 SSE 没有使用 `VITE_API_BASE_URL`

- 位置：`frontend/src/hooks/useSSEProgress.ts:26`
- 影响：前后端分域部署时 Axios 请求可以走 `VITE_API_BASE_URL`，但 SSE 仍请求当前域 `/api/progress/...`，导致生产进度失效。
- 状态：已修复。前端基于 `API_BASE_URL` 构造 EventSource URL。

## P2 次要问题

### 10. 前端 token 存在 localStorage

- 位置：`frontend/src/contexts/AuthContext.tsx:35`、`frontend/src/utils/api.ts:20`
- 影响：一旦出现 XSS，token 可被读取。
- 建议：生产环境优先使用 HttpOnly Secure SameSite Cookie；同时补充 CSP。

### 11. 前端残留 Vite 示例 CSS

- 位置：`frontend/src/App.css:1`
- 影响：虽然当前 `App.tsx` 未引入 `App.css`，但示例样式容易造成维护混乱。
- 状态：已修复。未使用的 `frontend/src/App.css` 已删除。

### 12. 设计 token 和颜色硬编码较多

- 位置：`frontend/src/index.css:6`、多处 `className="bg-[#0f0f14] ..."`
- 影响：主题一致性和可维护性一般，深色界面替换成本较高。
- 建议：抽出 CSS 变量或 Tailwind theme tokens。

### 13. 分析工作台移动端适配风险

- 位置：`frontend/src/pages/AnalysisPage.tsx`
- 影响：左右面板 resize、时间线、视频区域更像桌面工作台；窄屏下操作成本较高。
- 建议：移动端改成分段 tabs/抽屉布局，隐藏 resize handle，保证 44px 触控目标。

### 14. 测试依赖未写入 requirements

- 位置：`backend/test_e2e.py`
- 影响：测试使用 `pytest`，但 `backend/requirements.txt` 没有包含测试依赖，新贡献者无法按 README 直接运行。
- 状态：已修复。已新增 `backend/requirements-dev.txt` 并同步 README。

## 正向发现

- `.gitignore` 已覆盖 `.env`、数据库、上传文件、切片、缩略图、日志和管理员凭据。
- 后端分层清晰，路由、服务、提示词、数据模型拆分合理。
- 前端 API 客户端统一处理 token 和 401，基本开发体验清晰。
- 视频播放接口支持 Range 请求，对大视频拖动播放友好。
- 已有端到端测试雏形，覆盖认证、积分、上传、管理员等核心流程。
- README、README.en.md 和 LICENSE 已补齐，项目基础材料已具备。

## 建议修复顺序

1. 后续：补充 Redis/数据库任务表，支持多 worker、多实例和任务取消。
2. 后续：将会话存储升级为 HttpOnly Secure Cookie。
3. 后续：增加 MIME/文件头校验、反向代理请求体上限和 API rate limit。
4. 后续：补齐移动端分析页适配和可访问性。
5. 后续：增加 CI，固定前后端测试矩阵。

## 发布清单

- [x] 添加 MIT License。
- [x] 添加中文 README。
- [x] 添加英文 README。
- [x] 添加审计报告。
- [ ] 确认仓库历史中没有真实 `.env`、API Key、数据库、视频和管理员凭据。
- [x] 修复主要 P0 安全问题。
- [ ] 配置 GitHub 仓库描述、topics、Issue/PR 模板和安全策略。
