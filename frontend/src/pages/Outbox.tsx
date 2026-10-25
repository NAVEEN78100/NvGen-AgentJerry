import { Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorNote, PageHeader, Skeleton } from '../components/ui'
import { dateTime } from '../lib/format'
import { useApi } from '../lib/hooks'

type Msg = { id: string; agent_id: string; agent_name: string; execution_id: string; to: string; to_name: string; subject: string; body: string; transport: string; sent_at: string }

export function Outbox() {
  const list = useApi<Msg[]>('/outbox', { poll: 8000 })
  const [sel, setSel] = useState<string | null>(null)
  const cur = list.data?.find(m => m.id === sel) || list.data?.[0]
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
                  <div className="flex items-center gap-2"><span className="text-[13.5px] font-semibold truncate flex-1">{m.to_name}</span><span className="text-2xs text-ink-3 whitespace-nowrap">{dateTime(m.sent_at)}</span></div>
                  <div className="text-xs text-ink-2 truncate">{m.subject}</div>
                </button>
              </li>
            ))}
          </ul>
          <article className="card overflow-hidden">
            <header className="px-5 py-4 border-b border-line">
              <h2 className="text-[17px] font-semibold">{cur.subject}</h2>
              <div className="mt-1 text-[13px] text-ink-2">To <b className="text-ink font-semibold">{cur.to_name}</b> &lt;{cur.to}&gt; · {dateTime(cur.sent_at)}</div>
              <div className="mt-1.5 flex flex-wrap gap-2 text-xs">
                <span className="h-5 px-1.5 rounded bg-paper border border-line font-semibold inline-flex items-center">{cur.transport === 'smtp' ? 'Delivered via SMTP' : 'Sandbox delivery'}</span>
                <Link to={`/agents/${cur.agent_id}/runs/${cur.execution_id}`} className="font-semibold text-brand hover:underline">From {cur.agent_name}</Link>
              </div>
            </header>
            <pre className="px-5 py-4 whitespace-pre-wrap font-sans text-[14px] leading-relaxed">{cur.body}</pre>
          </article>
        </div>
      )}
    </div>
  )
}
