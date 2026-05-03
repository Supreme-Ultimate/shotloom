import { createContext, useContext } from 'react'

export interface AuthUser {
  id: number
  email: string
  display_name: string | null
  is_superuser: boolean
  is_active: boolean
}

export interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  refreshUser: () => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  refreshUser: async () => {},
  logout: async () => {},
})

export function useAuth() {
  return useContext(AuthContext)
}
