import { Outlet, useNavigate, useLocation, Link } from 'react-router-dom'
import { StyleProvider } from '@ant-design/cssinjs'
import { ConfigProvider, Layout, Menu, theme } from 'antd'
import { useAuth } from '../../contexts/auth-context'
import BrandMark from '../../components/BrandMark'

const { Sider, Content } = Layout

const menuItems = [
  { key: '/admin/users', label: '用户管理', icon: '👥' },
]

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <StyleProvider layer>
      <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
        <Layout className="min-h-screen" style={{ background: '#0f0f14' }}>
          <Sider
            width={200}
            style={{ background: '#12121f', borderRight: '1px solid #1f2937' }}
          >
            {/* Brand */}
            <div className="px-4 py-4 border-b border-gray-800">
              <Link to="/" className="block hover:opacity-90 transition-opacity">
                <BrandMark size="sm" subtitle="管理后台" />
              </Link>
            </div>

            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              style={{ background: 'transparent', border: 'none', marginTop: 8 }}
              items={menuItems.map(item => ({
                key: item.key,
                label: `${item.icon} ${item.label}`,
                onClick: () => navigate(item.key),
              }))}
            />
          </Sider>

          <Layout style={{ background: '#0f0f14' }}>
            {/* 顶栏 */}
            <div className="flex items-center justify-between px-6 py-3 bg-[#12121f] border-b border-gray-800">
              <span className="text-gray-300 text-sm font-medium">管理后台</span>
              <div className="flex items-center gap-3">
                <span className="text-gray-500 text-xs">{user?.display_name || user?.email}</span>
                <button
                  onClick={logout}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  退出
                </button>
              </div>
            </div>

            <Content style={{ padding: '24px', overflow: 'auto' }}>
              <Outlet />
            </Content>
          </Layout>
        </Layout>
      </ConfigProvider>
    </StyleProvider>
  )
}
