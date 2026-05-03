"""
测试脚本：验证进度更新修复是否有效
"""
import asyncio

# 模拟全局进度字典
_task_progress = {}

async def test_progress_update():
    """测试并发进度更新（使用字典而不是 nonlocal 变量）"""
    task_id = "test_task"
    total = 5

    # 初始化进度
    _task_progress[task_id] = {"stage": "analyzing", "done": 0, "total": total}
    print(f"初始进度: {_task_progress[task_id]}")

    # 使用字典存储进度状态
    progress_state = {"done": 0}
    progress_lock = asyncio.Lock()

    async def analyze_one(shot_index):
        """模拟分析一个镜头"""
        await asyncio.sleep(0.1)  # 模拟分析耗时

        # 更新进度
        async with progress_lock:
            progress_state["done"] += 1
            current_done = progress_state["done"]
            _task_progress[task_id] = {"stage": "analyzing", "done": current_done, "total": total}
            print(f"[进度更新] 镜头 {shot_index} 完成: done={current_done}/{total}, progress={_task_progress[task_id]}")

    # 并发执行
    await asyncio.gather(*[analyze_one(i) for i in range(total)])

    # 验证最终结果
    final_progress = _task_progress[task_id]
    print(f"\n最终进度: {final_progress}")

    if final_progress["done"] == total:
        print("✅ 测试通过：进度更新正确")
    else:
        print(f"❌ 测试失败：期望 done={total}，实际 done={final_progress['done']}")

if __name__ == "__main__":
    asyncio.run(test_progress_update())
