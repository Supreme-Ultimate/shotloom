import { useCallback, useEffect, useState } from 'react'
import { Button, Drawer, Input, Select, Tabs, message } from 'antd'
import api from '../utils/api'
import { AnalysisField, AnalysisFieldSource, AnalysisFieldType, AnalysisSchema } from '../types/analysis'
import { getApiErrorMessage } from '../utils/error'

interface Props { videoId: number; open: boolean; onClose: () => void; onSaved: () => void }
interface Preset { id: number; name: string; is_system: boolean; config: AnalysisSchema }

const types: AnalysisFieldType[] = ['string', 'number', 'boolean', 'string_array', 'object', 'object_array']
function FieldEditor({ field, onChange, onDelete }: { field: AnalysisField; onChange: (field: AnalysisField) => void; onDelete: () => void }) {
  const update = (patch: Partial<AnalysisField>) => onChange({ ...field, ...patch })
  const children = field.fields ?? []
  return (
    <div className="mb-2 rounded-lg border border-gray-700 bg-gray-900/50 p-3">
      <div className="grid grid-cols-2 gap-2">
        <Input value={field.label} placeholder="显示名称" onChange={event => update({ label: event.target.value })} />
        <Input value={field.key} placeholder="field_key" onChange={event => update({ key: event.target.value })} />
      </div>
      {!field.fields && <div className="mt-2 grid grid-cols-2 gap-2">
        <Select value={field.type ?? 'string'} options={types.map(value => ({ value, label: value }))} onChange={value => update({ type: value })} />
        <Select disabled value={field.source ?? 'vision'} options={([field.source ?? 'vision'] as AnalysisFieldSource[]).map(value => ({ value, label: `数据来源·${value}` }))} />
      </div>}
      <Input.TextArea className="mt-2" value={field.description} placeholder="字段说明 / 提示词" autoSize={{ minRows: 1, maxRows: 4 }} onChange={event => update({ description: event.target.value })} />
      {field.fields && <div className="mt-3 border-l border-indigo-800 pl-3">
        {children.map((child, index) => <FieldEditor key={`${child.key}-${index}`} field={child} onChange={next => update({ fields: children.map((item, i) => i === index ? next : item) })} onDelete={() => update({ fields: children.filter((_, i) => i !== index) })} />)}
        <Button size="small" onClick={() => update({ fields: [...children, { key: `field_${children.length + 1}`, label: '新字段', type: 'string', source: 'vision', description: '' }] })}>+ 添加字段</Button>
      </div>}
      <Button danger type="text" size="small" onClick={onDelete}>删除</Button>
    </div>
  )
}

export default function AnalysisConfigDrawer({ videoId, open, onClose, onSaved }: Props) {
  const [config, setConfig] = useState<AnalysisSchema | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [revision, setRevision] = useState(1)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [jsonMode, setJsonMode] = useState(false)
  const [jsonText, setJsonText] = useState('')

  const load = useCallback(async () => {
    const [configRes, presetsRes] = await Promise.all([api.get(`/api/videos/${videoId}/analysis-config`), api.get('/api/analysis-presets')])
    setConfig(configRes.data.draft_config)
    setRevision(configRes.data.draft_revision)
    setDirty(configRes.data.dirty)
    setPresets(presetsRes.data)
    setJsonText(JSON.stringify(configRes.data.draft_config, null, 2))
  }, [videoId])
  useEffect(() => { if (open) load().catch(error => message.error(getApiErrorMessage(error, '加载配置失败'))) }, [open, load])

  const save = async () => {
    if (!config) return
    setSaving(true)
    try {
      const next = jsonMode ? JSON.parse(jsonText) : config
      const response = await api.put(`/api/videos/${videoId}/analysis-config`, { config: next, revision })
      setConfig(next)
      setRevision(response.data.draft_revision)
      setDirty(response.data.dirty)
      message.success('分析配置已保存')
      onSaved()
    } catch (error) { message.error(getApiErrorMessage(error, '保存配置失败')) } finally { setSaving(false) }
  }
  const applyPreset = async (presetId: number) => {
    try {
      const response = await api.post(`/api/videos/${videoId}/analysis-config/apply-preset/${presetId}?expected_revision=${revision}`)
      setConfig(response.data.draft_config)
      setJsonText(JSON.stringify(response.data.draft_config, null, 2))
      setRevision(response.data.draft_revision)
      setDirty(response.data.dirty)
      message.success('模板已复制到当前视频')
    } catch (error) { message.error(getApiErrorMessage(error, '应用模板失败')) }
  }
  const savePreset = async () => {
    if (!config) return
    const name = window.prompt('请输入模板名称', config.name || '我的分析模板')?.trim()
    if (!name) return
    try {
      await api.post('/api/analysis-presets', { name, description: config.description ?? '', config })
      message.success('已保存为私有模板')
      await load()
    } catch (error) { message.error(getApiErrorMessage(error, '保存模板失败')) }
  }
  const scopeTab = (scope: 'shot' | 'segment' | 'overall') => {
    if (!config) return null
    const fields = config.scopes[scope]
    return <div>{fields.map((field, index) => <FieldEditor key={`${field.key}-${index}`} field={field} onChange={next => setConfig({ ...config, scopes: { ...config.scopes, [scope]: fields.map((item, i) => i === index ? next : item) } })} onDelete={() => setConfig({ ...config, scopes: { ...config.scopes, [scope]: fields.filter((_, i) => i !== index) } })} />)}<Button onClick={() => setConfig({ ...config, scopes: { ...config.scopes, [scope]: [...fields, { key: `group_${fields.length + 1}`, label: '新分组', fields: [] }] } })}>+ 添加分组</Button></div>
  }
  return (
    <Drawer title="分析配置" width={720} open={open} onClose={onClose} styles={{ body: { background: '#0f0f14', color: '#fff' } }} extra={<span className="text-xs text-gray-500">revision {revision}{dirty ? ' · 需要完整重分析' : ''}</span>}>
      {!config ? <div className="text-gray-500">加载中…</div> : <>
        <div className="mb-4 flex flex-wrap gap-2">
          <Select className="min-w-52" placeholder="应用 preset" options={presets.map(item => ({ value: item.id, label: `${item.is_system ? '系统 · ' : ''}${item.name}` }))} onChange={applyPreset} />
          <Button onClick={savePreset}>保存为 preset</Button>
          <Button onClick={() => { setJsonMode(!jsonMode); setJsonText(JSON.stringify(config, null, 2)) }}>{jsonMode ? '返回可视化编辑' : '高级 JSON'}</Button>
          <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
        </div>
        {dirty && <div className="mb-4 rounded border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-200">当前结果仍使用旧配置。新配置将在完整重新分析后生效。</div>}
        {jsonMode ? <Input.TextArea value={jsonText} onChange={event => setJsonText(event.target.value)} autoSize={{ minRows: 24 }} className="font-mono" /> : <>
          <div className="mb-4 grid gap-2"><Input value={config.name} placeholder="配置名称" onChange={event => setConfig({ ...config, name: event.target.value })} /><Input value={config.description} placeholder="配置说明" onChange={event => setConfig({ ...config, description: event.target.value })} /></div>
          <Tabs items={[{ key: 'shot', label: '镜头字段', children: scopeTab('shot') }, { key: 'segment', label: '段落字段', children: scopeTab('segment') }, { key: 'overall', label: '整体字段', children: scopeTab('overall') }, { key: 'prompts', label: '提示词', children: <div className="space-y-3">{Object.entries(config.prompts ?? {}).map(([key, value]) => <div key={key}><div className="mb-1 text-xs text-gray-500">{key}</div><Input.TextArea value={value} autoSize={{ minRows: 2, maxRows: 6 }} onChange={event => setConfig({ ...config, prompts: { ...config.prompts, [key]: event.target.value } })} /></div>)}</div> }]} />
        </>}
      </>}
    </Drawer>
  )
}
