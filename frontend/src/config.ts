/**
 * 应用配置
 * 从环境变量读取配置，提供默认值
 */

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
