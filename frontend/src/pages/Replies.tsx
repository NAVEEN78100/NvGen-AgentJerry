import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { Ban, Check, ChevronDown, MailOpen, MessageCircleQuestion, Plane, Send, Sparkles, ThumbsDown, ThumbsUp, Clock, Undo2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { EmptyState, ErrorNote, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { dateTime, timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'

export type ReplyT = {
  id: string; from_email: string; from_name: string; subject: string; body: string; category: string; category_label: string
  confidence: number; summary: string; status: string; suggested_reply: string | null; response_id: string | null
  agent_id: string | null; agent_name: string | null; received_at: string
  original: { id: string; subject: string; body: string; sent_at: string; touch: number } | null
}

export const CAT: Record<string, { cls: string; icon: ReactNode }> = {
  interested: { cls: 'bg-f-actionbg text-f-action', icon: <ThumbsUp className="h-3.5 w-3.5" /> },
  question: { cls: 'bg-f-databg text-f-data', icon: <MessageCircleQuestion className="h-3.5 w-3.5" /> },
  not_now: { cls: 'bg-f-triggerbg text-[#8A5D00]', icon: <Clock className="h-3.5 w-3.5" /> },
  not_interested: { cls: 'bg-ink/[0.06] text-ink-2', icon: <ThumbsDown className="h-3.5 w-3.5" /> },
  unsubscribe: { cls: 'bg-f-approvalbg text-f-approval', icon: <Ban className="h-3.5 w-3.5" /> },
  out_of_office: { cls: 'bg-f-knowledgebg text-f-knowledge', icon: <Plane className="h-3.5 w-3.5" /> },
  other: { cls: 'bg-ink/[0.06] text-ink-2', icon: <MailOpen className="h-3.5 w-3.5" /> },
}

export function CategoryChip({ category, label }: { category: string; label: string }) {
  const c = CAT[category] || CAT.other
  return <span className={clsx('inline-flex items-center gap-1 h-6 px-2 rounded-full text-xs font-semibold whitespace-nowrap', c.cls)}>{c.icon}{label}</span>
}

const FILTERS = [
  ['all', 'All'], ['interested', 'Interested'], ['question', 'Questions'], ['not_now', 'Not now'],
  ['not_interested', 'Not interested'], ['unsubscribe', 'Unsubscribed'], ['out_of_office', 'Out of office'],
] as const

export function Replies() {
  const [sp] = useSearchParams()
  const [cat, setCat] = useState<string>('all')
  const [status, setStatus] = useState<'open' | 'handled'>('open')
  const list = useApi<{ items: ReplyT[]; open_counts: Record<string, number> }>(`/replies?category=${cat}&status=${status}`, { poll: 6000 })
  const [sel, setSel] = useState<string | null>(sp.get('open'))
  const [draft, setDraft] = useState('')
  const [subject, setSubject] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [showOrig, setShowOrig] = useState(false)
  const items = list.data?.items || []
  const cur = items.find(r => r.id === sel) || items[0]
  const counts = list.data?.open_counts || {}
  const totalOpen = Object.values(counts).reduce((a, b) => a + b, 0)

  useEffect(() => {
    if (!cur) return
    setDraft(cur.suggested_reply || '')
    setSubject(cur.original ? (cur.original.subject.startsWith('Re:') ? cur.original.subject : `Re: ${cur.original.subject}`) : cur.subject || 'Re:')
    setShowOrig(false)
  }, [cur?.id]) // eslint-disable-line

  const respond = async () => {
    if (!cur) return
    setBusy('send')
    try { await api(`/replies/${cur.id}/respond`, { body: { subject, body: draft } }); toast.success(`Sent to ${cur.from_name || cur.from_email}`); list.reload() }
    catch (e: any) { toast.error(e.message) } finally { setBusy(null) }
  }
  const mark = async (s: 'open' | 'handled') => {
    if (!cur) return
    setBusy('mark')
    try { await api(`/replies/${cur.id}/status`, { body: { status: s } }); toast(s === 'handled' ? 'Marked as handled' : 'Moved back to open'); list.reload() }
    catch (e: any) { toast.error(e.message) } finally { setBusy(null) }
  }
  const block = async () => {
    if (!cur) return
    setBusy('block')
    try { await api('/suppressions', { body: { emails: cur.from_email, reason: `Added from a reply: ${cur.summary}` } }); toast(`${cur.from_email} won’t be emailed again`) }
    catch (e: any) { toast.error(e.message) } finally { setBusy(null) }
  }

  return (
    <div>
      <PageHeader title="Replies" subtitle="Answers to what your agents sent, sorted by intent. Anyone who replies stops getting follow-ups automatically; anyone who unsubscribes goes straight onto the do-not-contact list." />
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {FILTERS.map(([v, l]) => (
          <button key={v} onClick={() => { setCat(v); setSel(null) }}
            className={clsx('h-8 px-3 rounded-full text-[13px] font-semibold border transition-colors', cat === v ? 'bg-ink text-white border-ink' : 'bg-surface border-line text-ink-2 hover:border-line-strong')}>
            {l}{status === 'open' && (v === 'all' ? totalOpen : counts[v]) ? <span className={clsx('ml-1.5 tabular', cat === v ? 'text-white/70' : 'text-ink-3')}>{v === 'all' ? totalOpen : counts[v]}</span> : null}
          </button>
        ))}
        <div className="ml-auto flex rounded-lg border border-line bg-surface p-0.5">
          {(['open', 'handled'] as const).map(s => (
            <button key={s} onClick={() => { setStatus(s); setSel(null) }} className={clsx('h-7 px-3 rounded-md text-xs font-semibold', status === s ? 'bg-ink/[0.07] text-ink' : 'text-ink-3')}>{s === 'open' ? 'Open' : 'Handled'}</button>
          ))}
        </div>
      </div>
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-96" />}
      {list.data && !items.length && (
        <div className="card"><EmptyState icon={<MailOpen className="h-5 w-5" />} title={status === 'open' ? 'No replies to handle' : 'Nothing handled yet'}
          body="When someone answers an email an agent sent, it lands here, already sorted. In sandbox mode you can simulate a reply from the Outbox."
          action={<Link to="/outbox" className="btn-secondary">Open outbox</Link>} /></div>
      )}
      {!!items.length && cur && (
        <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)] items-start">
          <ul className="card overflow-hidden max-h-[72vh] overflow-y-auto thin-scroll">
            {items.map(r => (
              <li key={r.id}>
                <button onClick={() => setSel(r.id)} className={clsx('w-full text-left px-4 py-3 border-b border-line', cur.id === r.id ? 'bg-brand-soft/60' : 'hover:bg-paper')}>
                  <div className="flex items-center gap-2">
                    <span className="text-[13.5px] font-semibold truncate flex-1">{r.from_name || r.from_email}</span>
                    <span className="text-2xs text-ink-3 whitespace-nowrap">{timeAgo(r.received_at)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2"><CategoryChip category={r.category} label={r.category_label} /><span className="text-xs text-ink-2 truncate">{r.summary}</span></div>
                </button>
              </li>
            ))}
          </ul>

          <AnimatePresence mode="wait">
            <motion.div key={cur.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} className="space-y-4 min-w-0">
              <div className="card p-5">
                <div className="flex flex-wrap items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <h2 className="text-[17px] font-semibold">{cur.from_name || cur.from_email}</h2>
                    <div className="text-[13px] text-ink-2">{cur.from_email} · {dateTime(cur.received_at)}{cur.agent_name && <> · replying to <Link className="font-semibold text-brand hover:underline" to={`/agents/${cur.agent_id}`}>{cur.agent_name}</Link></>}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <CategoryChip category={cur.category} label={cur.category_label} />
                    <span className="text-2xs text-ink-3">{Math.round(cur.confidence * 100)}% confident</span>
                  </div>
                </div>
                <pre className="mt-4 whitespace-pre-wrap font-sans text-[14.5px] leading-relaxed rounded-xl bg-paper border border-line p-4">{cur.body}</pre>
                {cur.category === 'unsubscribe' && <p className="mt-3 text-[13px] text-f-approval flex items-center gap-1.5"><Ban className="h-4 w-4" />Added to the do-not-contact list. No agent will email them again.</p>}
                {cur.category === 'out_of_office' && <p className="mt-3 text-[13px] text-ink-2">Auto-reply. Follow-ups for this person were paused because they replied. Clear their memory entry to resume.</p>}
                {cur.original && (
                  <div className="mt-3">
                    <button className="flex items-center gap-1 text-xs font-semibold text-ink-2 hover:text-ink" onClick={() => setShowOrig(s => !s)} aria-expanded={showOrig}>
                      <ChevronDown className={clsx('h-3.5 w-3.5 transition-transform', showOrig && 'rotate-180')} />
                      Your email{cur.original.touch > 1 ? ` (follow-up #${cur.original.touch})` : ''} · {dateTime(cur.original.sent_at)}
                    </button>
                    {showOrig && <pre className="mt-2 whitespace-pre-wrap font-sans text-[13px] text-ink-2 border-l-2 border-line pl-3">{cur.original.subject}{'\n\n'}{cur.original.body}</pre>}
                  </div>
                )}
              </div>

              {cur.response_id ? (
                <div className="card p-5 flex items-center gap-3 text-[14px]"><Check className="h-4 w-4 text-f-action" />You responded. It’s in the Outbox.</div>
              ) : cur.suggested_reply !== null && cur.category !== 'unsubscribe' ? (
                <div className="card p-5">
                  <div className="flex items-center gap-2 text-[13.5px] font-semibold"><Sparkles className="h-4 w-4 text-brand" />Suggested response <span className="text-xs font-normal text-ink-3">— edit anything, it’s only sent when you click Send</span></div>
                  <input aria-label="Subject" className="input h-9 mt-3 font-semibold" value={subject} onChange={e => setSubject(e.target.value)} />
                  <textarea aria-label="Response" className="textarea mt-2 min-h-[200px]" value={draft} onChange={e => setDraft(e.target.value)} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="btn-primary" onClick={respond} disabled={!!busy || !draft.trim()}>{busy === 'send' ? <Spinner /> : <Send className="h-4 w-4" />}Send response</button>
                    {cur.status === 'open' && <button className="btn-ghost" onClick={() => mark('handled')} disabled={!!busy}>Mark handled without replying</button>}
                  </div>
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                {cur.status === 'handled' && !cur.response_id && <button className="btn-ghost btn-sm" onClick={() => mark('open')} disabled={!!busy}><Undo2 className="h-3.5 w-3.5" />Move back to open</button>}
                {cur.category !== 'unsubscribe' && <button className="btn-ghost btn-sm" onClick={block} disabled={!!busy}><Ban className="h-3.5 w-3.5" />Never email this person again</button>}
                {cur.status === 'open' && (cur.category === 'unsubscribe' || cur.category === 'out_of_office') && <button className="btn-secondary btn-sm" onClick={() => mark('handled')} disabled={!!busy}><Check className="h-3.5 w-3.5" />Mark handled</button>}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}
