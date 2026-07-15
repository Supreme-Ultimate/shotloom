import { AnalysisSchema, VideoSegmentReport } from '../types/analysis'
import SchemaRenderer from './SchemaRenderer'

interface Props { report?: VideoSegmentReport | null; schema?: AnalysisSchema }

export default function SegmentReport({ report, schema }: Props) {
  const segments = report?.segments ?? []
  if (!segments.length) return <div className="h-full px-4 py-8 text-center text-sm text-gray-500">暂无段落分析</div>
  return (
    <div className="h-full space-y-4 overflow-y-auto px-4 py-3">
      {segments.map((segment, index) => (
        <article key={`${segment.segment_index ?? index}-${segment.shot_indices?.join('-')}`}>
          <div className="mb-2 text-sm font-semibold text-white">段落 #{index + 1}</div>
          <div className="mb-2 text-xs text-sky-300">镜头 {(segment.shot_indices ?? []).map(i => `#${i + 1}`).join('、')}</div>
          {schema?.version === 2
            ? <SchemaRenderer data={segment as unknown as Record<string, unknown>} fields={schema.scopes.segment} />
            : <pre className="whitespace-pre-wrap break-words text-xs text-gray-300">{JSON.stringify(segment, null, 2)}</pre>}
        </article>
      ))}
    </div>
  )
}
