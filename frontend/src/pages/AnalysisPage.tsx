import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { AnalysisResult, Shot, TaskProgress } from '../types/analysis'
import ShotList from '../components/ShotList'
import ShotDetailPanel from '../components/ShotDetailPanel'
import ShotTimeline from '../components/ShotTimeline'
import ContinuityReport from '../components/ContinuityReport'
import { useSSEProgress } from '../hooks/useSSEProgress'

interface Props {
  videoId: number
  onBack: () => void
}

type RightTab = 'detail' | 'continuity'

function ProgressBar({ progress }: { progress: TaskProgress }) {
  const labels: Record<string, string> = {
    starting: '初始化…',
    cutting_clips: '切割镜头片段…',
    analyzing: `AI 分析中 ${progress.done ?? 0}/${progress.total ?? 0}`,
    continuity: '生成整体分析…',
    completed: '分析完成',
    error: `错误：${progress.msg}`,
  }
  const pct = progress.total
    ? Math.round(((progress.done ?? 0) / progress.total) * 100)
    : progress.stage === 'completed' ? 100 : 0

  return (
    <div className="bg-[#1a1a2e] border-b border-gray-800 px-4 py-2 flex items-center gap-3">
      <div className="flex-1">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>{labels[progress.stage] ?? progress.stage}</span>
          <span>{pct}%</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full transition-all ${progress.stage === 'error' ? 'bg-red-500' : 'bg-indigo-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  )
}

export default function AnalysisPage({ videoId, onBack }: Props) {
  const [data, setData] = useState<AnalysisResult | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [detecting, setDetecting] = useState(false)
  const [isAnalyzingSelected, setIsAnalyzingSelected] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [isReanalyzingContinuity, setIsReanalyzingContinuity] = useState(false)
  const [rightTab, setRightTab] = useState<RightTab>('detail')
  const [selectedShots, setSelectedShots] = useState<Set<number>>(new Set())
  const [analyzingShots, setAnalyzingShots] = useState<Set<number>>(new Set())
  const [leftWidth, setLeftWidth] = useState(280)
  const [rightWidth, setRightWidth] = useState(400)
  const [isResizingLeft, setIsResizingLeft] = useState(false)
  const [isResizingRight, setIsResizingRight] = useState(false)
  const [shouldStopAtShotEnd, setShouldStopAtShotEnd] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const progress = useSSEProgress(taskId)

  // 加载视频信息
  const loadData = async () => {
    const res = await axios.get(`/api/results/${videoId}`)
    setData(res.data)
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
        const res = await axios.get(`/api/videos/${videoId}/task-status`)
        console.log('[AnalysisPage] 任务状态响应:', res.data)

        if (res.data.has_active_task && res.data.task_id) {
          console.log('[AnalysisPage] 发现活跃任务，task_id:', res.data.task_id)
          setTaskId(res.data.task_id)

          // 推断正在分析的镜头：所有未分析的镜头
          const shotsRes = await axios.get(`/api/results/${videoId}`)
          if (shotsRes.data?.shots) {
            const unanalyzedIndices = shotsRes.data.shots
              .filter((s: Shot) => !s.analysis)
              .map((s: Shot) => s.index)
            console.log('[AnalysisPage] 未分析的镜头索引:', unanalyzedIndices)
            setAnalyzingShots(new Set(unanalyzedIndices))
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

  // 检测完成或出错后清理状态
  useEffect(() => {
    if (progress?.stage === 'completed' || progress?.stage === 'error') {
      setTaskId(null)
      setSelectedShots(new Set()) // 任务完成后清空选中状态
      setAnalyzingShots(new Set()) // 清空分析中状态
      if (progress?.stage === 'completed') {
        loadData()
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
    setDetecting(true)
    try {
      await axios.post(`/api/detect/${videoId}`)
      await loadData()
    } finally {
      setDetecting(false)
    }
  }

  const handleAnalyzeSelected = async (indices: number[]) => {
    setIsAnalyzingSelected(true)
    setAnalyzingShots(new Set(indices)) // 标记正在分析的镜头
    try {
      const res = await axios.post(`/api/analyze/${videoId}`, {
        shot_indices: indices
      })
      setTaskId(res.data.task_id)
      setIsAnalyzingSelected(false) // 任务启动成功后立即恢复按钮状态
      // 不要在这里清空选中状态，等任务完成后再清空
    } catch (err: any) {
      console.error('分析失败:', err)
      setIsAnalyzingSelected(false)
      setAnalyzingShots(new Set()) // 出错时清空分析中状态
    }
  }

  const handleAnalyzeContinuity = async (shotIndices: number[]) => {
    setIsReanalyzingContinuity(true)
    try {
      await axios.post(`/api/reanalyze-continuity/${videoId}`, {
        shot_indices: shotIndices
      })
      await loadData() // 重新加载数据
    } catch (err: any) {
      console.error('整体分析失败:', err)
    } finally {
      setIsReanalyzingContinuity(false)
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

      // 自动选中当前镜头
      const active = data?.shots.find(s => t >= s.start_time && t < s.end_time)
      if (active && active.index !== selectedIndex) setSelectedIndex(active.index)
    }
  }

  const video = data?.video
  const shots = data?.shots ?? []
  const selectedShot: Shot | null = shots[selectedIndex] ?? null
  const isTaskRunning = !!(progress && progress.stage !== 'completed' && progress.stage !== 'error')
  const canDetect = video?.status === 'uploaded' && !detecting && !isTaskRunning
  const hasSelectedShotsAnalyzing = Array.from(selectedShots).some(idx => analyzingShots.has(idx))

  const handleExport = async (format: 'excel' | 'pdf') => {
    setIsExporting(true)
    try {
      window.open(`/api/export/${videoId}?format=${format}`, '_blank')
      // 给一个短暂延迟后恢复按钮状态
      setTimeout(() => setIsExporting(false), 1000)
    } catch (err: any) {
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
            <button
              onClick={handleDetect}
              disabled={detecting}
              className="text-xs px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {detecting && (
                <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              )}
              {detecting ? '检测中...' : '检测镜头'}
            </button>
          )}
          {/* 分析选中的镜头按钮 */}
          {selectedShots.size > 0 && !hasSelectedShotsAnalyzing && (
            <button
              onClick={() => handleAnalyzeSelected(Array.from(selectedShots))}
              disabled={isAnalyzingSelected}
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
      {progress && progress.stage !== 'completed' && <ProgressBar progress={progress} />}

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
                src={`/api/video-file/${videoId}`}
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
            {(['detail', 'continuity'] as RightTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setRightTab(tab)}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${
                  rightTab === tab ? 'text-indigo-300 border-b-2 border-indigo-500 bg-indigo-950/20' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {tab === 'detail' ? '镜头详情' : '整体分析'}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-hidden flex flex-col">
            {rightTab === 'detail' ? (
              <ShotDetailPanel shot={selectedShot} videoId={videoId} />
            ) : (
              <>
                <div className="flex-shrink-0 px-4 py-2 border-b border-gray-800">
                  {selectedShots.size > 0 ? (
                    <button
                      onClick={() => handleAnalyzeContinuity(Array.from(selectedShots))}
                      disabled={isReanalyzingContinuity}
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
                  <ContinuityReport report={data?.overall_analysis} />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
