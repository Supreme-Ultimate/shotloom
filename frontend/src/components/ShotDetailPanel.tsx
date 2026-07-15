import { Shot } from '../types/analysis'
import { API_BASE_URL } from '../config'
import { getUserFacingErrorMessage } from '../utils/error'

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



function sourceLabel(source?: string, mode?: string) {
  const key = source || mode
  if (key === 'whole_video' || mode === 'whole_video_context') return '整片上下文'
  if (key === 'chunk_segment' || mode === 'chunk_segment_context') return '分块上下文'
  if (key === 'merged_context' || mode === 'merged_context') return '合并上下文'
  if (key === 'shot_clip' || mode === 'shot_clip') return '单镜头回退'
  return key || ''
}

function formatShotRange(indices?: number[]) {
  if (!indices?.length) return ''
  return indices.map(i => `#${i + 1}`).join('、')
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
          src={`${API_BASE_URL}/api/thumbnail/${videoId}/${shot.index}`}
          className="w-full rounded-lg mb-4 object-cover max-h-40"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      )}

      {!a && (
        <div className="text-gray-500 text-sm py-8 text-center">
          <div className="text-2xl mb-2">⌁</div>
          <p>请选中镜头进行 AI 分析</p>
        </div>
      )}

      {hasError && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-300">
          分析出错：{getUserFacingErrorMessage(a?.error, '分析失败')}
        </div>
      )}

      {a && !hasError && (
        <>
          {(a.analysis_source || a.analysis_mode) && (
            <div className="mb-3 inline-flex rounded-full border border-sky-700/60 bg-sky-950/30 px-2 py-1 text-[11px] text-sky-200">
              分析来源：{sourceLabel(a.analysis_source, a.analysis_mode)}
            </div>
          )}

          {a.analysis_mode === 'merged_context' && (
            <div className="mb-4 rounded-lg border border-amber-700/60 bg-amber-950/20 p-3 text-xs text-amber-100">
              <div className="mb-1 font-semibold text-amber-300">合并上下文分析</div>
              <div>分析范围：{formatShotRange(a.analysis_shot_indices)}</div>
              {typeof a.merged_start_time === 'number' && typeof a.merged_end_time === 'number' && (
                <div>{a.merged_start_time.toFixed(1)}s → {a.merged_end_time.toFixed(1)}s</div>
              )}
              {typeof a.target_offset_start === 'number' && typeof a.target_offset_end === 'number' && (
                <div>本镜头位于输入片段 {a.target_offset_start.toFixed(1)}s → {a.target_offset_end.toFixed(1)}s</div>
              )}
            </div>
          )}

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

          {a.audio && (
            <Section title="声音分析">
              <Row label="音轨台词" value={a.audio.dialogue} />
              <Row label="声音类型" value={a.audio.sound_type} />
              <Row label="音乐" value={a.audio.music} />
              <Row label="环境声" value={a.audio.ambient_sound} />
              <Row label="人声情绪" value={a.audio.speaker_emotion} />
              <Row label="声画关系" value={a.audiovisual_sync} />
              <Row label="声音叙事" value={a.audio_narrative_role} />
            </Section>
          )}

          {(a.audio_continuity || a.action_continuity) && (
            <Section title="跨镜头连续性">
              <Row label="声音承前" value={a.audio_continuity?.continues_from_previous} />
              <Row label="声音启后" value={a.audio_continuity?.continues_to_next} />
              <Row label="台词未完" value={a.audio_continuity?.unfinished_dialogue} />
              <Row label="声音说明" value={a.audio_continuity?.notes} />
              <Row label="动作承前" value={a.action_continuity?.continues_from_previous} />
              <Row label="动作启后" value={a.action_continuity?.continues_to_next} />
              <Row label="动作说明" value={a.action_continuity?.notes} />
            </Section>
          )}

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

          {a.context_shot_summaries?.length ? (
            <Section title="上下文镜头">
              <div className="space-y-2">
                {a.context_shot_summaries.map((item, idx) => (
                  <div key={idx} className="rounded border border-gray-800 bg-gray-900/40 p-2 text-xs text-gray-300">
                    <div className="mb-1 text-amber-300">
                      {typeof item.shot_index === 'number' ? `镜头 #${item.shot_index + 1}` : `上下文 ${idx + 1}`}
                      {item.shot_scale ? ` · ${item.shot_scale}` : ''}
                    </div>
                    <div>{item.summary || item.action || item.role}</div>
                  </div>
                ))}
              </div>
            </Section>
          ) : null}

          {a.merged_segment_analysis && (
            <Section title="合并段落分析">
              <p className="text-sm leading-relaxed text-gray-200">{a.merged_segment_analysis}</p>
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
