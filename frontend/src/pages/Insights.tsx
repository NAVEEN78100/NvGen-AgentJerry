import { BarChart3 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorNote, PageHeader, Skeleton, Stat } from '../components/ui'
import { useApi } from '../lib/hooks'

type M = { sent: number; approved: number; reviewed: number; approval_rate: number | null; edit_rate: number | null; reply_rate: number | null; interested: number; unsubscribed: number; replied: number; followups_sent: number; hours_saved: number }
type Org = { funnel: { stage: string; value: number }[]; agents: { agent: { id: string; name: string; status: string }; metrics: M }[]; weeks: { week: string; sent: number; replies: number }[]; hours_saved: number }

const SENT = '#3B4FB8'
const REPLIES = '#1F9AA8'
const pct = (v: number | null | undefined) => v == null ? '—' : `${Math.round(v * 100)}%`

export function Funnel({ data }: { data: { stage: string; value: number }[] }) {
  const max = Math.max(1, data[0]?.value || 1, ...data.map(d => d.value))
  return (
    <ol className="space-y-2.5" aria-label="Outreach funnel">
      {data.map((d, i) => {
        const prev = i > 0 ? data[i - 1].value : null
        const conv = prev ? Math.round((d.value / prev) * 100) : null
        return (
          <li key={d.stage} className="grid grid-cols-[120px_1fr_auto] sm:grid-cols-[140px_1fr_96px] items-center gap-3">
            <span className="text-[13px] text-ink-2">{d.stage}</span>
            <span className="h-7 rounded-md bg-paper overflow-hidden" title={`${d.stage}: ${d.value}`}>
              <span className="block h-full rounded-r-[4px] transition-[width] duration-700" style={{ width: `${Math.max(d.value ? 2 : 0, (d.value / max) * 100)}%`, background: SENT, opacity: 1 - i * 0.12 }} />
            </span>
            <span className="text-right text-[13px] tabular"><b className="font-semibold">{d.value}</b>{conv != null && <span className="text-ink-3"> · {conv}%</span>}</span>
          </li>
        )
      })}
    </ol>
  )
}

export function WeeklyBars({ weeks }: { weeks: { week: string; sent: number; replies: number }[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [table, setTable] = useState(false)
  const max = Math.max(1, ...weeks.map(w => Math.max(w.sent, w.replies)))
  const H = 140
  const lab = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  return (
    <div>
      <div className="flex items-center justify-end gap-3 text-xs text-ink-2 mb-3">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: SENT }} />Sent</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: REPLIES }} />Replies</span>
        <button className="text-ink-3 hover:text-ink font-semibold" onClick={() => setTable(t => !t)}>{table ? 'Chart' : 'Table'}</button>
      </div>
      {table ? (
        <table className="w-full text-[13px] tabular"><thead><tr className="text-left text-xs text-ink-3"><th className="font-semibold py-1">Week ending</th><th className="font-semibold">Sent</th><th className="font-semibold">Replies</th></tr></thead>
          <tbody>{weeks.map(w => <tr key={w.week} className="border-t border-line"><td className="py-1.5">{lab(w.week)}</td><td>{w.sent}</td><td>{w.replies}</td></tr>)}</tbody></table>
      ) : (
        <>
          <div className="flex items-end gap-2 sm:gap-4" style={{ height: H }} role="img" aria-label={weeks.map(w => `${lab(w.week)}: ${w.sent} sent, ${w.replies} replies`).join('; ')}>
            {weeks.map((w, i) => (
              <div key={w.week} className="relative flex-1 h-full flex items-end justify-center gap-[2px]" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                {[['sent', SENT], ['replies', REPLIES]].map(([k, c]) => {
                  const v = (w as any)[k] as number
                  return <span key={k} className="w-full max-w-[16px] rounded-t-[4px]" style={{ height: v ? Math.max(3, (v / max) * (H - 6)) : 2, background: v ? c : '#E2E4EB', opacity: hover === null || hover === i ? 1 : 0.5 }} />
                })}
                {hover === i && <div className="absolute bottom-full mb-2 z-10 whitespace-nowrap rounded-lg bg-ink text-white text-xs px-2.5 py-1.5 shadow-pop"><div className="font-semibold">Week ending {lab(w.week)}</div><div className="tabular">{w.sent} sent · {w.replies} replies</div></div>}
              </div>
            ))}
          </div>
          <div className="flex gap-2 sm:gap-4 mt-2 border-t border-line pt-1.5">{weeks.map(w => <div key={w.week} className="flex-1 text-center text-2xs text-ink-3">{lab(w.week)}</div>)}</div>
        </>
      )}
    </div>
  )
}

export function Insights() {
  const d = useApi<Org>('/insights', { poll: 15000 })
  if (d.error) return <ErrorNote message={d.error} onRetry={d.reload} />
  if (!d.data) return <div className="space-y-4"><Skeleton className="h-10 w-64" /><Skeleton className="h-64" /></div>
  const f = d.data.funnel
  const sent = f[2].value, replied = f[3].value
  return (
    <div>
      <PageHeader title="Insights" subtitle="What your agents achieved, where people drop off, and which agents need attention." />
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        <Stat label="Emails sent" value={sent} hint="Every one approved by a person" />
        <Stat label="Reply rate" value={sent ? pct(replied / sent) : '—'} hint={`${replied} people replied`} />
        <Stat label="Interested" value={f[4].value} hint="Waiting in Replies" />
        <Stat label="Time saved (est.)" value={`${d.data.hours_saved}h`} hint="Writing emails by hand" />
      </div>
      {!sent ? (
        <div className="card mt-6"><EmptyState icon={<BarChart3 className="h-5 w-5" />} title="No results yet" body="Insights appear after an agent’s first live run. Run one, approve the drafts, then come back." action={<Link to="/agents" className="btn-primary">Go to agents</Link>} /></div>
      ) : (
        <>
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <div className="card p-5"><h2 className="text-[15px] font-semibold mb-4">From draft to interested</h2><Funnel data={f} /><p className="mt-3 text-xs text-ink-3">Percentages compare each stage with the one before.</p></div>
            <div className="card p-5"><h2 className="text-[15px] font-semibold">Sent and replies per week</h2><WeeklyBars weeks={d.data.weeks} /></div>
          </div>
          <div className="card mt-6 overflow-hidden">
            <div className="px-5 h-12 flex items-center border-b border-line"><h2 className="text-[15px] font-semibold">By agent</h2></div>
            <div className="overflow-x-auto thin-scroll">
              <table className="w-full text-[13px] min-w-[760px] tabular">
                <thead className="bg-paper/70 text-left text-xs text-ink-3"><tr>{['Agent', 'Sent', 'Follow-ups', 'Approved as written', 'Edited', 'Reply rate', 'Interested', 'Unsubscribed'].map(h => <th key={h} className="font-semibold px-4 py-2.5 first:pl-5">{h}</th>)}</tr></thead>
                <tbody>
                  {d.data.agents.map(({ agent, metrics: m }) => (
                    <tr key={agent.id} className="border-t border-line hover:bg-paper">
                      <td className="pl-5 pr-4 py-3"><Link to={`/agents/${agent.id}?tab=insights`} className="font-semibold hover:underline">{agent.name}</Link></td>
                      <td className="px-4">{m.sent}</td><td className="px-4">{m.followups_sent}</td>
                      <td className="px-4">{pct(m.approval_rate)}</td><td className="px-4">{pct(m.edit_rate)}</td>
                      <td className="px-4">{pct(m.reply_rate)}</td><td className="px-4">{m.interested}</td>
                      <td className={`px-4 ${m.unsubscribed ? 'text-f-approval font-semibold' : ''}`}>{m.unsubscribed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
