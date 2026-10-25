import { Play } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState, ErrorNote, ModeTag, PageHeader, RunStatusPill, Skeleton, Tabs } from '../components/ui'
import { dateTime, duration } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { RunBrief } from '../lib/types'

export function Runs() {
  const runs = useApi<RunBrief[]>('/runs', { poll: 6000 })
  const [tab, setTab] = useState<'all' | 'live' | 'test'>('all')
  const all = runs.data || []
  const shown = all.filter(r => tab === 'all' || r.mode === tab)
  return (
    <div>
      <PageHeader title="Runs" subtitle="Every execution, step by step. Tests use real data but never send or remember anything." />
      <Tabs value={tab} onChange={setTab} items={[{ value: 'all', label: 'All', count: all.length }, { value: 'live', label: 'Live', count: all.filter(r => r.mode === 'live').length }, { value: 'test', label: 'Tests', count: all.filter(r => r.mode === 'test').length }]} />
      {runs.error && <ErrorNote message={runs.error} onRetry={runs.reload} />}
      {!runs.data && !runs.error && <Skeleton className="h-80" />}
      {runs.data && (
        <div className="card overflow-hidden">
          {!shown.length && <EmptyState icon={<Play className="h-5 w-5" />} title="No runs yet" body="Runs appear here as soon as an agent is tested or runs live." />}
          <div className="overflow-x-auto thin-scroll">
            <table className="w-full text-[13px] min-w-[720px]">
              {!!shown.length && <thead className="bg-paper/70 text-left text-xs text-ink-3"><tr><th className="font-semibold px-5 py-2.5">Agent</th><th className="font-semibold">Mode</th><th className="font-semibold">Result</th><th className="font-semibold">Started</th><th className="font-semibold">Took</th><th className="font-semibold pr-5">Status</th></tr></thead>}
              <tbody>
                {shown.map(r => {
                  const took = r.finished_at ? new Date(r.finished_at).getTime() - new Date(r.started_at).getTime() : null
                  return (
                    <tr key={r.id} className="border-t border-line hover:bg-paper">
                      <td className="px-5 py-3"><Link to={`/agents/${r.agent_id}/runs/${r.id}`} className="font-semibold hover:underline">{r.agent_name}</Link></td>
                      <td><ModeTag mode={r.mode} /></td>
                      <td className="text-ink-2 max-w-[360px] truncate pr-4">{r.status === 'awaiting_approval' ? 'Waiting for your approval' : r.summary?.headline || r.error || '—'}</td>
                      <td className="text-ink-2 whitespace-nowrap">{dateTime(r.started_at)}</td>
                      <td className="text-ink-3 tabular whitespace-nowrap">{took != null && r.status !== 'cancelled' ? duration(took) : '—'}</td>
                      <td className="pr-5"><RunStatusPill status={r.status} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
