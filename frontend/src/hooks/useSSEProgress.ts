import { useEffect, useRef, useState } from 'react'
import { TaskProgress } from '../types/analysis'

export function useSSEProgress(taskId: string | null) {
  const [progress, setProgress] = useState<TaskProgress | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) {
      console.log('[useSSEProgress] taskId 为空，不建立 SSE 连接')
      return
    }

    console.log('[useSSEProgress] 建立 SSE 连接，taskId:', taskId)
    const es = new EventSource(`/api/progress/${taskId}`)
    esRef.current = es

    es.onopen = () => {
      console.log('[useSSEProgress] SSE 连接已建立')
    }

    es.onmessage = (e) => {
      try {
        const data: TaskProgress = JSON.parse(e.data)
        console.log('[useSSEProgress] 收到进度更新:', data)
        setProgress(data)
        if (data.stage === 'completed' || data.stage === 'error') {
          console.log('[useSSEProgress] 任务结束，关闭 SSE 连接')
          es.close()
        }
      } catch (err) {
        console.error('[useSSEProgress] 解析进度数据失败:', err)
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
  }, [taskId])

  return progress
}
