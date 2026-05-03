import { MAX_UPLOAD_SIZE_BYTES, UPLOAD_LIMIT_LABEL } from '../config'

export const SUPPORTED_VIDEO_FORMATS = 'MP4 / MOV / AVI / MKV / WebM'
export const UPLOAD_HELP_TEXT = `支持 ${SUPPORTED_VIDEO_FORMATS}，单个文件最大 ${UPLOAD_LIMIT_LABEL}`

export function getUploadSizeError(file: File) {
  if (file.size <= MAX_UPLOAD_SIZE_BYTES) return null
  return `文件过大，单个视频最大支持 ${UPLOAD_LIMIT_LABEL}`
}
