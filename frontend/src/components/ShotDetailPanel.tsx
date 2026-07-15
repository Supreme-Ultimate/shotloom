import { AnalysisSchema, Shot } from '../types/analysis'
import { API_BASE_URL } from '../config'
import { getUserFacingErrorMessage } from '../utils/error'
import SchemaRenderer from './SchemaRenderer'

interface Props { shot: Shot | null; videoId: number; schema?: AnalysisSchema }

export default function ShotDetailPanel({ shot, videoId, schema }: Props) {
  if (!shot) return <div className="flex h-full items-center justify-center text-sm text-gray-600">选择一个镜头查看详情</div>
  const analysis = shot.analysis
  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      <div className="mb-4">
        <h3 className="text-base font-bold text-white">镜头 #{shot.index + 1}</h3>
        <p className="text-xs text-gray-500">{shot.start_time.toFixed(3)}s → {shot.end_time.toFixed(3)}s · {shot.duration.toFixed(3)}s</p>
      </div>
      {shot.thumbnail_path && <img src={`${API_BASE_URL}/api/thumbnail/${videoId}/${shot.index}`} className="mb-4 max-h-40 w-full rounded-lg object-cover" />}
      {!analysis && <div className="py-8 text-center text-sm text-gray-500">请选中镜头进行 AI 分析</div>}
      {analysis?.error && <div className="rounded-lg border border-red-700 bg-red-900/30 p-3 text-sm text-red-300">分析出错：{getUserFacingErrorMessage(analysis.error, '分析失败')}</div>}
      {analysis && !analysis.error && schema?.version === 2 && <SchemaRenderer data={analysis as Record<string, unknown>} fields={schema.scopes.shot} />}
      {analysis && !analysis.error && schema?.version !== 2 && (
        <pre className="whitespace-pre-wrap break-words rounded-lg bg-gray-900 p-3 text-xs text-gray-300">{JSON.stringify(analysis, null, 2)}</pre>
      )}
    </div>
  )
}
