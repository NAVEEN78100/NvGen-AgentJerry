import { Activity as Icon } from 'lucide-react'
import { EmptyState, ErrorNote, PageHeader, Skeleton } from '../components/ui'
import { dateTime } from '../lib/format'
import { useApi } from '../lib/hooks'

type Ev = { id: number; actor: string; action: string; entity_type: string; detail: string; at: string }

const GROUP: Record<string, string> = { agent: 'Agent', run: 'Run', approval: 'Approval', email: 'Email', file: 'File', knowledge: 'Knowledge', memory: 'Memory', settings: 'Settings', auth: 'Sign-in' }

export function Activity() {
  const list = useApi<Ev[]>('/activity', { poll: 10000 })
  let lastDay = ''
  return (
    <div>
      <PageHeader title="Activity log" subtitle="An audit trail of every decision: who built, tested, approved and sent what, and when." />
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-96" />}
      {list.data && !list.data.length && <div className="card"><EmptyState icon={<Icon className="h-5 w-5" />} title="No activity yet" body="Actions appear here as soon as they happen." /></div>}
      {!!list.data?.length && (
        <div className="card p-5">
          <ol className="space-y-0">
            {list.data.map(e => {
              const day = new Date(e.at).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
              const header = day !== lastDay ? (lastDay = day) : null
              return (
                <li key={e.id}>
                  {header && <div className="text-xs font-semibold text-ink-3 pt-3 pb-2 first:pt-0">{header}</div>}
                  <div className="flex gap-4 py-2 border-b border-line last:border-0 text-[13px]">
                    <span className="w-16 shrink-0 text-ink-3 tabular">{new Date(e.at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</span>
                    <span className="w-20 shrink-0 text-2xs font-semibold text-ink-3 pt-0.5">{GROUP[e.action.split('.')[0]] || e.entity_type}</span>
                    <span className="min-w-0 flex-1"><b className="font-semibold">{e.actor}</b> <span className="text-ink-2">{e.detail}</span></span>
                    <span className="hidden md:block text-2xs text-ink-3 whitespace-nowrap">{dateTime(e.at)}</span>
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </div>
  )
}
