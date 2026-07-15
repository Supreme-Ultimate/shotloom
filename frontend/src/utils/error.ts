type ApiErrorDetail = string | Array<{ msg?: string } & Record<string, unknown>> | undefined

export const MODEL_PROVIDER_BUSY_MESSAGE = '模型服务当前负载过高，请稍后手动重试。'

interface ApiErrorLike {
  message?: string
  response?: {
    status?: number
    data?: {
      detail?: ApiErrorDetail
    }
  }
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const apiError = error as ApiErrorLike
  const detail = apiError.response?.data?.detail
  let message = ''
  if (Array.isArray(detail)) {
    message = detail.map((item) => item.msg || JSON.stringify(item)).join(', ')
  } else {
    message = detail || apiError.message || fallback
  }
  return getUserFacingErrorMessage(message, fallback)
}

export function getApiErrorStatus(error: unknown): number | undefined {
  return (error as ApiErrorLike).response?.status
}

export function getApiErrorData(error: unknown): unknown {
  return (error as ApiErrorLike).response?.data
}

export function isProviderQuotaMessage(message: string): boolean {
  const normalized = message.toLowerCase()
  return message.includes(MODEL_PROVIDER_BUSY_MESSAGE)
    || normalized.includes('insufficient_quota')
    || normalized.includes('current quota')
    || normalized.includes('token-limit')
    || normalized.includes('you exceeded your current quota')
    || normalized.includes('rate limit')
    || normalized.includes('rate_limit')
    || normalized.includes('rate_limit_exceeded')
    || normalized.includes('too many requests')
}

export function getUserFacingErrorMessage(message: string | undefined, fallback = '操作失败'): string {
  const raw = message?.trim() || fallback
  if (isProviderQuotaMessage(raw)) return MODEL_PROVIDER_BUSY_MESSAGE
  return raw
}

export function isAppCreditError(error: unknown): boolean {
  const status = getApiErrorStatus(error)
  const message = getApiErrorMessage(error, '')

  return status === 402 && message.includes('积分不足')
}

export function isProviderQuotaError(error: unknown): boolean {
  const apiError = error as ApiErrorLike
  const detail = apiError.response?.data?.detail
  const message = Array.isArray(detail)
    ? detail.map((item) => item.msg || JSON.stringify(item)).join(', ')
    : detail || apiError.message || ''
  return isProviderQuotaMessage(message)
}

export function isCreditOrQuotaError(error: unknown): boolean {
  return isAppCreditError(error)
}
