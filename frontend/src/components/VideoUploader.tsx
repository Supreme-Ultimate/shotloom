import { useCallback, useState } from 'react'
import axios from 'axios'

interface Props {
  onUploadComplete: (videoId: number) => void
}

export default function VideoUploader({ onUploadComplete }: Props) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')

  const upload = useCallback(async (file: File) => {
    setError('')
    setUploading(true)
    setProgress(0)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await axios.post('/api/upload', form, {
        onUploadProgress: (e) => {
          if (e.total) setProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      onUploadComplete(res.data.video_id)
    } catch (e: any) {
      setError(e.response?.data?.detail || '上传失败')
    } finally {
      setUploading(false)
    }
  }, [onUploadComplete])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload(file)
  }, [upload])

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) upload(file)
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#0f0f14] px-4">
      <div className="mb-8 text-center">
        <h1 className="text-4xl font-bold text-white mb-2">视频拉片工具</h1>
        <p className="text-gray-400 text-sm">AI 驱动的镜头语言分析 · Powered by Qwen</p>
      </div>

      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`w-full max-w-xl border-2 border-dashed rounded-2xl p-16 flex flex-col items-center gap-4 cursor-pointer transition-all
          ${dragging ? 'border-indigo-400 bg-indigo-950/30' : 'border-gray-600 hover:border-indigo-500 bg-[#16162a]'}`}
      >
        <input type="file" accept="video/*" className="hidden" onChange={onFileChange} />
        <div className="text-5xl">🎬</div>
        <p className="text-lg text-gray-300 font-medium">
          {uploading ? `上传中 ${progress}%` : '拖拽视频到这里，或点击选择'}
        </p>
        <p className="text-xs text-gray-500">支持 MP4 / MOV / AVI / MKV / WebM</p>

        {uploading && (
          <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
            <div
              className="bg-indigo-500 h-2 rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
        {error && <p className="text-red-400 text-sm">{error}</p>}
      </label>
    </div>
  )
}
