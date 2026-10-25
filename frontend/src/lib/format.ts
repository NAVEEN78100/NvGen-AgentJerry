export function timeAgo(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso).getTime()
  const s = Math.round((Date.now() - d) / 1000)
  if (s < 10) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const days = Math.round(h / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export function dateTime(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export function untilLabel(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = d.getTime() - Date.now()
  const h = Math.round(diff / 3_600_000)
  const when = d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
  if (h < 1) return `${when} (soon)`
  if (h < 24) return `${when} (in ${h}h)`
  return `${when} (in ${Math.round(h / 24)}d)`
}

export function duration(ms?: number | null): string {
  if (ms == null) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

export const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`
