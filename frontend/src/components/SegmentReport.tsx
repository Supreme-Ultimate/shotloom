import { VideoSegmentReport } from '../types/analysis'

interface Props {
  report?: VideoSegmentReport | null
}

function safe(value?: string | number | null) {
  if (value === undefined || value === null || value === '') return '—'
  return String(value)
}

function formatShots(indices?: number[]) {
  if (!indices?.length) return '—'
  return indices.map((index) => `#${index + 1}`).join('、')
}

export default function SegmentReport({ report }: Props) {
  const safeReport = report ?? undefined
  const segments = safeReport?.segments ?? []

  if (!segments.length) {
    return (
      <div className="h-full overflow-y-auto px-4 py-8 text-center text-sm text-gray-500">
        <div className="mb-2 text-2xl">⌁</div>
        <p>暂无段落分析</p>
        <p className="mt-2 text-xs leading-relaxed text-gray-600">
          使用整片/分块上下文分析后，会自动生成按对白、动作与叙事连贯性合并的二层级段落。
        </p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      <div className="mb-4 rounded-lg border border-sky-900/60 bg-sky-950/20 p-3 text-xs text-sky-100">
        <div className="font-semibold text-sky-300">二层级段落分析</div>
        <div className="mt-1 text-gray-300">来源：{safeReport?.strategy ?? 'auto'} · 覆盖 {safeReport?.shot_count ?? '—'} 个镜头</div>
        {safeReport?.reason && <div className="mt-1 text-gray-400">{safeReport?.reason}</div>}
      </div>

      <div className="space-y-3">
        {segments.map((segment, idx) => (
          <div key={`${segment.segment_index ?? idx}-${segment.shot_indices?.join('-')}`} className="rounded-xl border border-gray-800 bg-gray-900/50 p-3">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-white">{segment.title || `段落 #${idx + 1}`}</div>
                <div className="mt-1 text-[11px] text-sky-300">镜头 {formatShots(segment.shot_indices)}</div>
              </div>
              <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-200">
                {segment.segment_type ?? 'segment'}
              </span>
            </div>
            <p className="mb-2 text-sm leading-relaxed text-gray-200">{safe(segment.summary)}</p>
            <div className="space-y-1 text-xs leading-relaxed text-gray-400">
              <p><span className="text-gray-500">合并原因：</span>{safe(segment.merge_reason)}</p>
              <p><span className="text-gray-500">声音连续：</span>{safe(segment.audio_continuity)}</p>
              <p><span className="text-gray-500">动作连续：</span>{safe(segment.action_continuity)}</p>
              <p><span className="text-gray-500">剪辑逻辑：</span>{safe(segment.editing_logic)}</p>
              <p><span className="text-gray-500">情绪推进：</span>{safe(segment.emotional_arc)}</p>
              <p><span className="text-gray-500">叙事功能：</span>{safe(segment.narrative_function)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
