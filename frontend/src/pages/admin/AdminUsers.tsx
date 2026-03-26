import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import { Button, InputNumber, Modal, Tag, message } from 'antd'
import axios from 'axios'

interface UserRow {
  id: number
  email: string
  display_name: string | null
  is_superuser: boolean
  is_active: boolean
  credits: number
  video_count: number
  created_at: string
  wechat_linked: boolean
}

export default function AdminUsers() {
  const actionRef = useRef<ActionType>()
  const navigate = useNavigate()
  const [resetModal, setResetModal] = useState<{ open: boolean; userId: number; current: number }>({
    open: false, userId: 0, current: 0,
  })
  const [newBalance, setNewBalance] = useState<number>(0)

  const columns: ProColumns<UserRow>[] = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '用户',
      dataIndex: 'email',
      render: (_, row) => (
        <div>
          <div className="text-sm font-medium">{row.display_name || row.email}</div>
          <div className="text-xs text-gray-400">{row.email}</div>
        </div>
      ),
    },
    {
      title: '登录方式',
      width: 100,
      render: (_, row) => (
        <div className="flex flex-col gap-1">
          {row.wechat_linked && <Tag color="green" style={{ fontSize: 11 }}>微信</Tag>}
          {row.email && !row.email.includes('@wechat.placeholder') && <Tag color="blue" style={{ fontSize: 11 }}>邮箱</Tag>}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      render: (_, row) => (
        row.is_active
          ? <Tag color="success">正常</Tag>
          : <Tag color="error">已禁用</Tag>
      ),
    },
    {
      title: '积分',
      dataIndex: 'credits',
      width: 80,
      render: (val) => <span className="text-yellow-400 font-medium">{val as number}</span>,
    },
    {
      title: '视频数',
      dataIndex: 'video_count',
      width: 70,
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      width: 160,
      render: (val) => new Date(val as string).toLocaleString('zh-CN'),
    },
    {
      title: '操作',
      width: 180,
      render: (_, row) => (
        <div className="flex gap-2 flex-wrap">
          <Button size="small" onClick={() => navigate(`/admin/users/${row.id}`)}>
            查看详情
          </Button>
          <Button
            size="small"
            type="dashed"
            onClick={() => {
              setResetModal({ open: true, userId: row.id, current: row.credits })
              setNewBalance(row.credits)
            }}
          >
            重置积分
          </Button>
          <Button
            size="small"
            danger={row.is_active}
            onClick={async () => {
              await axios.patch(`/api/admin/users/${row.id}/status`)
              actionRef.current?.reload()
            }}
          >
            {row.is_active ? '禁用' : '启用'}
          </Button>
        </div>
      ),
    },
  ]

  const handleResetCredits = async () => {
    try {
      await axios.post(`/api/admin/users/${resetModal.userId}/credits/reset`, { balance: newBalance })
      message.success('积分已重置')
      setResetModal(prev => ({ ...prev, open: false }))
      actionRef.current?.reload()
    } catch (e: unknown) {
      message.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '重置失败')
    }
  }

  return (
    <>
      <ProTable<UserRow>
        headerTitle="用户管理"
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        request={async (params) => {
          const res = await axios.get('/api/admin/users', {
            params: { page: params.current, page_size: params.pageSize, keyword: params.keyword },
          })
          return { data: res.data.data, total: res.data.total, success: true }
        }}
        search={{ labelWidth: 'auto', filterType: 'light' }}
        pagination={{ pageSize: 20, showSizeChanger: true }}
        scroll={{ x: 900 }}
      />

      <Modal
        title="重置用户积分"
        open={resetModal.open}
        onOk={handleResetCredits}
        onCancel={() => setResetModal(prev => ({ ...prev, open: false }))}
        okText="确认重置"
      >
        <p className="text-gray-400 text-sm mb-3">当前余额：{resetModal.current} 积分</p>
        <InputNumber
          min={0}
          value={newBalance}
          onChange={v => setNewBalance(v ?? 0)}
          addonAfter="积分"
          style={{ width: '100%' }}
        />
      </Modal>
    </>
  )
}
