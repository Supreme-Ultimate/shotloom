import { AnalysisSchema, ContinuityReport as CReport } from '../types/analysis'
import { getUserFacingErrorMessage } from '../utils/error'
import SchemaRenderer from './SchemaRenderer'

interface Props { report: CReport | null | undefined; loading?: boolean; schema?: AnalysisSchema }

export default function ContinuityReport({ report, loading = false, schema }: Props) {
  if (loading) return <div className="flex h-48 items-center justify-center text-sm text-gray-400">整体分析生成中…</div>
  if (!report) return <div className="flex h-48 items-center justify-center text-sm text-gray-600">整体分析生成后显示</div>
  if (report.error) return <div className="m-4 rounded-lg border border-red-800 bg-red-900/20 p-4 text-sm text-red-300">整体分析出错：{getUserFacingErrorMessage(report.error, '整体分析失败')}</div>
  return (
    <div className="h-full overflow-y-auto p-4">
      {schema?.version === 2
        ? <SchemaRenderer data={report as Record<string, unknown>} fields={schema.scopes.overall} />
        : <pre className="whitespace-pre-wrap break-words text-xs text-gray-300">{JSON.stringify(report, null, 2)}</pre>}
    </div>
  )
}
