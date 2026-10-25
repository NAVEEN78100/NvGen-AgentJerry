import { MessageSquareReply, Send } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { EmptyState, ErrorNote, Modal, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { dateTime } from '../lib/format'
import { useApi } from '../lib/hooks'
import { CategoryChip } from './Replies'

type Msg = {
  id: string; agent_id: string; agent_name: string; execution_id: string; to: string; to_name: string; subject: string; body: string
  transport: string; sent_at: string; touch: number; replied_at: string | null; reply_category: string | null
}

const LABEL: Record<string, string> = { interested: 'Interested', question: 'Has a question', not_now: 'Not right now', not_interested: 'Not interested', unsubscribe: 'Unsubscribe', out_of_office: 'Out of office', other: 'Replied' }

const SAMPLES = [
  ['Interested', 'Thanks for reaching out — this sounds useful. Happy to set up a call next week.'],
  ['Question', 'How long does it usually take to get set up, and does it work with Tally?'],
  ['Not now', 'Not right now, we are busy until after Diwali. Please reach out next quarter.'],
  ['Not interested', 'No thanks, we already use another tool for this.'],
  ['Unsubscribe', 'Please remove me from your mailing list.'],
  ['Out of office', 'I am out of office until Monday with limited access to email.'],
]

export function Outbox() {
  const list = useApi<Msg[]>('/outbox', { poll: 8000 })
  const nav = useNavigate()
  const [sel, setSel] = useState<string | null>(null)
  const [sim, setSim] = useState(false)
  const [text, setText] = useState(SAMPLES[0][1])
  const [busy, setBusy] = useState(false)
  const cur = list.data?.find(m => m.id === sel) || list.data?.[0]

  const simulate = async () => {
    if (!cur) return
    setBusy(true)
    try {
      const r = await api(`/outbox/${cur.id}/reply`, { body: { body: text } })
      setSim(false); list.reload()
      toast.success(`Reply recorded — sorted as “${r.category_label}”`, { action: { label: 'Open', onClick: () => nav(`/replies?open=${r.id}`) } })
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Outbox" subtitle="Every email agents have sent, exactly as approved. In sandbox mode nothing leaves this machine — connect SMTP in Settings to deliver for real." />
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-96" />}
      {list.data && !list.data.length && <div className="card"><EmptyState icon={<Send className="h-5 w-5" />} title="No emails sent yet" body="Approved emails from live runs appear here." /></div>}
      {!!list.data?.length && cur && (
        <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)] items-start">
          <ul className="card overflow-hidden max-h-[70vh] overflow-y-auto thin-scroll">
            {list.data.map(m => (
              <li key={m.id}>
                <button onClick={() => setSel(m.id)} className={`w-full text-left px-4 py-3 border-b border-line ${cur.id === m.id ? 'bg-brand-soft/60' : 'hover:bg-paper'}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-[13.5px] font-semibold truncate flex-1">{m.to_name}</span>
                    {m.touch > 1 && <span className="text-2xs font-semibold text-f-memory bg-f-memorybg h-5 px-1.5 rounded inline-flex items-center">Follow-up #{m.touch}</span>}
                    {m.touch === 0 && <span className="text-2xs font-semibold text-brand bg-brand-soft h-5 px-1.5 rounded inline-flex items-center">Your reply</span>}
                    <span className="text-2xs text-ink-3 whitespace-nowrap">{dateTime(m.sent_at)}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-ink-2 truncate flex-1">{m.subject}</span>
                    {m.reply_category && <span className="h-2 w-2 rounded-full bg-f-action shrink-0" title="Replied" />}
                  </div>
                </button>
              </li>
            ))}
          </ul>
          <article className="card overflow-hidden">
            <header className="px-5 py-4 border-b border-line">
              <div className="flex flex-wrap items-start gap-3">
                <h2 className="text-[17px] font-semibold flex-1 min-w-0">{cur.subject}</h2>
                {cur.touch > 0 && (cur.reply_category
                  ? <CategoryChip category={cur.reply_category} label={LABEL[cur.reply_category] || 'Replied'} />
                  : <button className="btn-secondary btn-sm" onClick={() => { setText(SAMPLES[0][1]); setSim(true) }}><MessageSquareReply className="h-4 w-4" />Simulate a reply</button>)}
              </div>
              <div className="mt-1 text-[13px] text-ink-2">To <b className="text-ink font-semibold">{cur.to_name}</b> &lt;{cur.to}&gt; · {dateTime(cur.sent_at)}</div>
              <div className="mt-1.5 flex flex-wrap gap-2 text-xs">
                <span className="h-5 px-1.5 rounded bg-paper border border-line font-semibold inline-flex items-center">{cur.transport === 'smtp' ? 'Delivered via SMTP' : 'Sandbox delivery'}</span>
                {cur.execution_id !== 'manual' && cur.agent_name && <Link to={`/agents/${cur.agent_id}/runs/${cur.execution_id}`} className="font-semibold text-brand hover:underline">From {cur.agent_name}</Link>}
                {cur.reply_category && <Link to="/replies" className="font-semibold text-brand hover:underline">See the reply</Link>}
              </div>
            </header>
            <pre className="px-5 py-4 whitespace-pre-wrap font-sans text-[14px] leading-relaxed">{cur.body}</pre>
          </article>
        </div>
      )}
      <Modal open={sim} onClose={() => setSim(false)} title={`Simulate a reply from ${cur?.to_name || ''}`}
        footer={<><button className="btn-ghost" onClick={() => setSim(false)}>Cancel</button><button className="btn-primary" onClick={simulate} disabled={busy || !text.trim()}>{busy && <Spinner />}Record reply</button></>}>
        <p className="text-[13px] text-ink-2">Sandbox only. In production, replies arrive through the inbound-email webhook in Settings.</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {SAMPLES.map(([l, t]) => <button key={l} onClick={() => setText(t)} className={`h-7 px-2.5 rounded-full text-xs font-semibold border ${text === t ? 'bg-ink text-white border-ink' : 'border-line hover:border-line-strong'}`}>{l}</button>)}
        </div>
        <textarea aria-label="Reply text" className="textarea mt-3 min-h-[120px]" value={text} onChange={e => setText(e.target.value)} />
      </Modal>
    </div>
  )
}
