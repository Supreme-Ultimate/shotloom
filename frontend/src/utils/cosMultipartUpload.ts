import axios, { AxiosError } from 'axios'
import api from './api'

const CONCURRENCY = 4
const MAX_ATTEMPTS = 3

interface SignedPart {
  part_number: number
  url: string
}

interface InitResponse {
  session_id: string
  part_size: number
  part_count: number
  parts: SignedPart[]
}

interface CompletedVideo {
  video_id: number
  filename: string
  duration: number
  fps: number
  width: number | null
  height: number | null
}

const delay = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds))

async function renewPartUrl(sessionId: string, partNumber: number) {
  const response = await api.post<{ parts: SignedPart[] }>(
    `/api/uploads/cos/${sessionId}/parts/sign`,
    { part_numbers: [partNumber] },
  )
  return response.data.parts[0].url
}

export async function uploadVideoMultipart(
  file: File,
  onProgress: (percent: number) => void,
): Promise<CompletedVideo> {
  const initialized = await api.post<InitResponse>('/api/uploads/cos/init', {
    filename: file.name,
    file_size: file.size,
    content_type: file.type || 'application/octet-stream',
  })
  const session = initialized.data
  const urls = new Map(session.parts.map((part) => [part.part_number, part.url]))
  const uploadedBytes = new Map<number, number>()
  const etags = new Map<number, string>()

  const reportProgress = () => {
    const loaded = [...uploadedBytes.values()].reduce((sum, value) => sum + value, 0)
    onProgress(Math.min(99, Math.floor((loaded / file.size) * 100)))
  }

  let nextPart = 1
  const uploadPart = async (partNumber: number) => {
    const start = (partNumber - 1) * session.part_size
    const blob = file.slice(start, Math.min(start + session.part_size, file.size))
    let lastError: unknown

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      uploadedBytes.set(partNumber, 0)
      reportProgress()
      try {
        let url = urls.get(partNumber)
        if (!url || attempt > 1) {
          url = await renewPartUrl(session.session_id, partNumber)
          urls.set(partNumber, url)
        }
        const response = await axios.put(url, blob, {
          withCredentials: false,
          timeout: 0,
          onUploadProgress: (event) => {
            uploadedBytes.set(partNumber, Math.min(event.loaded, blob.size))
            reportProgress()
          },
        })
        const etag = response.headers.etag as string | undefined
        if (!etag) {
          throw new Error('对象存储未返回 ETag，请确认 COS 跨域规则已暴露 ETag 响应头')
        }
        uploadedBytes.set(partNumber, blob.size)
        etags.set(partNumber, etag)
        reportProgress()
        return
      } catch (error) {
        lastError = error
        const status = error instanceof AxiosError ? error.response?.status : undefined
        if (attempt === MAX_ATTEMPTS || (status !== undefined && status < 500 && status !== 401 && status !== 403 && status !== 408 && status !== 429)) {
          break
        }
        await delay(500 * 2 ** (attempt - 1))
      }
    }
    throw lastError
  }

  let uploadFailure: unknown
  try {
    const worker = async () => {
      while (!uploadFailure && nextPart <= session.part_count) {
        const partNumber = nextPart
        nextPart += 1
        try {
          await uploadPart(partNumber)
        } catch (error) {
          uploadFailure = error
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, session.part_count) }, worker))
    if (uploadFailure) throw uploadFailure
  } catch (error) {
    await api.delete(`/api/uploads/cos/${session.session_id}`).catch(() => undefined)
    throw error
  }

  // Once COS has merged the parts, aborting is no longer valid. If server-side
  // materialization fails, leave the session intact so completing can be retried.
  const completed = await api.post<CompletedVideo>(`/api/uploads/cos/${session.session_id}/complete`, {
    parts: Array.from({ length: session.part_count }, (_, index) => ({
      part_number: index + 1,
      etag: etags.get(index + 1),
    })),
  })
  onProgress(100)
  return completed.data
}
