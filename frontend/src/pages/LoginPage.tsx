import { useEffect } from 'react'
import { useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import api from '../utils/api'
import { useAuth } from '../contexts/auth-context'

const schema = z.object({
  email: z.string().email('请输入有效的邮箱地址'),
  password: z.string().min(6, '密码不能少于 6 位'),
})
type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const { refreshUser, user } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  // 处理微信 OAuth 回调（token 在 query string 里）
  useEffect(() => {
    const wechatCode = searchParams.get('wechat_code')
    if (wechatCode) {
      api.post('/api/auth/wechat/exchange', null, { params: { code: wechatCode } })
        .then(async () => {
          await refreshUser()
          navigate('/', { replace: true })
        })
        .catch(() => navigate('/login', { replace: true }))
    }
  }, [])

  // 已登录则跳转首页
  useEffect(() => {
    if (user) navigate('/', { replace: true })
  }, [user])

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    try {
      await api.post('/api/auth/login', data)
      await refreshUser()
      navigate('/')
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '登录失败，请检查邮箱和密码'
      setError('root', { message: msg })
    }
  }

  return (
    <div className="min-h-screen bg-[#0f0f14] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-3xl mb-2">🎬</div>
          <h1 className="text-white text-xl font-semibold">ShotLoom</h1>
          <p className="text-gray-500 text-sm mt-1">AI 驱动的镜头语言分析与拉片工作台</p>
        </div>

        {/* 登录卡片 */}
        <div className="bg-[#12121f] border border-gray-800 rounded-xl p-6 shadow-xl">
          <h2 className="text-white text-base font-medium mb-5">登录账号</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="text-gray-400 text-xs mb-1 block">邮箱</label>
              <input
                {...register('email')}
                type="email"
                placeholder="your@email.com"
                className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {errors.email && <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>}
            </div>

            <div>
              <label className="text-gray-400 text-xs mb-1 block">密码</label>
              <input
                {...register('password')}
                type="password"
                placeholder="••••••••"
                className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
            </div>

            {errors.root && (
              <p className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errors.root.message}</p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
            >
              {isSubmitting ? '登录中…' : '登录'}
            </button>
          </form>

          {/* 微信登录 - 暂时禁用 */}
          {/* <div className="mt-4">
            <div className="flex items-center gap-3 my-4">
              <div className="flex-1 h-px bg-gray-800" />
              <span className="text-gray-600 text-xs">或</span>
              <div className="flex-1 h-px bg-gray-800" />
            </div>
            <a
              href="/api/auth/wechat/login"
              className="flex items-center justify-center gap-2 w-full border border-gray-700 hover:border-green-600 text-gray-300 hover:text-green-400 rounded-lg py-2 text-sm transition-colors"
            >
              <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current">
                <path d="M8.5 11.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm5 0a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/>
                <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm-1.5 14.5c-.828 0-1.5-.672-1.5-1.5v-1c-1.5-.5-2.5-1.828-2.5-3.25C6.5 8.753 8.753 7 12 7s5.5 1.753 5.5 3.75c0 2.071-2.5 3.75-5.5 3.75-.414 0-.817-.04-1.197-.112L9.5 15.5l.5-1.25c-.331.158-.668.25-1 .25h-.5z"/>
              </svg>
              微信扫码登录
            </a>
          </div> */}

          <p className="text-center text-gray-600 text-xs mt-4">
            还没有账号？{' '}
            <Link to="/register" className="text-indigo-400 hover:text-indigo-300">
              立即注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
