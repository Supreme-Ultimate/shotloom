import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ProTable } from '@ant-design/pro-components'
import type { ProColumns } from '@ant-design/pro-components'
import { Button, Descriptions, Tag, Spin } from 'antd'
import api from '../../utils/api'

interface UserInfo {
  id: number
  email: string
  display_name: string | null
  is_superuser: boolean
  is_active: boolean
  credits: number
  created_at: string
  wechat_linked: boolean
}

interface VideoRow {
  id: number
  filename: string
  duration: number
  status: string
  created_at: string
  shot_count: number
}

interface TxRow {
  id: number
  delta: number
  reason: string
  video_id: number | null
  shot_count: number | null
  created_at: string
}

const STATUS_COLOR: Record<string, string> = {
  uploaded: 'default',
  detecting: 'processing',
  detected: 'blue',
  analyzing: 'processing',
  completed: 'success',
  error: 'error',
}

const REASON_LABEL: Record<string, string> = {
  initial_grant: '初始赠送',
  analysis: '视频分析',
  admin_reset: '管理员设置',
  refund: '退款',
}

export default function AdminUserDetail() {
  const { userId } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!userId) return
    api.get(`/api/admin/users/${userId}`)
      .then(res => setUserInfo(res.data))
      .finally(() => setLoading(false))
  }, [userId])

  const videoColumns: ProColumns<VideoRow>[] = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    {
      title: '时长',
      dataIndex: 'duration',
      width: 80,
      render: (v) => `${Math.round(v as number)}s`,
    },
    {
      title: '镜头数',
      dataIndex: 'shot_count',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v) => <Tag color={STATUS_COLOR[v as string] || 'default'}>{v as string}</Tag>,
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v) => new Date(v as string).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 80,
      render: (_, record) => (
        <a onClick={() => navigate(`/analysis/${record.id}`)} className="text-indigo-400 hover:text-indigo-300 cursor-pointer">
          查看
        </a>
      ),
    },
  ]

  const txColumns: ProColumns<TxRow>[] = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '变动',
      dataIndex: 'delta',
      width: 80,
      render: (v) => (
        <span className={(v as number) > 0 ? 'text-green-400' : 'text-red-400'}>
          {(v as number) > 0 ? '+' : ''}{v as number}
        </span>
      ),
    },
    {
      title: '原因',
      dataIndex: 'reason',
      width: 110,
      render: (v) => REASON_LABEL[v as string] || v as string,
    },
    { title: '关联视频', dataIndex: 'video_id', width: 80, render: (v) => v || '—' },
    { title: '镜头数', dataIndex: 'shot_count', width: 80, render: (v) => v || '—' },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v) => new Date(v as string).toLocaleString('zh-CN'),
    },
  ]

  if (loading) return <div className="flex items-center justify-center h-64"><Spin /></div>
  if (!userInfo) return <div className="text-gray-400">用户不存在</div>

  return (
    <div className="space-y-6">
      <Button onClick={() => navigate('/admin/users')}>← 返回用户列表</Button>

      {/* 基本信息 */}
      <Descriptions
        title="用户信息"
        bordered
        size="small"
        style={{ background: '#12121f' }}
        items={[
          { label: '用户ID', children: userInfo.id },
          { label: '昵称', children: userInfo.display_name || '—' },
          { label: '邮箱', children: userInfo.email },
          { label: '积分余额', children: <span className="text-yellow-400 font-medium">{userInfo.credits}</span> },
          { label: '管理员', children: userInfo.is_superuser ? '是' : '否' },
          { label: '状态', children: userInfo.is_active ? <Tag color="success">正常</Tag> : <Tag color="error">禁用</Tag> },
          { label: '微信绑定', children: userInfo.wechat_linked ? '已绑定' : '未绑定' },
          { label: '注册时间', children: new Date(userInfo.created_at).toLocaleString('zh-CN') },
        ]}
      />

      {/* 视频列表 */}
      <ProTable<VideoRow>
        headerTitle="上传视频记录"
        rowKey="id"
        columns={videoColumns}
        request={async (params) => {
          const res = await api.get(`/api/admin/users/${userId}/videos`, {
            params: { page: params.current, page_size: params.pageSize },
          })
          return { data: res.data.data, total: res.data.total, success: true }
        }}
        search={false}
        pagination={{ pageSize: 10 }}
        scroll={{ x: 700 }}
      />

      {/* 积分流水 */}
      <ProTable<TxRow>
        headerTitle="积分流水"
        rowKey="id"
        columns={txColumns}
        request={async (params) => {
          const res = await api.get(`/api/admin/users/${userId}/transactions`, {
            params: { page: params.current, page_size: params.pageSize },
          })
          return { data: res.data.data, total: res.data.total, success: true }
        }}
        search={false}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 600 }}
      />
    </div>
  )
}
