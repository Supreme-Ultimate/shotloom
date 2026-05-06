import { useEffect, useRef, useState } from 'react'
import { message } from 'antd'
import api from '../utils/api'
import { API_BASE_URL } from '../config'
import { AnalysisResult, Shot, TaskProgress } from '../types/analysis'
import ShotList from '../components/ShotList'
import ShotDetailPanel from '../components/ShotDetailPanel'
import ShotTimeline from '../components/ShotTimeline'
import ContinuityReport from '../components/ContinuityReport'
import SegmentReport from '../components/SegmentReport'
import { useSSEProgress } from '../hooks/useSSEProgress'
import { getApiErrorData, getApiErrorMessage, getApiErrorStatus } from '../utils/error'

interface Props {
  videoId: number
  onBack: () => void
}

type RightTab = 'detail' | 'segments' | 'continuity'

function formatElapsed(seconds: number) {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return mins > 0 ? `${mins}分${secs.toString().padStart(2, '0')}秒` : `${secs}秒`
}

function ProgressBar({ progress }: { progress: TaskProgress }) {
  const [now, setNow] = useState(Date.now())
  const startedAtRef = useRef(Date.now())

  useEffect(() => {
    if (progress.stage === 'completed' || progress.stage === 'error' || progress.stage === 'cancelled') return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [progress.stage])

  useEffect(() => {
    startedAtRef.current = Date.now()
  }, [])

  const elapsed = Math.max(0, Math.floor((now - startedAtRef.current) / 1000))
  const isIndeterminate = progress.stage === 'analyzing' && (progress.total ?? 0) <= 1 && (progress.done ?? 0) === 0
  const analyzingLabel = progress.msg ?? `AI 分析中 ${progress.done ?? 0}/${progress.total ?? 0}`
  const labels: Record<string, string> = {
    starting: '初始化…',
    cutting_clips: '切割镜头片段…',
    analyzing: isIndeterminate ? `${analyzingLabel} · 已进行 ${formatElapsed(elapsed)}` : analyzingLabel,
    continuity: `生成整体分析… · 已进行 ${formatElapsed(elapsed)}`,
    completed: '分析完成',
    error: `错误：${progress.msg}`,
    cancelled: progress.msg ?? '分析已中断',
  }
  const pct = progress.total
    ? Math.round(((progress.done ?? 0) / progress.total) * 100)
    : progress.stage === 'completed' ? 100 : 0

  return (
    <div className="bg-[#1a1a2e] border-b border-gray-800 px-4 py-2 flex items-center gap-3">
      <div className="flex-1">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span className="inline-flex items-center gap-2">
            {isIndeterminate || progress.stage === 'continuity' ? <span className="h-2 w-2 rounded-full bg-indigo-400 animate-pulse" /> : null}
            {labels[progress.stage] ?? progress.stage}
          </span>
          <span>{isIndeterminate || progress.stage === 'continuity' ? '处理中' : `${pct}%`}</span>
        </div>
        {isIndeterminate || progress.stage === 'continuity' ? (
          <div className="w-full bg-gray-700 rounded-full h-1.5 overflow-hidden">
            <div className="h-1.5 w-1/3 rounded-full bg-indigo-500 animate-pulse" />
          </div>
        ) : (
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div
              className={`h-1.5 rounded-full transition-all ${progress.stage === 'error' ? 'bg-red-500' : 'bg-indigo-500'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

function isProgressTerminal(progress: TaskProgress | null) {
  if (!progress) return true
  if (progress.stage === 'completed' || progress.stage === 'error' || progress.stage === 'cancelled' || progress.stage === 'not_found') return true
  return Boolean(progress.total && progress.done !== undefined && progress.done >= progress.total)
}

function updateAnalysisState(
  result: AnalysisResult,
  status: AnalysisResult['video']['status'],
  shots: Shot[],
  overallAnalysis: AnalysisResult['overall_analysis'] = result.overall_analysis,
  segments: AnalysisResult['segments'] = result.segments,
): AnalysisResult {
  return {
    ...result,
    video: {
      ...result.video,
      status,
    },
    shots,
    overall_analysis: overallAnalysis,
    segments,
  }
}

export default function AnalysisPage({ videoId, onBack }: Props) {
  const [data, setData] = useState<AnalysisResult | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [sceneThreshold, setSceneThreshold] = useState(27)
  const [isAnalyzingSelected, setIsAnalyzingSelected] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [isReanalyzingContinuity, setIsReanalyzingContinuity] = useState(false)
  const [continuityLoading, setContinuityLoading] = useState(false)
  const [cancellingAnalysis, setCancellingAnalysis] = useState(false)
  const [rightTab, setRightTab] = useState<RightTab>('detail')
  const [selectedShots, setSelectedShots] = useState<Set<number>>(new Set())
  const [analyzingShots, setAnalyzingShots] = useState<Set<number>>(new Set())
  const [shotCount, setShotCount] = useState<number>(0)
  const [leftWidth, setLeftWidth] = useState(280)
  const [rightWidth, setRightWidth] = useState(400)
  const [isResizingLeft, setIsResizingLeft] = useState(false)
  const [isResizingRight, setIsResizingRight] = useState(false)
  const [shouldStopAtShotEnd, setShouldStopAtShotEnd] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const progress = useSSEProgress(taskId, shotCount)
  const normalizedSceneThreshold = Math.min(100, Math.max(5, sceneThreshold || 27))

  // 加载视频信息
  const loadData = async () => {
    const res = await api.get(`/api/results/${videoId}`)
    setData(res.data)

    // 同步更新 analyzingShots 状态：移除已经有 analysis 的镜头
    if (res.data?.shots) {
      setAnalyzingShots((prev) => {
        const stillAnalyzing = new Set<number>()
        res.data.shots.forEach((s: Shot) => {
          // 如果镜头在 analyzingShots 中但还没有 analysis，保持分析中状态
          if (prev.has(s.index) && !s.analysis) {
            stillAnalyzing.add(s.index)
          }
        })
        console.log('[loadData] 更新 analyzingShots:', { prev: Array.from(prev), stillAnalyzing: Array.from(stillAnalyzing) })
        return stillAnalyzing
      })
    }
  }

  // 页面加载时检查是否有正在进行的任务
  useEffect(() => {
    const init = async () => {
      console.log('[AnalysisPage] 页面初始化，videoId:', videoId)

      // 先加载数据
      await loadData()
      console.log('[AnalysisPage] 数据加载完成')

      // 然后检查任务状态
      try {
        console.log('[AnalysisPage] 开始检查任务状态...')
        const res = await api.get(`/api/videos/${videoId}/task-status`)
        console.log('[AnalysisPage] 任务状态响应:', res.data)

        if (res.data.has_active_task && res.data.task_id) {
          console.log('[AnalysisPage] 发现活跃任务，task_id:', res.data.task_id)
          setTaskId(res.data.task_id)

          // 推断正在分析的镜头：所有未分析的镜头
          const shotsRes = await api.get(`/api/results/${videoId}`)
          if (shotsRes.data?.shots) {
            const unanalyzedIndices = shotsRes.data.shots
              .filter((s: Shot) => !s.analysis)
              .map((s: Shot) => s.index)
            console.log('[AnalysisPage] 未分析的镜头索引:', unanalyzedIndices)
            setAnalyzingShots(new Set(unanalyzedIndices))
            setShotCount(unanalyzedIndices.length)  // 设置 shotCount 以显示正确的进度条
          }
        } else {
          console.log('[AnalysisPage] 没有活跃任务')
        }
      } catch (err) {
        console.error('[AnalysisPage] 检查任务状态失败:', err)
      }
    }

    init()
  }, [videoId])

  // 检测完成、出错或进度已满后清理状态，避免进度事件漏掉 completed 时一直显示“AI 分析中”。
  useEffect(() => {
    if (progress && isProgressTerminal(progress)) {
      setTaskId(null)
      setSelectedShots(new Set())
      setAnalyzingShots(new Set())

      if (progress.stage === 'completed' || progress.stage === 'cancelled' || (progress.total && progress.done !== undefined && progress.done >= progress.total)) {
        console.log('[AnalysisPage] 任务完成，立即刷新数据')
        // 立即刷新数据，并添加重试机制
        const refreshData = async (retryCount = 0) => {
          try {
            await loadData()
            console.log('[AnalysisPage] 任务完成后数据刷新成功')
          } catch (err) {
            console.error('[AnalysisPage] 任务完成后数据刷新失败:', err)
            // 增加重试次数到 5 次，延迟改为 1000ms
            if (retryCount < 5) {
              console.log(`[AnalysisPage] 将在 1000ms 后重试 (${retryCount + 1}/5)`)
              setTimeout(() => refreshData(retryCount + 1), 1000)
            }
          }
        }
        refreshData()
      }
    }
  }, [progress?.stage])

  // 定期刷新分析进度中的镜头数据
  useEffect(() => {
    if (progress?.stage === 'analyzing' || progress?.stage === 'continuity') {
      const timer = setInterval(loadData, 3000)
      return () => clearInterval(timer)
    }
  }, [progress?.stage])

  const handleDetect = async () => {
    if (shots.length > 0) {
      const confirmed = window.confirm(
        '重新检测镜头会清空当前镜头列表、切片和已有分析结果，并重新生成镜头边界。确定继续吗？'
      )
      if (!confirmed) return
    }

    setDetecting(true)
    try {
      setTaskId(null)
      setSelectedShots(new Set())
      setAnalyzingShots(new Set())
      setShotCount(0)
      setSelectedIndex(0)
      setCurrentTime(0)
      setRightTab('detail')
      setData((prev) => prev ? updateAnalysisState(prev, 'detecting', [], undefined) : prev)

      const res = await api.post(`/api/detect/${videoId}`, null, { params: { threshold: normalizedSceneThreshold } })
      setData((prev) => prev ? updateAnalysisState(prev, 'detected', res.data.shots ?? [], undefined) : prev)
      await loadData()
      setSelectedIndex(0)
    } catch (err: unknown) {
      const errorMessage = getApiErrorMessage(err, '镜头检测失败')
      console.error('镜头检测失败:', getApiErrorStatus(err), getApiErrorData(err), errorMessage)
      message.error(errorMessage)
      setData((prev) => prev ? updateAnalysisState(prev, 'error', prev.shots) : prev)
    } finally {
      setDetecting(false)
    }
  }

  const handleAnalyzeSelected = async (indices: number[]) => {
    const selected = shots.filter((shot) => indices.includes(shot.index))
    const alreadyAnalyzed = selected.filter((shot) => shot.analysis && !shot.analysis.error)
    if (alreadyAnalyzed.length > 0) {
      const confirmed = window.confirm(
        `选中的镜头中有 ${alreadyAnalyzed.length} 个已经正常分析过。继续会覆盖这些镜头的分析结果，确定继续吗？`
      )
      if (!confirmed) return
    }

    setIsAnalyzingSelected(true)
    setAnalyzingShots(new Set(indices)) // 标记正在分析的镜头
    setData((prev) => prev ? updateAnalysisState(prev, 'analyzing', prev.shots) : prev)
    try {
      const res = await api.post(`/api/analyze/${videoId}`, {
        shot_indices: indices
      })
      setTaskId(res.data.task_id)
      setShotCount(indices.length) // 存储镜头数量
      setIsAnalyzingSelected(false) // 任务启动成功后立即恢复按钮状态
      // 不要在这里清空选中状态，等任务完成后再清空
    } catch (err: unknown) {
      console.error('分析失败:', getApiErrorStatus(err), getApiErrorData(err), getApiErrorMessage(err, '分析失败'))
      setIsAnalyzingSelected(false)
      setAnalyzingShots(new Set()) // 出错时清空分析中状态
      setData((prev) => prev ? updateAnalysisState(prev, 'error', prev.shots) : prev)
    }
  }

  const handleCancelAnalysis = async () => {
    if (!taskId) return
    const confirmed = window.confirm('确定中断当前 AI 分析吗？已经完成的镜头分析结果会保留。')
    if (!confirmed) return

    setCancellingAnalysis(true)
    try {
      await api.post(`/api/analyze/${videoId}/cancel`, { task_id: taskId })
      setTaskId(null)
      setAnalyzingShots(new Set())
      setSelectedShots(new Set())
      await loadData()
    } catch (err: unknown) {
      console.error('中断分析失败:', getApiErrorStatus(err), getApiErrorData(err), getApiErrorMessage(err, '中断分析失败'))
    } finally {
      setCancellingAnalysis(false)
    }
  }

  const handleAnalyzeContinuity = async (shotIndices: number[]) => {
    setIsReanalyzingContinuity(true)
    setContinuityLoading(true)
    setRightTab('continuity')
    try {
      const res = await api.post(`/api/reanalyze-continuity/${videoId}`, {
        shot_indices: shotIndices
      })
      setData((prev) => prev ? {
        ...prev,
        overall_analysis: res.data.report,
      } : prev)
      await loadData() // 重新加载数据
    } catch (err: unknown) {
      console.error('整体分析失败:', getApiErrorStatus(err), getApiErrorData(err), getApiErrorMessage(err, '整体分析失败'))
    } finally {
      setIsReanalyzingContinuity(false)
      setContinuityLoading(false)
    }
  }

  const handleSeek = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time
      videoRef.current.play().catch(() => {})
    }
  }

  const handleShotSelect = (index: number) => {
    setSelectedIndex(index)
    const shot = data?.shots[index]
    if (shot) {
      setShouldStopAtShotEnd(true) // 点击镜头列表时，设置为在镜头结束时停止
      handleSeek(shot.start_time)
    }
  }

  // 跟踪播放位置
  const handleTimeUpdate = () => {
    if (videoRef.current) {
      const t = videoRef.current.currentTime
      setCurrentTime(t)

      // 只有在点击镜头列表时才在镜头结束时停止
      if (shouldStopAtShotEnd) {
        const selectedShot = data?.shots[selectedIndex]
        if (selectedShot && t >= selectedShot.end_time) {
          videoRef.current.pause()
          setShouldStopAtShotEnd(false) // 停止后重置标志
        }
      }

      // 自动选中当前镜头 - 已禁用，避免播放完自动跳转到下一个分镜
      // const active = data?.shots.find(s => t >= s.start_time && t < s.end_time)
      // if (active && active.index !== selectedIndex) setSelectedIndex(active.index)
    }
  }

  const video = data?.video
  const shots = data?.shots ?? []
  const selectedShot: Shot | null = shots[selectedIndex] ?? null
  const shouldShowProgress = !!(progress && !isProgressTerminal(progress))
  const isTaskRunning = shouldShowProgress
  const canDetect = !!video && !isTaskRunning && !isAnalyzingSelected
  const hasSelectedShotsAnalyzing = Array.from(selectedShots).some(idx => analyzingShots.has(idx))
  const isAnalysisBusy = isTaskRunning || isAnalyzingSelected || cancellingAnalysis

  const handleExport = async (format: 'excel' | 'pdf') => {
    setIsExporting(true)
    try {
      window.open(`${API_BASE_URL}/api/export/${videoId}?format=${format}`, '_blank')
      // 给一个短暂延迟后恢复按钮状态
      setTimeout(() => setIsExporting(false), 1000)
    } catch (err: unknown) {
      console.error('导出失败:', err)
      setIsExporting(false)
    }
  }

  // 左侧拖拽调整宽度
  useEffect(() => {
    if (!isResizingLeft) return
    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(200, Math.min(400, e.clientX))
      setLeftWidth(newWidth)
    }
    const handleMouseUp = () => setIsResizingLeft(false)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizingLeft])

  // 右侧拖拽调整宽度
  useEffect(() => {
    if (!isResizingRight) return
    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(300, Math.min(600, window.innerWidth - e.clientX))
      setRightWidth(newWidth)
    }
    const handleMouseUp = () => setIsResizingRight(false)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizingRight])

  return (
    <div className="flex flex-col h-screen bg-[#0f0f14] overflow-hidden">
      {/* 顶栏 */}
      <div className="flex items-center justify-between px-4 py-2 bg-[#12121f] border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-gray-400 hover:text-white text-sm transition-colors">← 返回</button>
          <h1 className="text-white font-medium text-sm truncate max-w-xs">{video?.filename}</h1>
          {video && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              video.status === 'completed' ? 'bg-emerald-900 text-emerald-300' :
              video.status === 'error' ? 'bg-red-900 text-red-300' :
              'bg-indigo-900 text-indigo-300'
            }`}>{video.status}</span>
          )}
        </div>
        <div className="flex gap-2 items-center">
          {/* 检测镜头按钮 */}
          {canDetect && (
            <div className={`flex items-center gap-2 rounded-lg border px-2 py-1 ${
              shots.length > 0 ? 'border-amber-700 bg-amber-950/30' : 'border-gray-700 bg-gray-900/50'
            }`}>
              <label className="flex items-center gap-1 text-[11px] text-gray-300">
                阈值
                <input
                  type="number"
                  min={5}
                  max={100}
                  step={1}
                  value={sceneThreshold}
                  onChange={(event) => setSceneThreshold(Number(event.target.value))}
                  onBlur={() => setSceneThreshold(normalizedSceneThreshold)}
                  disabled={detecting}
                  className="w-14 rounded border border-gray-700 bg-[#0f0f14] px-1.5 py-0.5 text-xs text-white outline-none focus:border-indigo-500 disabled:opacity-50"
                />
              </label>
              <span
                className="group relative inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-indigo-500/70 bg-indigo-500/10 text-[10px] font-semibold text-indigo-200"
                aria-label="阈值说明"
              >
                i
                <span className="pointer-events-none absolute right-0 top-6 z-50 hidden w-64 rounded-lg border border-gray-700 bg-[#181824] p-3 text-left text-xs leading-5 text-gray-200 shadow-2xl group-hover:block">
                  <span className="mb-1 block font-medium text-white">镜头检测阈值</span>
                  <span className="block text-gray-300">控制画面变化被判断为新镜头的敏感度。阈值越低越敏感，镜头可能越多；阈值越高越保守，镜头可能越少。</span>
                  <span className="mt-1 block text-indigo-200">建议：常规视频 20-35，剪辑快或光线变化大可试 35-50，漏检较多可降到 15-25。</span>
                </span>
              </span>
              <button
                onClick={handleDetect}
                disabled={detecting}
                title={`使用阈值 ${normalizedSceneThreshold} 检测镜头。阈值越低越敏感，镜头可能越多。`}
                className={`text-xs px-3 py-1.5 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 ${
                  shots.length > 0
                    ? 'bg-amber-700 hover:bg-amber-600'
                    : 'bg-gray-700 hover:bg-gray-600'
                }`}
              >
                {detecting && (
                  <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                )}
                {detecting ? '检测中...' : shots.length > 0 ? '重新检测镜头' : '检测镜头'}
              </button>
            </div>
          )}
          {/* 分析选中的镜头按钮 */}
          {selectedShots.size > 0 && !hasSelectedShotsAnalyzing && (
            <button
              onClick={() => handleAnalyzeSelected(Array.from(selectedShots))}
              disabled={isAnalysisBusy}
              className="text-xs px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {isAnalyzingSelected && (
                <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              )}
              {isAnalyzingSelected ? '启动中...' : `分析选中的 ${selectedShots.size} 个镜头`}
            </button>
          )}
          {isTaskRunning && taskId && (
            <button
              onClick={handleCancelAnalysis}
              disabled={cancellingAnalysis}
              className="text-xs px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {cancellingAnalysis ? '中断中...' : '中断分析'}
            </button>
          )}
          {video?.status === 'completed' && (
            <>
              <button
                onClick={() => handleExport('excel')}
                disabled={isExporting}
                className="text-xs px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isExporting && (
                  <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                )}
                导出 Excel
              </button>
              <button
                onClick={() => handleExport('pdf')}
                disabled={isExporting}
                className="text-xs px-3 py-1.5 bg-rose-700 hover:bg-rose-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isExporting && (
                  <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                )}
                导出 PDF
              </button>
            </>
          )}
        </div>
      </div>

      {/* 进度条 */}
      {shouldShowProgress && <ProgressBar progress={progress} />}

      {/* 主体：三栏 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左栏：镜头列表 */}
        <div className="flex-shrink-0 border-r border-gray-800 overflow-hidden" style={{ width: `${leftWidth}px` }}>
          <ShotList
            shots={shots}
            selectedIndex={selectedIndex}
            onSelect={handleShotSelect}
            currentTime={currentTime}
            videoId={videoId}
            selectedShots={selectedShots}
            onToggleShot={(index) => {
              const newSet = new Set(selectedShots)
              if (newSet.has(index)) newSet.delete(index)
              else newSet.add(index)
              setSelectedShots(newSet)
            }}
            onBatchToggle={(indices, selected) => {
              const newSet = new Set(selectedShots)
              indices.forEach(idx => {
                if (selected) {
                  newSet.add(idx)
                } else {
                  newSet.delete(idx)
                }
              })
              setSelectedShots(newSet)
            }}
            analyzingShots={analyzingShots}
          />
        </div>
        {/* 左侧拖拽手柄 */}
        <div
          onMouseDown={() => setIsResizingLeft(true)}
          className="w-1 flex-shrink-0 bg-gray-800 hover:bg-indigo-500 cursor-col-resize transition-colors"
        />

        {/* 中栏：播放器 + 时间轴 */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 bg-black flex items-center justify-center overflow-hidden">
            {video ? (
              <video
                ref={videoRef}
                src={`${API_BASE_URL}/api/video-file/${videoId}`}
                controls
                className="max-h-full max-w-full"
                onTimeUpdate={handleTimeUpdate}
              />
            ) : (
              <div className="text-gray-600">加载中…</div>
            )}
          </div>

          {/* 自定义时间轴 */}
          {shots.length > 0 && (
            <ShotTimeline
              shots={shots}
              duration={video?.duration ?? 0}
              currentTime={currentTime}
              selectedIndex={selectedIndex}
              onSeek={handleSeek}
              onSelect={handleShotSelect}
            />
          )}
        </div>

        {/* 右侧拖拽手柄 */}
        <div
          onMouseDown={() => setIsResizingRight(true)}
          className="w-1 flex-shrink-0 bg-gray-800 hover:bg-indigo-500 cursor-col-resize transition-colors"
        />
        {/* 右栏：详情 / 整体分析 */}
        <div className="flex-shrink-0 border-l border-gray-800 flex flex-col overflow-hidden" style={{ width: `${rightWidth}px` }}>
          <div className="flex border-b border-gray-800 flex-shrink-0">
            {(['detail', 'segments', 'continuity'] as RightTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${
                  rightTab === tab ? 'text-indigo-300 border-b-2 border-indigo-500 bg-indigo-950/20' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {tab === 'detail' ? '镜头详情' : tab === 'segments' ? '段落分析' : '整体分析'}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-hidden flex flex-col">
            {rightTab === 'detail' ? (
              <ShotDetailPanel shot={selectedShot} videoId={videoId} />
            ) : rightTab === 'segments' ? (
              <SegmentReport report={data?.segments} />
            ) : (
              <>
                <div className="flex-shrink-0 px-4 py-2 border-b border-gray-800">
                  {selectedShots.size > 0 || continuityLoading ? (
                    <button
                      onClick={() => handleAnalyzeContinuity(Array.from(selectedShots))}
                      disabled={isReanalyzingContinuity || selectedShots.size === 0}
                      className="text-xs px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {isReanalyzingContinuity && (
                        <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                      )}
                      {isReanalyzingContinuity ? '分析中...' : `整体分析选中的 ${selectedShots.size} 个镜头`}
                    </button>
                  ) : (
                    <div className="text-xs text-gray-500">
                      请在左侧选择镜头后进行整体分析
                    </div>
                  )}
                </div>
                <div className="flex-1 overflow-hidden">
                  <ContinuityReport report={data?.overall_analysis} loading={continuityLoading} />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
