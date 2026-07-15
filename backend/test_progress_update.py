"""
测试脚本：验证 SSE 进度更新是否正常工作
"""
import asyncio
import time
import pytest

pytestmark = pytest.mark.asyncio

# 模拟 _task_progress 字典
_task_progress = {}

async def simulate_analyze_one(shot_index: int, task_id: str, progress_lock: asyncio.Lock):
    """模拟单个镜头分析"""
    global done

    # 模拟 AI 分析耗时
    await asyncio.sleep(0.5)

    # 更新进度
    async with progress_lock:
        done += 1
        _task_progress[task_id] = {"stage": "analyzing", "done": done, "total": total}
        print(f"[进度更新] 镜头 {shot_index} 完成: done={done}/{total}, progress={_task_progress[task_id]}")

async def test_concurrent_progress():
    """测试并发进度更新"""
    global done, total

    task_id = "test_task_1"
    total = 6
    done = 0

    # 初始化进度
    _task_progress[task_id] = {"stage": "analyzing", "done": 0, "total": total}
    print(f"[初始化] task_id={task_id}, progress={_task_progress[task_id]}")

    progress_lock = asyncio.Lock()

    # 并发执行 6 个镜头分析
    tasks = [simulate_analyze_one(i, task_id, progress_lock) for i in range(total)]
    await asyncio.gather(*tasks)

    # 检查最终进度
    final_progress = _task_progress[task_id]
    print(f"\n[最终结果] progress={final_progress}")

    if final_progress["done"] == total:
        print("✅ 测试通过：进度更新正确")
    else:
        print(f"❌ 测试失败：done={final_progress['done']}, 期望={total}")

if __name__ == "__main__":
    asyncio.run(test_concurrent_progress())
