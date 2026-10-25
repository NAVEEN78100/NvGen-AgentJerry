import { Bot, FileSpreadsheet, Plus, Radio, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AgentStatusPill, DeptTag, EmptyState, ErrorNote, PageHeader, RunStatusPill, Skeleton, Tabs } from '../components/ui'
import { timeAgo, untilLabel } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { AgentBrief } from '../lib/types'

export function Agents() {
  const list = useApi<AgentBrief[]>('/agents', { poll: 10000 })
  const [tab, setTab] = useState<'all' | 'live' | 'building'>('all')
  const all = list.data || []
  const shown = all.filter(a => tab === 'all' || (tab === 'live' ? ['deployed', 'paused'].includes(a.status) : ['draft', 'ready', 'tested'].includes(a.status)))
  return (
    <div>
      <PageHeader title="Agents" subtitle="Every agent was described in plain words, tested safely, and only then taken live."
        actions={<Link to="/studio" className="btn-primary"><Plus className="h-4 w-4" />Create agent</Link>} />
      <Tabs value={tab} onChange={setTab} items={[
        { value: 'all', label: 'All', count: all.length },
        { value: 'live', label: 'Live & paused', count: all.filter(a => ['deployed', 'paused'].includes(a.status)).length },
        { value: 'building', label: 'Being built', count: all.filter(a => ['draft', 'ready', 'tested'].includes(a.status)).length },
      ]} />
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-44" />)}</div>}
      {list.data && !shown.length && (
        <div className="card"><EmptyState icon={<Bot className="h-5 w-5" />} title={tab === 'all' ? 'No agents yet' : 'Nothing here'}
          body="Describe a task you repeat, and Jerry will build, test and safety-check the agent for you." action={<Link to="/studio" className="btn-primary">Create an agent</Link>} /></div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {shown.map(a => (
          <Link key={a.id} to={a.status === 'draft' ? `/studio/${a.id}` : `/agents/${a.id}`} className="card p-5 hover:shadow-pop hover:border-line-strong transition-all flex flex-col">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <DeptTag dept={a.department} />
                <h2 className="text-[17px] font-semibold leading-snug">{a.name}</h2>
              </div>
              <AgentStatusPill status={a.status} />
            </div>
            <p className="mt-2 text-[13px] text-ink-2 line-clamp-2">{a.goal || 'Still needs a few details.'}</p>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
              <span className="flex items-center gap-1.5"><Radio className="h-3.5 w-3.5 text-f-trigger" />{a.status === 'deployed' && a.next_run ? `Next ${untilLabel(a.next_run)}` : a.trigger_label}</span>
              {a.source_file && <span className="flex items-center gap-1.5"><FileSpreadsheet className="h-3.5 w-3.5 text-f-data" />{a.source_file}</span>}
              {a.approval_required && <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5 text-f-approval" />Approval required</span>}
            </div>
            <div className="mt-auto pt-4 flex items-center gap-3 text-xs text-ink-3 border-t border-line mt-4">
              <span className="tabular">{a.stats.emails_sent ?? 0} sent</span>
              <span className="tabular">{a.stats.memory ?? 0} remembered</span>
              {!!a.stats.pending_approvals && <span className="text-f-approval font-semibold">{a.stats.pending_approvals} awaiting approval</span>}
              <span className="ml-auto flex items-center gap-2">{a.stats.last_run ? <>{timeAgo(a.stats.last_run.started_at)} <RunStatusPill status={a.stats.last_run.status} /></> : 'Never run'}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
