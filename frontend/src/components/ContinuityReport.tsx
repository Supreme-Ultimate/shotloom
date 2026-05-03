import { ContinuityReport as CReport } from '../types/analysis'

interface Props {
  report: CReport | null | undefined
  loading?: boolean
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-[#16162a] rounded-xl p-4 border border-gray-800 mb-4">
      <h3 className="text-indigo-400 font-bold text-sm mb-3 pb-2 border-b border-indigo-900/60">{title}</h3>
      {children}
    </div>
  )
}

function Item({ label, value }: { label: string; value?: string | number | string[] | null }) {
  if (!value && value !== 0) return null
  const display = Array.isArray(value) ? value : String(value)
  return (
    <div className="mb-3">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      {Array.isArray(display)
        ? <ul className="space-y-1">{display.map((v, i) => <li key={i} className="text-sm text-gray-300 pl-2 border-l-2 border-indigo-800">{v}</li>)}</ul>
        : <p className="text-sm text-gray-200 leading-relaxed">{display}</p>
      }
    </div>
  )
}

export default function ContinuityReport({ report, loading = false }: Props) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400 text-sm gap-3">
        <svg className="animate-spin h-5 w-5 text-indigo-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>整体分析生成中…</span>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
        整体分析生成后显示
      </div>
    )
  }

  if (report.error) {
    return (
      <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 text-sm text-red-300">
        整体分析出错：{report.error}
      </div>
    )
  }

  const c = report.continuity
  const r = report.rhythm
  const n = report.narrative_structure
  const g = report.genre_patterns

  return (
    <div className="p-4 overflow-y-auto h-full">
      {c && (
        <Card title="连贯性分析">
          <Item label="景别流动" value={c.shot_scale_flow} />
          <Item label="运镜衔接" value={c.movement_coherence} />
          <Item label="情绪弧线" value={c.emotional_arc} />
          <Item label="色调连续性" value={c.color_continuity} />

        </Card>
      )}

      {r && (
        <Card title="节奏分析">
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div className="bg-indigo-950/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-indigo-300">{r.avg_shot_duration?.toFixed(1)}s</div>
              <div className="text-xs text-gray-500 mt-1">平均镜头时长</div>
            </div>
            <div className="bg-indigo-950/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-indigo-300">{r.shortest_shot?.toFixed(1)}s</div>
              <div className="text-xs text-gray-500 mt-1">最短镜头</div>
            </div>
            <div className="bg-indigo-950/40 rounded-lg p-3 text-center">
              <div className="text-xl font-bold text-indigo-300">{r.longest_shot?.toFixed(1)}s</div>
              <div className="text-xs text-gray-500 mt-1">最长镜头</div>
            </div>
          </div>
          <Item label="剧情变化频率" value={r.plot_change_frequency} />
          <Item label="信息密度分布" value={r.info_density_pattern} />
          <Item label="节奏评估" value={r.pacing_assessment} />
          <Item label="张力高潮点" value={r.tension_peaks} />
        </Card>
      )}

      {n && (
        <Card title="叙事结构">
          <Item label="推测类型" value={n.detected_genre} />
          <Item label="三幕结构" value={n.three_act} />
          <Item label="关键转折点" value={n.key_turning_points} />
          <Item label="信息揭示策略" value={n.information_release_strategy} />
        </Card>
      )}

      {g && (
        <Card title="类型规律">
          <Item label="类型惯例体现" value={g.structural_notes} />
          <Item label="与惯例的偏差" value={g.deviation_notes} />
        </Card>
      )}

      {report.raw && (
        <Card title="原始输出">
          <pre className="text-xs text-gray-400 whitespace-pre-wrap">{report.raw}</pre>
        </Card>
      )}
    </div>
  )
}
