import { Shot } from '../types/analysis'

interface Props {
  shot: Shot | null
  videoId: number
}

function Row({ label, value }: { label: string; value?: string | string[] | boolean | null }) {
  if (!value && value !== false) return null
  const display = Array.isArray(value) ? value.join('；') : String(value)
  if (!display || display === '—') return null
  return (
    <div className="flex gap-2 text-sm py-1 border-b border-gray-800/50">
      <span className="text-gray-500 flex-shrink-0 w-20 text-xs pt-0.5">{label}</span>
      <span className="text-gray-200 flex-1 leading-relaxed">{display}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-xs font-bold text-indigo-400 uppercase tracking-wider mb-2 pb-1 border-b border-indigo-900">
        {title}
      </div>
      {children}
    </div>
  )
}

function WhyBlock({ label, value, color = 'text-gray-200' }: { label: string; value?: string; color?: string }) {
  if (!value) return null
  return (
    <div className="mb-3">
      <div className="text-xs font-bold text-indigo-500 uppercase mb-1">{label}</div>
      <p className={`text-sm leading-relaxed ${color}`}>{value}</p>
    </div>
  )
}

export default function ShotDetailPanel({ shot, videoId }: Props) {
  if (!shot) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        选择一个镜头查看详情
      </div>
    )
  }

  const a = shot.analysis
  const hasError = a?.error

  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      {/* 标题 */}
      <div className="mb-4">
        <h3 className="text-white font-bold text-base">镜头 #{shot.index + 1}</h3>
        <p className="text-gray-500 text-xs">
          {shot.start_time.toFixed(1)}s → {shot.end_time.toFixed(1)}s &nbsp;·&nbsp; {shot.duration.toFixed(1)}s
        </p>
      </div>

      {/* 缩略图 */}
      {shot.thumbnail_path && (
        <img
          src={`/api/thumbnail/${videoId}/${shot.index}`}
          className="w-full rounded-lg mb-4 object-cover max-h-40"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      )}

      {!a && (
        <div className="text-gray-600 text-sm py-8 text-center">
          <div className="text-2xl mb-2 animate-spin inline-block">⟳</div>
          <p>等待 AI 分析中…</p>
        </div>
      )}

      {hasError && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-300">
          分析出错：{a?.error}
        </div>
      )}

      {a && !hasError && (
        <>
          {/* 基础信息 */}
          <Section title="镜头参数">
            <Row label="景别" value={a.shot_scale} />
            <Row label="运镜" value={a.camera_movement} />
            <Row label="构图" value={a.composition} />
            <Row label="光影" value={a.lighting} />
            <Row label="色调" value={a.color_tone} />
            <Row label="内容" value={a.content_description} />
          </Section>

          {/* 字幕/对话 */}
          {(a.on_screen_text && a.on_screen_text !== '无') || (a.dialogue && a.dialogue !== '无') ? (
            <Section title="字幕与对话">
              {a.on_screen_text && a.on_screen_text !== '无' && (
                <Row label="画面文字" value={a.on_screen_text} />
              )}
              {a.dialogue && a.dialogue !== '无' && (
                <Row label="对话/旁白" value={a.dialogue} />
              )}
            </Section>
          ) : null}

          {/* WHW 分析 */}
          <Section title="创作者视角">
            <div className="bg-indigo-950/40 rounded-lg p-3 border border-indigo-900/50">
              <WhyBlock label="WHAT" value={a.what} />
              <WhyBlock label="HOW" value={a.how} />
              <WhyBlock label="WHY" value={a.why} color="text-indigo-200" />
            </div>
          </Section>

          {/* 叙事层级 */}
          {a.narrative_level && (
            <Section title="叙事层级">
              <div className="bg-emerald-950/30 rounded-lg p-3 border border-emerald-900/40 space-y-2">
                <div>
                  <span className="text-xs text-emerald-500 font-bold">场景</span>
                  <p className="text-sm text-gray-300 mt-0.5">{a.narrative_level.scene}</p>
                </div>
                <div>
                  <span className="text-xs text-emerald-500 font-bold">事件</span>
                  <p className="text-sm text-gray-300 mt-0.5">{a.narrative_level.event}</p>
                </div>
                <div>
                  <span className="text-xs text-emerald-500 font-bold">信息</span>
                  <p className="text-sm text-gray-300 mt-0.5">{a.narrative_level.information}</p>
                </div>
              </div>
            </Section>
          )}

          {/* 叙事决策 */}
          <Section title="叙事与节奏">
            <Row label="情绪功能" value={a.emotional_function} />
            <Row label="叙事决策" value={a.narrative_decision} />
            <Row label="节奏贡献" value={a.rhythm_contribution} />
          </Section>

        </>
      )}
    </div>
  )
}
