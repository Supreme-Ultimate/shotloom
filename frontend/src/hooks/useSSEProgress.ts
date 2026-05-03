import { useEffect, useRef, useState } from 'react'
import { TaskProgress } from '../types/analysis'
import { API_BASE_URL } from '../config'

export function useSSEProgress(taskId: string | null, initialTotal?: number) {
  const [progress, setProgress] = useState<TaskProgress | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) {
      console.log('[useSSEProgress] taskId 为空，不建立 SSE 连接')
      // taskId 为空时清空 progress
      setProgress(null)
      return
    }

    console.log('[useSSEProgress] 建立 SSE 连接，taskId:', taskId)

    // 立即设置一个临时的 progress 状态，显示"分析中"
    // 这样用户能立即看到进度条，而不是等待 SSE 连接
    setProgress({
      stage: 'analyzing',
      done: 0,
      total: initialTotal ?? 0,
    })

    const es = new EventSource(`${API_BASE_URL}/api/progress/${taskId}`, { withCredentials: true })
    esRef.current = es

    es.onopen = () => {
      console.log('[useSSEProgress] SSE 连接已建立')
    }

    es.onmessage = (e) => {
      try {
        const data: TaskProgress = JSON.parse(e.data)
        console.log('[useSSEProgress] 收到进度更新:', {
          taskId,
          stage: data.stage,
          done: data.done,
          total: data.total,
          rawData: data
        })
        setProgress(data)

        // 延迟关闭连接，确保 setProgress 已被处理
        if (data.stage === 'completed' || data.stage === 'error' || data.stage === 'cancelled') {
          console.log('[useSSEProgress] 任务结束，将在下一个事件循环关闭 SSE 连接', {
            stage: data.stage,
            done: data.done,
            total: data.total
          })
          // 使用 setTimeout 确保 React 状态更新完成
          setTimeout(() => {
            console.log('[useSSEProgress] 关闭 SSE 连接')
            es.close()
          }, 0)
        }
      } catch (err) {
        console.error('[useSSEProgress] 解析进度数据失败:', err, 'raw data:', e.data)
      }
    }

    es.onerror = (err) => {
      console.error('[useSSEProgress] SSE 连接错误:', err)
      es.close()
    }

    return () => {
      console.log('[useSSEProgress] 清理 SSE 连接')
      es.close()
    }
  }, [taskId])  // 移除 initialTotal 依赖，避免重复建立连接

  return progress
}
