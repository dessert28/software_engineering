import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Spin } from 'antd'
import { api, tokenStore, type User } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<User>
  logout: () => void
  hasRole: (...roles: User['role'][]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  // 刷新页面时用已存 token 换回用户信息
  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false)
      return
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      async login(email, password) {
        const { access_token, user: u } = await api.login(email, password)
        tokenStore.set(access_token)
        setUser(u)
        return u
      },
      logout() {
        tokenStore.clear()
        setUser(null)
      },
      hasRole: (...roles) => !!user && roles.includes(user.role),
    }),
    [user, loading],
  )

  if (loading) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="正在恢复登录状态…" />
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
