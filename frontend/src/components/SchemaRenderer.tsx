import { AnalysisField } from '../types/analysis'

interface Props {
  data?: Record<string, unknown> | null
  fields: AnalysisField[]
  emptyText?: string
}

function Value({ value }: { value: unknown }) {
  if (value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0)) return <span className="text-gray-600">—</span>
  if (Array.isArray(value)) {
    if (value.every(item => typeof item !== 'object')) {
      return <ul className="space-y-1">{value.map((item, index) => <li key={index} className="border-l-2 border-indigo-800 pl-2">{String(item)}</li>)}</ul>
    }
    return <pre className="whitespace-pre-wrap break-words text-xs text-gray-300">{JSON.stringify(value, null, 2)}</pre>
  }
  if (typeof value === 'object') {
    return <pre className="whitespace-pre-wrap break-words text-xs text-gray-300">{JSON.stringify(value, null, 2)}</pre>
  }
  if (typeof value === 'boolean') return <>{value ? '是' : '否'}</>
  return <span className="whitespace-pre-wrap break-words">{String(value)}</span>
}

export default function SchemaRenderer({ data, fields, emptyText = '暂无分析结果' }: Props) {
  const source = data ?? {}
  if (!fields.length) return <div className="py-8 text-center text-sm text-gray-500">{emptyText}</div>
  return (
    <div className="space-y-4">
      {fields.map(field => {
        const value = source[field.key]
        if (field.fields?.length) {
          return (
            <section key={field.key} className="rounded-xl border border-gray-800 bg-[#16162a] p-4">
              <h3 className="mb-3 border-b border-indigo-900/60 pb-2 text-sm font-bold text-indigo-400">{field.label}</h3>
              <SchemaRenderer data={(value as Record<string, unknown>) ?? {}} fields={field.fields} emptyText="此分组暂无内容" />
            </section>
          )
        }
        return (
          <div key={field.key} className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 border-b border-gray-800/60 py-2 text-sm">
            <div className="text-xs text-gray-500">{field.label}</div>
            <div className="leading-relaxed text-gray-200"><Value value={value} /></div>
          </div>
        )
      })}
    </div>
  )
}
