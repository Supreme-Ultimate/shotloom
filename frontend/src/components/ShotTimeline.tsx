import { Shot } from '../types/analysis'

interface Props {
  shots: Shot[]
  duration: number
  currentTime: number
  selectedIndex: number
  onSeek: (time: number) => void
  onSelect: (index: number) => void
}

export default function ShotTimeline({ shots, duration, currentTime, selectedIndex, onSeek, onSelect }: Props) {
  const pct = (t: number) => duration > 0 ? `${(t / duration) * 100}%` : '0%'

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    onSeek(ratio * duration)
  }

  return (
    <div className="px-3 py-2 bg-[#12121f] border-t border-gray-800">
      {/* 进度轨道 */}
      <div
        className="relative h-10 bg-gray-800 rounded-lg overflow-hidden cursor-pointer select-none"
        onClick={handleClick}
      >
        {shots.map((shot) => {
          const isSelected = shot.index === selectedIndex
          const hasAnalysis = !!shot.analysis && !shot.analysis.error
          return (
            <div
              key={shot.index}
              title={`镜头#${shot.index + 1} ${shot.duration.toFixed(1)}s`}
              onClick={(e) => { e.stopPropagation(); onSelect(shot.index); onSeek(shot.start_time) }}
              style={{ left: pct(shot.start_time), width: pct(shot.duration) }}
              className={`absolute top-0 h-full border-r border-[#0f0f14] transition-colors cursor-pointer
                ${isSelected ? 'bg-indigo-600/80 ring-1 ring-indigo-400' : hasAnalysis ? 'bg-indigo-900/60 hover:bg-indigo-800/60' : 'bg-gray-700/60 hover:bg-gray-600/60'}`}
            >
              <span className="absolute bottom-0.5 left-0.5 text-[9px] text-gray-400 leading-none pointer-events-none">
                {shot.index + 1}
              </span>
            </div>
          )
        })}

        {/* 播放头 */}
        <div
          className="absolute top-0 h-full w-0.5 bg-white/80 pointer-events-none z-10"
          style={{ left: pct(currentTime) }}
        />
      </div>

      {/* 时间标尺 */}
      <div className="flex justify-between text-[10px] text-gray-600 mt-1 px-1">
        <span>0:00</span>
        <span>{Math.floor(duration / 60)}:{String(Math.floor(duration % 60)).padStart(2, '0')}</span>
      </div>
    </div>
  )
}
