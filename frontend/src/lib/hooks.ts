import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

/** Fetch JSON with loading/error state; `reload()` refetches; optional polling. */
export function useApi<T>(path: string | null, opts: { poll?: number | ((d: T | undefined) => number | false) } = {}) {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(!!path)
  const dataRef = useRef<T | undefined>(undefined)
  const pollRef = useRef(opts.poll)
  pollRef.current = opts.poll

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!path) return
    try {
      const d = await api<T>(path, { signal })
      dataRef.current = d
      setData(d)
      setError(null)
    } catch (e: any) {
      if (e?.name !== 'AbortError') setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [path])

  useEffect(() => {
    if (!path) return
    const ctrl = new AbortController()
    let timer: number | undefined
    let alive = true
    const tick = async () => {
      await load(ctrl.signal)
      if (!alive) return
      const p = pollRef.current
      const ms = typeof p === 'function' ? p(dataRef.current) : p
      if (ms) timer = window.setTimeout(tick, ms)
    }
    setLoading(true)
    tick()
    return () => { alive = false; ctrl.abort(); if (timer) clearTimeout(timer) }
  }, [path, load])

  return { data, setData, error, loading, reload: () => load() }
}

export function useKey(handler: (e: KeyboardEvent) => void, deps: unknown[]) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      handler(e)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
