/**
 * 应用配置
 * 从环境变量读取配置，提供默认值
 */


// 前端部署基础路径；Vite 会在子路径部署时注入，例如 /shotloom/
const rawBasePath = import.meta.env.BASE_URL || '/'
export const APP_BASE_PATH = rawBasePath === '/' ? '/' : `/${rawBasePath.replace(/^\/+|\/+$/g, '')}`
export const ASSET_BASE_URL = APP_BASE_PATH === '/' ? '/' : `${APP_BASE_PATH}/`
export const LOGIN_URL = `${APP_BASE_PATH === '/' ? '' : APP_BASE_PATH}/login`
export const SHOTLOOM_LOGO_URL = `${ASSET_BASE_URL}shotloom.svg`

// 单个上传文件最大体积，需与后端 MAX_UPLOAD_SIZE_MB / Nginx client_max_body_size 保持一致。
const parsedMaxUploadSizeMb = Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_MB || '1024')
export const MAX_UPLOAD_SIZE_MB = Number.isFinite(parsedMaxUploadSizeMb) && parsedMaxUploadSizeMb > 0
  ? parsedMaxUploadSizeMb
  : 1024
export const MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
export const UPLOAD_LIMIT_LABEL = MAX_UPLOAD_SIZE_MB >= 1024 && MAX_UPLOAD_SIZE_MB % 1024 === 0
  ? `${MAX_UPLOAD_SIZE_MB / 1024}GB`
  : `${MAX_UPLOAD_SIZE_MB}MB`

// API 基础地址
// 开发环境：通过 Vite proxy 转发，使用空字符串
// 生产环境：使用环境变量中配置的完整 URL
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 应用标题
export const APP_TITLE = import.meta.env.VITE_APP_TITLE || 'ShotLoom'

// 是否为生产环境
export const IS_PRODUCTION = import.meta.env.PROD

// 是否为开发环境
export const IS_DEVELOPMENT = import.meta.env.DEV
