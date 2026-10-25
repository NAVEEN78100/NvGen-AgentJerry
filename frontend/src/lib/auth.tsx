import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken } from './api'

interface User { id: string; name: string; email: string; role: string; title: string }
interface AuthState {
  user: User | null; org: { id: string; name: string } | null
  engine: { provider: string; model: string | null; enabled: boolean } | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [org, setOrg] = useState<AuthState['org']>(null)
  const [engine, setEngine] = useState<AuthState['engine']>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!getToken()) { setLoading(false); return }
    try {
      const me = await api('/auth/me')
      setUser(me.user); setOrg(me.org); setEngine(me.engine)
    } catch { setUser(null) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onOut = () => { setUser(null); setOrg(null) }
    window.addEventListener('agentjerry:logout', onOut)
    return () => window.removeEventListener('agentjerry:logout', onOut)
  }, [])

  const login = async (email: string, password: string) => {
    const r = await api('/auth/login', { body: { email, password } })
    setToken(r.token)
    await load()
  }
  const logout = () => { setToken(null); setUser(null); setOrg(null) }

  return <Ctx.Provider value={{ user, org, engine, loading, login, logout }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside provider')
  return v
}
