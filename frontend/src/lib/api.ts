const TOKEN_KEY = 'agentjerry.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

type Opts = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal }

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const t = getToken()
  if (t) headers.Authorization = `Bearer ${t}`
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body) }
  let res: Response
  try {
    res = await fetch(`/api${path}`, { method: opts.method || (body ? 'POST' : 'GET'), headers, body, signal: opts.signal })
  } catch (e: any) {
    if (e?.name === 'AbortError') throw e
    throw new ApiError(0, 'Can’t reach the AgentJerry server. Check that it’s running.')
  }
  if (res.status === 401 && path !== '/auth/login') {
    setToken(null)
    window.dispatchEvent(new Event('agentjerry:logout'))
  }
  const text = await res.text()
  const data = text ? (() => { try { return JSON.parse(text) } catch { return text } })() : null
  if (!res.ok) {
    let msg = 'Something went wrong.'
    if (data && typeof data === 'object' && 'detail' in data) {
      const d = (data as any).detail
      msg = typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: any) => x.msg).join('; ') : msg
    }
    throw new ApiError(res.status, msg)
  }
  return data as T
}
