/**
 * Axios 实例配置
 * 统一管理 API 请求
 */
import axios from 'axios'
import { API_BASE_URL } from '../config'

// 创建 axios 实例
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0, // 不设全局超时，避免大文件上传被中断
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.request.use(
  (config) => {
    // 如果是 FormData，删除 Content-Type 让浏览器自动设置（包含 boundary）
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type']
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一处理错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Cookie 过期或无效，跳转登录页
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
