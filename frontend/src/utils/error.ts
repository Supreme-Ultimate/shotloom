type ApiErrorDetail = string | Array<{ msg?: string } & Record<string, unknown>> | undefined

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
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || JSON.stringify(item)).join(', ')
  }
  return detail || apiError.message || fallback
}

export function getApiErrorStatus(error: unknown): number | undefined {
  return (error as ApiErrorLike).response?.status
}

export function getApiErrorData(error: unknown): unknown {
  return (error as ApiErrorLike).response?.data
}

export function isCreditOrQuotaError(error: unknown): boolean {
  const status = getApiErrorStatus(error)
  const message = getApiErrorMessage(error, '')
  const normalized = message.toLowerCase()

  // App credits are explicit 402 responses from our backend.
  if (status === 402 && message.includes('积分不足')) return true

  // Model-provider quota errors must be matched by explicit provider markers.
  return normalized.includes('insufficient_quota')
    || normalized.includes('current quota')
    || normalized.includes('token-limit')
}
