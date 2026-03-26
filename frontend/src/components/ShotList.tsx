import { Shot } from '../types/analysis'

interface Props {
  shots: Shot[]
  selectedIndex: number
  onSelect: (index: number) => void
  currentTime?: number
  videoId: number
  selectedShots?: Set<number>
  onToggleShot?: (index: number) => void
  onBatchToggle?: (indices: number[], selected: boolean) => void
  analyzingShots?: Set<number>
}

function formatTime(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function ShotList({ shots, selectedIndex, onSelect, currentTime = 0, videoId, selectedShots, onToggleShot, onBatchToggle, analyzingShots }: Props) {
  const showCheckbox = !!selectedShots && !!onToggleShot

  // 批量选择功能
  const handleSelectAll = () => {
    if (!onBatchToggle || !selectedShots) return
    const allIndices = shots.map(s => s.index)
    const allSelected = allIndices.every(idx => selectedShots.has(idx))

    onBatchToggle(allIndices, !allSelected)
  }

  const handleSelectErrors = () => {
    if (!onBatchToggle || !selectedShots) return
    const errorIndices = shots.filter(s => s.analysis?.error).map(s => s.index)
    if (errorIndices.length === 0) return

    const allErrorsSelected = errorIndices.every(idx => selectedShots.has(idx))
    onBatchToggle(errorIndices, !allErrorsSelected)
  }

  const handleSelectUnanalyzed = () => {
    if (!onBatchToggle || !selectedShots) return
    const unanalyzedIndices = shots.filter(s => !s.analysis).map(s => s.index)
    if (unanalyzedIndices.length === 0) return

    const allUnanalyzedSelected = unanalyzedIndices.every(idx => selectedShots.has(idx))
    onBatchToggle(unanalyzedIndices, !allUnanalyzedSelected)
  }

  const errorCount = shots.filter(s => s.analysis?.error).length
  const unanalyzedCount = shots.filter(s => !s.analysis).length

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs text-gray-400 border-b border-gray-700">
        <div className="flex justify-between mb-2">
          <span>镜头列表</span>
          <span>{shots.length} 个镜头</span>
        </div>
        {showCheckbox && (
          <div className="flex gap-1 flex-wrap">
            <button
              onClick={handleSelectAll}
              className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition-colors"
            >
              全选
            </button>
            {unanalyzedCount > 0 && (
              <button
                onClick={handleSelectUnanalyzed}
                className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs transition-colors"
              >
                未分析 ({unanalyzedCount})
              </button>
            )}
            {errorCount > 0 && (
              <button
                onClick={handleSelectErrors}
                className="px-2 py-1 bg-red-900/50 hover:bg-red-800/50 rounded text-xs transition-colors"
              >
                错误 ({errorCount})
              </button>
            )}
          </div>
        )}
      </div>
      <div className="overflow-y-auto flex-1">
        {shots.map((shot) => {
          const isActive = currentTime >= shot.start_time && currentTime < shot.end_time
          const isSelected = shot.index === selectedIndex
          const hasAnalysis = !!shot.analysis && !shot.analysis.error
          const hasError = shot.analysis?.error
          const isAnalyzing = analyzingShots?.has(shot.index) ?? false
          const isChecked = selectedShots?.has(shot.index) ?? false

          // 状态指示器
          let statusIcon = null
          if (isAnalyzing) {
            statusIcon = (
              <svg className="animate-spin h-3 w-3 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            )
          } else if (hasError) {
            statusIcon = <span className="text-red-400 text-sm">✕</span>
          } else if (hasAnalysis) {
            statusIcon = <span className="text-green-400 text-sm">✓</span>
          } else {
            statusIcon = <span className="text-gray-600 text-sm">○</span>
          }

          return (
            <div
              key={shot.index}
              className={`flex items-center gap-2 px-3 py-2 border-b border-gray-800 transition-colors
                ${isSelected ? 'bg-indigo-900/60 border-l-2 border-l-indigo-400' : 'hover:bg-gray-800/50'}
                ${isActive ? 'ring-1 ring-inset ring-indigo-500/50' : ''}`}
            >
              {/* 状态指示器 */}
              <div className="flex-shrink-0 w-3 flex items-center justify-center">
                {statusIcon}
              </div>

              {/* Checkbox */}
              {showCheckbox && (
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={(e) => {
                    e.stopPropagation()
                    onToggleShot(shot.index)
                  }}
                  className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
                />
              )}

              {/* 缩略图 */}
              <div
                onClick={() => onSelect(shot.index)}
                className="w-14 h-8 flex-shrink-0 rounded overflow-hidden bg-gray-800 cursor-pointer"
              >
                {shot.thumbnail_path ? (
                  <img
                    src={`/api/thumbnail/${videoId}/${shot.index}`}
                    alt={`Shot ${shot.index + 1}`}
                    onError={(e) => {
                      const img = e.target as HTMLImageElement
                      img.style.display = 'none'
                      const placeholder = img.nextElementSibling as HTMLElement
                      if (placeholder) placeholder.style.display = 'flex'
                    }}
                    className="w-full h-full object-cover"
                  />
                ) : null}
                <div className="hidden w-full h-full bg-gray-700 items-center justify-center text-xs text-gray-500">
                  📹
                </div>
              </div>

              <div
                onClick={() => onSelect(shot.index)}
                className="flex-1 min-w-0 cursor-pointer"
              >
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">#{shot.index + 1}</span>
                  {isActive && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />}
                </div>
                <div className="text-xs text-gray-500">
                  {formatTime(shot.start_time)} · {shot.duration.toFixed(1)}s
                </div>
                {hasAnalysis && (
                  <div className="text-xs text-indigo-300 truncate">
                    {shot.analysis!.shot_scale} · {shot.analysis!.camera_movement}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
