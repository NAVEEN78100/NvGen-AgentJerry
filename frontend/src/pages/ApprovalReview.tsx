import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ArrowLeft, BookOpen, Check, ChevronDown, Pencil, ShieldCheck, Undo2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ErrorNote, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { HEX } from '../lib/fields'
import { dateTime } from '../lib/format'
import { useApi, useKey } from '../lib/hooks'
import type { Approval, ApprovalItem } from '../lib/types'

type Dec = { status: 'pending' | 'approved' | 'rejected'; subject: string; body: string; to: string }

export function ApprovalReview() {
  const { approvalId } = useParams()
  const nav = useNavigate()
  const ap = useApi<Approval>(`/approvals/${approvalId}`)
  const [decs, setDecs] = useState<Record<number, Dec>>({})
  const [sel, setSel] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [showRow, setShowRow] = useState(false)
  const items = ap.data?.items || []
  const readOnly = ap.data?.status !== 'pending'

  useEffect(() => {
    if (!ap.data?.items) return
    const init: Record<number, Dec> = {}
    ap.data.items.forEach(it => { init[it.id] = { status: it.status, subject: it.payload.subject, body: it.payload.body, to: it.payload.to } })
    setDecs(init)
    setSel(s => s ?? ap.data!.items![0]?.id ?? null)
  }, [ap.data?.id, ap.data?.status]) // eslint-disable-line

  const counts = useMemo(() => {
    const v = Object.values(decs)
    return { approved: v.filter(d => d.status === 'approved').length, rejected: v.filter(d => d.status === 'rejected').length, pending: v.filter(d => d.status === 'pending').length }
  }, [decs])

  const cur = items.find(i => i.id === sel)
  const curDec = sel != null ? decs[sel] : undefined
  const idx = items.findIndex(i => i.id === sel)
  const edited = (it: ApprovalItem) => decs[it.id] && (decs[it.id].subject !== it.payload.subject || decs[it.id].body !== it.payload.body || decs[it.id].to !== it.payload.to)

  const setStatus = (id: number, status: Dec['status'], advance = true) => {
    if (readOnly) return
    setDecs(d => ({ ...d, [id]: { ...d[id], status } }))
    if (advance && status !== 'pending') {
      const next = items.slice(idx + 1).find(i => decs[i.id]?.status === 'pending') || items.find(i => i.id !== id && decs[i.id]?.status === 'pending')
      if (next) setSel(next.id)
    }
  }
  const approveRemaining = () => setDecs(d => {
    const n = { ...d }
    items.forEach(it => { if (n[it.id].status === 'pending') n[it.id] = { ...n[it.id], status: 'approved' } })
    return n
  })

  useKey(e => {
    if (!cur || readOnly) return
    if (e.key === 'a') setStatus(cur.id, 'approved')
    else if (e.key === 'r') setStatus(cur.id, 'rejected')
    else if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); items[idx + 1] && setSel(items[idx + 1].id) }
    else if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); items[idx - 1] && setSel(items[idx - 1].id) }
  }, [cur, idx, items, decs, readOnly])

  const submit = async () => {
    if (!ap.data) return
    setSubmitting(true)
    try {
      const decisions = items.map(it => {
        const d = decs[it.id]
        return { id: it.id, status: d.status, ...(edited(it) ? { subject: d.subject, body: d.body, to: d.to } : {}) }
      })
      await api(`/approvals/${ap.data.id}/decide`, { body: { decisions } })
      toast.success(`Sending ${counts.approved} email${counts.approved === 1 ? '' : 's'} · ${counts.rejected} rejected`)
      nav(`/agents/${ap.data.agent_id}/runs/${ap.data.execution_id}`)
    } catch (e: any) { toast.error(e.message) } finally { setSubmitting(false) }
  }

  if (ap.error) return <ErrorNote message={ap.error} onRetry={ap.reload} />
  if (!ap.data || !cur || !curDec) return <div className="space-y-3"><Skeleton className="h-8 w-72" /><Skeleton className="h-[520px] w-full" /></div>
  const a = ap.data
  const errors = cur.flags.filter(f => f.level === 'error')

  return (
    <div className="pb-24">
      <Link to="/approvals" className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-2 hover:text-ink mb-3"><ArrowLeft className="h-4 w-4" />Approvals</Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-semibold">{readOnly ? 'Decided' : 'Review before sending'}</h1>
          <p className="mt-1 text-ink-2 text-[14px]">{a.title}</p>
        </div>
        <div className="flex items-center gap-2 text-[13px] text-ink-2"><ShieldCheck className="h-4 w-4" style={{ color: HEX.approval }} />{a.reason}</div>
      </div>
      {readOnly && <div className="mt-3 text-[13px] text-ink-2">Decided by <b className="text-ink">{a.decided_by || '—'}</b> on {dateTime(a.decided_at)}{a.status === 'expired' ? ' · this request expired because the run was cancelled' : ''}.</div>}

      <div className="mt-5 grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)] items-start">
        <div className="card overflow-hidden lg:sticky lg:top-20">
          <div className="px-4 h-11 flex items-center justify-between border-b border-line text-[13px]">
            <span className="font-semibold">{items.length} drafts</span>
            {!readOnly && <span className="hidden sm:flex items-center gap-1 text-2xs text-ink-3"><span className="kbd">J</span><span className="kbd">K</span> move <span className="kbd">A</span> approve <span className="kbd">R</span> reject</span>}
          </div>
          <ul className="max-h-[62vh] overflow-y-auto thin-scroll" role="listbox" aria-label="Drafts">
            {items.map(it => {
              const d = decs[it.id]
              return (
                <li key={it.id}>
                  <button role="option" aria-selected={sel === it.id} onClick={() => setSel(it.id)}
                    className={clsx('w-full text-left px-4 py-2.5 flex items-center gap-3 border-b border-line transition-colors', sel === it.id ? 'bg-brand-soft/60' : 'hover:bg-paper')}>
                    <span className={clsx('h-6 w-6 rounded-full grid place-items-center shrink-0 transition-colors',
                      d?.status === 'approved' ? 'bg-f-action text-white' : d?.status === 'rejected' ? 'bg-f-approval text-white' : 'border-2 border-line-strong')}>
                      {d?.status === 'approved' && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                      {d?.status === 'rejected' && <X className="h-3.5 w-3.5" strokeWidth={3} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[13.5px] font-semibold truncate">{it.payload.to_name}</span>
                        {edited(it) && <Pencil className="h-3 w-3 text-ink-3 shrink-0" aria-label="Edited" />}
                        {!!it.flags.length && <AlertTriangle className={clsx('h-3.5 w-3.5 shrink-0', it.flags.some(f => f.level === 'error') ? 'text-f-approval' : 'text-f-trigger')} />}
                      </span>
                      <span className="block text-xs text-ink-3 truncate">{d?.subject}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={cur.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -8 }} transition={{ duration: 0.16 }} className="card overflow-hidden">
            <div className="px-5 py-3 border-b border-line flex flex-wrap items-center gap-2">
              <span className="text-2xs font-semibold text-ink-3 tabular">{idx + 1} of {items.length}</span>
              <span className="text-[14px] font-semibold">{cur.payload.to_name}</span>
              {cur.payload.row?.Company && <span className="text-[13px] text-ink-3">· {cur.payload.row.Company}</span>}
              <div className="ml-auto flex gap-2">
                {curDec.status !== 'pending' && !readOnly && <button className="btn-ghost btn-sm" onClick={() => setStatus(cur.id, 'pending', false)}><Undo2 className="h-3.5 w-3.5" />Undo</button>}
                <button className={clsx('btn-sm', curDec.status === 'rejected' ? 'btn bg-f-approval text-white' : 'btn-danger')} disabled={readOnly} onClick={() => setStatus(cur.id, 'rejected')}><X className="h-4 w-4" />Reject</button>
                <button className={clsx('btn-sm', curDec.status === 'approved' ? 'btn bg-f-action text-white' : 'btn-secondary')} disabled={readOnly} onClick={() => setStatus(cur.id, 'approved')}><Check className="h-4 w-4" />Approve</button>
              </div>
            </div>
            {(!!cur.flags.length || cur.note) && (
              <div className={clsx('px-5 py-2.5 border-b border-line text-[13px] space-y-1', errors.length ? 'bg-f-approvalbg/60' : 'bg-f-triggerbg/60')}>
                {cur.flags.map((f, i) => <div key={i} className="flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5" />{f.text}</div>)}
                {cur.note && <div className="text-ink-2">{cur.note}</div>}
              </div>
            )}
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-[64px_1fr] items-center gap-3">
                <label className="text-[12.5px] font-semibold text-ink-3" htmlFor="to">To</label>
                <input id="to" className="input h-9" value={curDec.to} disabled={readOnly} onChange={e => setDecs(d => ({ ...d, [cur.id]: { ...d[cur.id], to: e.target.value } }))} />
                <label className="text-[12.5px] font-semibold text-ink-3" htmlFor="subj">Subject</label>
                <input id="subj" className="input h-9 font-semibold" value={curDec.subject} disabled={readOnly} onChange={e => setDecs(d => ({ ...d, [cur.id]: { ...d[cur.id], subject: e.target.value } }))} />
              </div>
              <textarea aria-label="Email body" className="textarea min-h-[300px] text-[14px]" value={curDec.body} disabled={readOnly}
                onChange={e => setDecs(d => ({ ...d, [cur.id]: { ...d[cur.id], body: e.target.value } }))} />
              {edited(cur) && !readOnly && (
                <button className="text-xs font-semibold text-ink-2 hover:text-ink" onClick={() => setDecs(d => ({ ...d, [cur.id]: { ...d[cur.id], subject: cur.payload.subject, body: cur.payload.body, to: cur.payload.to } }))}>Discard my edits</button>
              )}
              {cur.payload.citations?.map((c, i) => (
                <div key={i} className="rounded-lg border border-line p-3 text-[13px]">
                  <div className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: HEX.knowledge }}><BookOpen className="h-3.5 w-3.5" />Grounded in {c.source_title}{c.section && ` › ${c.section}`}</div>
                  <p className="mt-1 text-ink-2 line-clamp-3">{c.text}</p>
                </div>
              ))}
              {cur.payload.row && Object.keys(cur.payload.row).length > 0 && (
                <div>
                  <button className="flex items-center gap-1 text-xs font-semibold text-ink-2 hover:text-ink" onClick={() => setShowRow(s => !s)} aria-expanded={showRow}>
                    <ChevronDown className={clsx('h-3.5 w-3.5 transition-transform', showRow && 'rotate-180')} />
                    Source data{cur.payload.row_number ? ` · spreadsheet row ${cur.payload.row_number}` : ''}
                  </button>
                  {showRow && (
                    <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs rounded-lg bg-paper p-3">
                      {Object.entries(cur.payload.row).map(([k, v]) => (<div key={k} className="contents"><dt className="text-ink-3">{k}</dt><dd className="text-ink">{v || '—'}</dd></div>))}
                    </dl>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>

      {!readOnly && (
        <div className="fixed bottom-0 left-0 right-0 lg:left-[248px] z-20 bg-surface/95 backdrop-blur border-t border-line">
          <div className="max-w-[1320px] px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-4 text-[13px] tabular">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-f-action" />{counts.approved} approved</span>
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-f-approval" />{counts.rejected} rejected</span>
              <span className="flex items-center gap-1.5 text-ink-3"><span className="h-2.5 w-2.5 rounded-full border-2 border-line-strong" />{counts.pending} to decide</span>
            </div>
            <div className="ml-auto flex gap-2">
              {counts.pending > 0 && <button className="btn-secondary" onClick={approveRemaining}>Approve the other {counts.pending}</button>}
              <button className="btn-primary" disabled={counts.pending > 0 || submitting} onClick={submit}
                title={counts.pending ? 'Decide every draft first' : undefined}>
                {submitting ? <Spinner /> : <Check className="h-4 w-4" />}
                {counts.approved ? `Send ${counts.approved} approved` : 'Submit — send nothing'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
