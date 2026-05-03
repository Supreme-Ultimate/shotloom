import { useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import api from '../utils/api'
import { useAuth } from '../contexts/auth-context'

const schema = z.object({
  display_name: z.string().min(1, '请输入昵称').max(20, '昵称不超过 20 个字符'),
  email: z.string().email('请输入有效的邮箱地址'),
  password: z.string().min(6, '密码不能少于 6 位'),
  confirm: z.string(),
}).refine(d => d.password === d.confirm, {
  message: '两次密码不一致',
  path: ['confirm'],
})
type FormData = z.infer<typeof schema>

export default function RegisterPage() {
  const { refreshUser, user } = useAuth()
  const navigate = useNavigate()

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
      await api.post('/api/auth/register', {
        email: data.email,
        password: data.password,
        display_name: data.display_name,
      })
      await refreshUser()
      navigate('/')
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '注册失败，请稍后重试'
      setError('root', { message: msg })
    }
  }

  return (
    <div className="min-h-screen bg-[#0f0f14] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="text-3xl mb-2">🎬</div>
          <h1 className="text-white text-xl font-semibold">ShotLoom</h1>
          <p className="text-gray-500 text-sm mt-1">注册新账号，开始你的创作分析之旅</p>
        </div>

        <div className="bg-[#12121f] border border-gray-800 rounded-xl p-6 shadow-xl">
          <h2 className="text-white text-base font-medium mb-5">创建账号</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="text-gray-400 text-xs mb-1 block">昵称</label>
              <input
                {...register('display_name')}
                type="text"
                placeholder="你的名字"
                className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {errors.display_name && <p className="text-red-400 text-xs mt-1">{errors.display_name.message}</p>}
            </div>

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
                placeholder="至少 6 位"
                className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
            </div>

            <div>
              <label className="text-gray-400 text-xs mb-1 block">确认密码</label>
              <input
                {...register('confirm')}
                type="password"
                placeholder="再次输入密码"
                className="w-full bg-[#1a1a2e] border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {errors.confirm && <p className="text-red-400 text-xs mt-1">{errors.confirm.message}</p>}
            </div>

            {errors.root && (
              <p className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-3 py-2">{errors.root.message}</p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
            >
              {isSubmitting ? '注册中…' : '注册'}
            </button>
          </form>

          <p className="text-center text-gray-600 text-xs mt-4">
            已有账号？{' '}
            <Link to="/login" className="text-indigo-400 hover:text-indigo-300">
              立即登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
