#!/bin/bash
set -e

# 加载环境变量
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "=== 启动后端 ==="
cd backend

# 创建虚拟环境（若不存在）
if [ ! -d .venv ]; then
  echo "创建虚拟环境..."
  python3 -m venv .venv
fi

# 安装/更新依赖
.venv/bin/pip install -r requirements.txt -q

# 启动后端
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

echo "=== 启动前端 ==="
cd frontend
source ~/.nvm/nvm.sh 2>/dev/null || true
nvm use 22 2>/dev/null || true
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✓ 后端运行在 http://localhost:8000"
echo "✓ 前端运行在 http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
