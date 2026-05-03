import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Tag, Spin, Empty, message, Modal } from 'antd'
import CreditsDisplay from '../components/CreditsDisplay'
import BrandMark from '../components/BrandMark'
import { useAuth } from '../contexts/auth-context'
import api from '../utils/api'
import { API_BASE_URL } from '../config'
import { APP_VERSION } from '../config/version'
import { getApiErrorData, getApiErrorMessage, getApiErrorStatus } from '../utils/error'

interface Video {
  id: number
  filename: string
  duration: number
  status: string
  created_at: string
  shot_count: number
}

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  uploaded: { color: 'default', label: '已上传' },
  detecting: { color: 'processing', label: '检测中' },
  detected: { color: 'blue', label: '已检测' },
  analyzing: { color: 'processing', label: '分析中' },
  completed: { color: 'success', label: '已完成' },
  error: { color: 'error', label: '错误' },
}

export default function HomePage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [videos, setVideos] = useState<Video[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await uploadFile(file)
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    await uploadFile(file)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const uploadFile = async (file: File) => {
    setUploading(true)
    setUploadProgress(0)
    const form = new FormData()
    form.append('file', file)

    try {
      const res = await api.post('/api/upload', form, {
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      message.success('上传成功')
      navigate(`/analysis/${res.data.video_id}`)
    } catch (err: unknown) {
      console.error('上传失败:', getApiErrorStatus(err), getApiErrorData(err))
      message.error(getApiErrorMessage(err, '上传失败'))
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async (e: React.MouseEvent, videoId: number, filename: string) => {
    e.stopPropagation()

    Modal.confirm({
      title: '确认删除',
      content: `确定要删除视频「${filename}」吗？此操作将删除视频文件、所有镜头切片、缩略图和分析结果，且无法恢复。`,
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        setDeletingId(videoId)
        try {
          await api.delete(`/api/videos/${videoId}`)
          message.success('删除成功')
          loadVideos()
        } catch (err: unknown) {
          message.error(getApiErrorMessage(err, '删除失败'))
        } finally {
          setDeletingId(null)
        }
      },
    })
  }

  const loadVideos = async () => {
    try {
      const res = await api.get('/api/videos')
      setVideos(res.data)
    } catch (err) {
      console.error('加载视频列表失败:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadVideos()
  }, [])

  const formatDuration = (seconds: number) => {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="min-h-screen bg-[#0f0f14] flex flex-col">
      {/* 顶部导航 */}
      <header className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 bg-[#12121f] border-b border-gray-800">
        <BrandMark size="sm" subtitle="Shot intelligence" />
        <div className="flex flex-wrap items-center justify-end gap-4">
          <CreditsDisplay />
          <span className="text-gray-400 text-xs">{user?.display_name || user?.email}</span>
          {user?.is_superuser && (
            <a href="/admin" className="text-xs text-[#d8a24a] hover:text-[#eecb7a] transition-colors">
              管理后台
            </a>
          )}
          <button
            onClick={logout}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            退出
          </button>
        </div>
      </header>

      {/* 主体内容 */}
      <div className="flex-1 overflow-y-auto relative">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {loading ? (
            <div className="flex justify-center py-12">
              <Spin />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {/* 上传区卡片 - 左上角第一个 */}
              <div
                className="bg-[#1a1a2e] border-2 border-dashed border-gray-600 hover:border-[#d8a24a] rounded-lg p-8 flex flex-col items-center justify-center gap-3 cursor-pointer transition-all min-h-[280px] hover:bg-[#1f1f35]"
                onClick={() => fileInputRef.current?.click()}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*"
                  className="hidden"
                  onChange={handleFileSelect}
                  disabled={uploading}
                />
                <img src="/shotloom.svg" alt="" className="h-12 w-12 rounded-2xl opacity-90" />
                {uploading ? (
                  <>
                    <p className="text-sm text-gray-300 font-medium">上传中 {uploadProgress}%</p>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <div
                        className="bg-[#d8a24a] h-2 rounded-full transition-all"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm text-gray-300 font-medium text-center">上传新视频</p>
                    <p className="text-xs text-gray-500 text-center">支持 MP4 / MOV / AVI / MKV</p>
                  </>
                )}
              </div>

              {/* 视频项目卡片 */}
              {videos.length === 0 ? (
                <div className="col-span-full flex justify-center py-12">
                  <Empty
                    description="暂无视频，点击左上角上传"
                    style={{ color: '#6b7280' }}
                  />
                </div>
              ) : (
                videos.map((video) => {
                  const statusInfo = STATUS_CONFIG[video.status] || { color: 'default', label: video.status }
                  return (
                    <div
                      key={video.id}
                      onClick={() => navigate(`/analysis/${video.id}`)}
                      className="bg-[#1a1a2e] border border-gray-700 hover:border-[#d8a24a] rounded-lg overflow-hidden cursor-pointer transition-all hover:shadow-lg hover:shadow-indigo-500/20"
                    >
                      {/* 视频预览图 */}
                      <div className="relative aspect-video bg-gray-900 flex items-center justify-center overflow-hidden group">
                        <img
                          src={`${API_BASE_URL}/api/video-thumbnail/${video.id}`}
                          alt={video.filename}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                            const placeholder = e.currentTarget.nextElementSibling as HTMLElement
                            if (placeholder) placeholder.style.display = 'flex'
                          }}
                        />
                        <img src="/shotloom.svg" alt="" className="hidden h-16 w-16 rounded-2xl opacity-25" />
                        <div className="absolute top-2 right-2 flex gap-2">
                          <Tag color={statusInfo.color} className="text-xs">
                            {statusInfo.label}
                          </Tag>
                        </div>
                        <button
                          onClick={(e) => handleDelete(e, video.id, video.filename)}
                          disabled={deletingId === video.id}
                          className="absolute top-2 left-2 bg-red-600 hover:bg-red-700 text-white text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
                        >
                          {deletingId === video.id && (
                            <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                          )}
                          {deletingId === video.id ? '删除中...' : '删除'}
                        </button>
                      </div>

                      {/* 视频信息 */}
                      <div className="p-4 space-y-2">
                        <h3 className="text-white text-sm font-medium truncate">
                          {video.filename}
                        </h3>
                        <div className="flex items-center gap-4 text-xs text-gray-400">
                          <span>⏱ {formatDuration(video.duration)}</span>
                          {video.shot_count > 0 && (
                            <span>📹 {video.shot_count} 镜头</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500">
                          {new Date(video.created_at).toLocaleString('zh-CN', {
                            month: 'numeric',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          )}
        </div>

        {/* 版本号 - 左下角固定 */}
        <div className="fixed bottom-4 left-4 text-xs text-gray-500 select-none">
          {APP_VERSION}
        </div>
      </div>
    </div>
  )
}
