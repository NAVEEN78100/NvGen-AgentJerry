import { motion } from 'framer-motion'
import { ArrowRight, Bot, Hourglass, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AgentStatusPill, EmptyState, ErrorNote, ModeTag, RunStatusPill, Skeleton, Stat } from '../components/ui'
import { useAuth } from '../lib/auth'
import { timeAgo, untilLabel } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { AgentBrief, Approval, RunBrief } from '../lib/types'

interface Dash {
  kpis: { agents_live: number; agents_total: number; runs_7d: number; tests_7d: number; emails_sent: number; pending_approvals: number; hours_saved: number; minutes_per_item: number }
  days: { date: string; test: number; live: number }[]
  pending: Approval[]; recent_runs: RunBrief[]; agents: AgentBrief[]
  activity: { id: number; actor: string; action: string; detail: string; at: string }[]
}

const LIVE = '#3B4FB8'
const TEST = '#1F9AA8'

function RunsChart({ days }: { days: Dash['days'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [table, setTable] = useState(false)
  const max = Math.max(1, ...days.map(d => d.live + d.test))
  const H = 140
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold">Runs in the last 7 days</h2>
        <div className="flex items-center gap-3 text-xs text-ink-2">
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: LIVE }} />Live</span>
          <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: TEST }} />Test</span>
          <button className="text-ink-3 hover:text-ink font-semibold" onClick={() => setTable(t => !t)}>{table ? 'Chart' : 'Table'}</button>
        </div>
      </div>
      {table ? (
        <table className="mt-4 w-full text-[13px] tabular">
          <thead><tr className="text-left text-ink-3 text-xs"><th className="font-semibold py-1">Day</th><th className="font-semibold">Live</th><th className="font-semibold">Test</th></tr></thead>
          <tbody>{days.map(d => <tr key={d.date} className="border-t border-line"><td className="py-1.5">{new Date(d.date).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}</td><td>{d.live}</td><td>{d.test}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="relative mt-4">
          <div className="flex items-end gap-2 sm:gap-3" style={{ height: H }} role="img" aria-label={`Runs per day: ${days.map(d => `${d.date} ${d.live} live ${d.test} test`).join(', ')}`}>
            {days.map((d, i) => {
              const lh = (d.live / max) * (H - 8), th = (d.test / max) * (H - 8)
              return (
                <div key={d.date} className="flex-1 h-full flex flex-col justify-end items-center relative cursor-default" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <div className="w-full max-w-[34px] flex flex-col justify-end gap-[2px] h-full">
                    {d.test > 0 && <motion.div initial={{ height: 0 }} animate={{ height: th }} transition={{ delay: 0.04 * i }} className="w-full rounded-t-[4px]" style={{ background: TEST, opacity: hover === null || hover === i ? 1 : 0.5 }} />}
                    {d.live > 0 && <motion.div initial={{ height: 0 }} animate={{ height: lh }} transition={{ delay: 0.04 * i }} className={d.test > 0 ? 'w-full' : 'w-full rounded-t-[4px]'} style={{ background: LIVE, opacity: hover === null || hover === i ? 1 : 0.5 }} />}
                    {d.live + d.test === 0 && <div className="w-full h-[2px] rounded bg-line" />}
                  </div>
                  {hover === i && (
                    <div className="absolute bottom-full mb-2 z-10 whitespace-nowrap rounded-lg bg-ink text-white text-xs px-2.5 py-1.5 shadow-pop">
                      <div className="font-semibold">{new Date(d.date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })}</div>
                      <div className="tabular">{d.live} live · {d.test} test</div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <div className="flex gap-2 sm:gap-3 mt-2 border-t border-line pt-1.5">
            {days.map(d => <div key={d.date} className="flex-1 text-center text-2xs text-ink-3">{new Date(d.date).toLocaleDateString(undefined, { weekday: 'short' })}</div>)}
          </div>
        </div>
      )}
    </div>
  )
}

export function Home() {
  const { user } = useAuth()
  const nav = useNavigate()
  const d = useApi<Dash>('/dashboard', { poll: 8000 })
  const [q, setQ] = useState('')
  const hour = new Date().getHours()
  const greet = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  if (d.error) return <ErrorNote message={d.error} onRetry={d.reload} />
  const k = d.data?.kpis

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-[28px] font-semibold">{greet}, {user?.name.split(' ')[0]}</h1>
          <p className="mt-1 text-ink-2">{k ? (k.pending_approvals ? `${k.pending_approvals} ${k.pending_approvals === 1 ? 'batch is' : 'batches are'} waiting for your approval.` : 'Nothing needs you right now.') : ' '}</p>
        </div>
        <form className="w-full sm:w-auto sm:min-w-[420px] card flex items-center gap-2 p-1.5 pl-3" onSubmit={e => { e.preventDefault(); nav('/studio', { state: { prompt: q } }) }}>
          <Sparkles className="h-4 w-4 text-ink-3 shrink-0" />
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Describe a new task to automate…" aria-label="Describe a new task" className="flex-1 bg-transparent text-[14px] focus:outline-none placeholder:text-ink-3 h-9 min-w-0" />
          <button className="btn-primary h-9">Build</button>
        </form>
      </div>

      {!!d.data?.pending.length && (
        <div className="mb-6 space-y-2">
          {d.data.pending.map(p => (
            <Link key={p.id} to={`/approvals/${p.id}`} className="flex items-center gap-4 card px-4 py-3 border-f-approval/35 hover:shadow-pop transition-shadow group">
              <span className="h-9 w-9 rounded-xl grid place-items-center bg-f-approvalbg text-f-approval shrink-0"><Hourglass className="h-4 w-4" /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[14px] font-semibold truncate">{p.title}</span>
                <span className="block text-xs text-ink-2">Waiting since {timeAgo(p.created_at)} · nothing is sent until you decide{p.counts.flagged ? ` · ${p.counts.flagged} flagged by the safety check` : ''}</span>
              </span>
              <span className="btn-primary btn-sm">Review <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" /></span>
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        {k ? (<>
          <Stat label="Live agents" value={k.agents_live} hint={`${k.agents_total} ${k.agents_total === 1 ? 'agent' : 'agents'} in total`} />
          <Stat label="Live runs this week" value={k.runs_7d} hint={`${k.tests_7d} safe ${k.tests_7d === 1 ? 'test' : 'tests'} too`} />
          <Stat label="Emails sent" value={k.emails_sent} hint="All approved by a person" />
          <Stat label="Time saved (est.)" value={`${k.hours_saved}h`} hint={`At ${k.minutes_per_item} min per email written by hand`} />
        </>) : [0, 1, 2, 3].map(i => <Skeleton key={i} className="h-[108px]" />)}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-6 min-w-0">
          {d.data ? <RunsChart days={d.data.days} /> : <Skeleton className="h-[230px]" />}
          <div className="card">
            <div className="px-5 h-12 flex items-center justify-between border-b border-line">
              <h2 className="text-[15px] font-semibold">Recent runs</h2>
              <Link to="/runs" className="text-xs font-semibold text-brand hover:underline">All runs</Link>
            </div>
            {d.data && !d.data.recent_runs.length && <div className="p-6 text-[13px] text-ink-3 text-center">No runs yet. Build an agent and run a test.</div>}
            <ul>
              {d.data?.recent_runs.map(r => (
                <li key={r.id}>
                  <Link to={`/agents/${r.agent_id}/runs/${r.id}`} className="flex items-center gap-3 px-5 py-3 border-b border-line last:border-0 hover:bg-paper">
                    <ModeTag mode={r.mode} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13.5px] font-semibold truncate">{r.agent_name}</span>
                      <span className="block text-xs text-ink-2 truncate">{r.status === 'awaiting_approval' ? 'Waiting for your approval — nothing sent yet' : r.summary?.headline || r.error || 'In progress'}</span>
                    </span>
                    <span className="hidden sm:block text-xs text-ink-3 whitespace-nowrap">{timeAgo(r.started_at)}</span>
                    <RunStatusPill status={r.status} />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="space-y-6 min-w-0">
          <div className="card">
            <div className="px-5 h-12 flex items-center justify-between border-b border-line">
              <h2 className="text-[15px] font-semibold">Your agents</h2>
              <Link to="/agents" className="text-xs font-semibold text-brand hover:underline">All agents</Link>
            </div>
            {d.data && !d.data.agents.length && <EmptyState icon={<Bot className="h-5 w-5" />} title="No agents yet" body="Describe a task you repeat every week and Jerry builds the agent." action={<Link to="/studio" className="btn-primary">Create an agent</Link>} />}
            <ul>
              {d.data?.agents.map(a => (
                <li key={a.id}>
                  <Link to={`/agents/${a.id}`} className="block px-5 py-3 border-b border-line last:border-0 hover:bg-paper">
                    <div className="flex items-center gap-2"><span className="text-[13.5px] font-semibold truncate flex-1">{a.name}</span><AgentStatusPill status={a.status} size="sm" /></div>
                    <div className="mt-0.5 text-xs text-ink-2 truncate">{a.status === 'deployed' && a.next_run ? `Next run ${untilLabel(a.next_run)}` : a.trigger_label}</div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="card">
            <div className="px-5 h-12 flex items-center justify-between border-b border-line">
              <h2 className="text-[15px] font-semibold">Activity</h2>
              <Link to="/activity" className="text-xs font-semibold text-brand hover:underline">Full log</Link>
            </div>
            <ul className="px-5 py-2">
              {d.data?.activity.map(e => (
                <li key={e.id} className="py-2 flex gap-3 text-[13px]">
                  <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-ink-3 shrink-0" />
                  <span className="min-w-0 flex-1"><b className="font-semibold">{e.actor}</b> <span className="text-ink-2">{e.detail}</span></span>
                  <span className="text-2xs text-ink-3 whitespace-nowrap">{timeAgo(e.at)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
