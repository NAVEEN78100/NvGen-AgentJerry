import { ArrowRight, Check, Hourglass, Inbox } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorNote, PageHeader, Skeleton, Tabs } from '../components/ui'
import { dateTime, timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { Approval } from '../lib/types'

export function Approvals() {
  const [tab, setTab] = useState<'pending' | 'decided'>('pending')
  const list = useApi<Approval[]>(`/approvals?status=${tab}`, { poll: 5000 })
  return (
    <div>
      <PageHeader title="Approvals" subtitle="Anything that leaves your company waits here for a person. Nothing is sent until you decide." />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'pending', label: 'Waiting for you' }, { value: 'decided', label: 'Decided' }]} />
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-48" />}
      {list.data && !list.data.length && (
        <div className="card"><EmptyState icon={tab === 'pending' ? <Inbox className="h-5 w-5" /> : <Check className="h-5 w-5" />}
          title={tab === 'pending' ? 'Nothing waiting' : 'No decisions yet'}
          body={tab === 'pending' ? 'When an agent drafts emails, they land here for your review.' : 'Approvals you’ve decided appear here with who decided and when.'} /></div>
      )}
      <div className="space-y-3">
        {list.data?.map(a => (
          <Link key={a.id} to={`/approvals/${a.id}`} className="card p-4 flex flex-wrap items-center gap-4 hover:shadow-pop transition-shadow group">
            <span className={`h-10 w-10 rounded-xl grid place-items-center shrink-0 ${tab === 'pending' ? 'bg-f-approvalbg text-f-approval' : 'bg-f-actionbg text-f-action'}`}>{tab === 'pending' ? <Hourglass className="h-4 w-4" /> : <Check className="h-4 w-4" />}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[14.5px] font-semibold">{a.title}</div>
              <div className="text-xs text-ink-2 mt-0.5">
                {tab === 'pending' ? `Waiting since ${timeAgo(a.created_at)}` : a.status === 'expired' ? 'Expired — the run was cancelled' : `${a.decided_by} decided ${dateTime(a.decided_at)}`}
                {tab === 'decided' && a.status !== 'expired' && ` · ${a.counts.approved} approved, ${a.counts.rejected} rejected`}
                {tab === 'pending' && !!a.counts.flagged && ` · ${a.counts.flagged} flagged`}
                {tab === 'pending' && a.assigned_to && ` · ${a.can_decide ? 'assigned to you' : `waiting for ${a.assigned_to.name}`}`}
              </div>
            </div>
            <span className={tab === 'pending' && a.can_decide ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}>{tab === 'pending' && a.can_decide ? 'Review' : 'View'}<ArrowRight className="h-3.5 w-3.5" /></span>
          </Link>
        ))}
      </div>
    </div>
  )
}
