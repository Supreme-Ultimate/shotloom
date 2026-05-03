import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { useAuth } from './contexts/auth-context'
import { APP_BASE_PATH } from './config'
import './index.css'

const HomePage = lazy(() => import('./pages/HomePage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const RegisterPage = lazy(() => import('./pages/RegisterPage'))
const AnalysisPageWrapper = lazy(() => import('./pages/AnalysisPageWrapper'))
const AdminLayout = lazy(() => import('./pages/admin/AdminLayout'))
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'))
const AdminUserDetail = lazy(() => import('./pages/admin/AdminUserDetail'))

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <div className="flex items-center justify-center h-screen bg-[#0f0f14] text-gray-400">加载中…</div>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="flex items-center justify-center h-screen bg-[#0f0f14] text-gray-400">加载中…</div>
  if (!user) return <Navigate to="/login" replace />
  if (!user.is_superuser) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter basename={APP_BASE_PATH}>
      <AuthProvider>
        <Suspense fallback={<div className="flex items-center justify-center h-screen bg-[#0f0f14] text-gray-400">加载中…</div>}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/" element={<RequireAuth><HomePage /></RequireAuth>} />
          <Route path="/analysis/:videoId" element={<RequireAuth><AnalysisPageWrapper /></RequireAuth>} />

          <Route path="/admin" element={<RequireAdmin><AdminLayout /></RequireAdmin>}>
            <Route index element={<Navigate to="/admin/users" replace />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="users/:userId" element={<AdminUserDetail />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
