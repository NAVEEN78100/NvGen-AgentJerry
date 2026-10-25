import { ArrowLeft, Brain, FlaskConical, Pause, Pencil, Play, Radio, Trash2, UserCheck, X } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AnnotatedText, FieldSwatch } from '../components/Annotated'
import { ValidationBadge, ValidationList } from '../components/Validation'
import { WorkflowGraph, WorkflowList } from '../components/WorkflowGraph'
import { AgentStatusPill, EmptyState, ErrorNote, Modal, ModeTag, RunStatusPill, Skeleton, Spinner, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { dateTime, timeAgo, untilLabel } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { Agent, RunBrief } from '../lib/types'

type Mem = { id: number; namespace: string; key: string; value: Record<string, any>; updated_at: string }

export function AgentDetail() {
  const { agentId } = useParams()
  const nav = useNavigate()
  const ag = useApi<Agent>(`/agents/${agentId}`, { poll: 8000 })
  const runs = useApi<RunBrief[]>(`/agents/${agentId}/runs`, { poll: 8000 })
  const mem = useApi<Mem[]>(`/agents/${agentId}/memory`)
  const versions = useApi<{ version: number; steps: number; status: string; created_at: string; tested: boolean }[]>(`/agents/${agentId}/versions`)
  const [sp] = useSearchParams()
  const [tab, setTab] = useState<'overview' | 'runs' | 'memory' | 'versions'>((sp.get('tab') as any) || 'overview')
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const a = ag.data

  const act = async (kind: 'test' | 'live' | 'deploy' | 'pause') => {
    setBusy(kind)
    try {
      if (kind === 'test' || kind === 'live') {
        const r = await api(`/agents/${agentId}/runs`, { body: { mode: kind } })
        nav(`/agents/${agentId}/runs/${r.id}`)
        return
      }
      const n = await api<Agent>(`/agents/${agentId}/${kind}`, { method: 'POST' })
      ag.setData(n)
      toast.success(kind === 'deploy' ? `${n.name} is live` : `${n.name} is paused`)
    } catch (e: any) { toast.error(e.message) } finally { setBusy(null) }
  }
  const forget = async (id: number) => {
    try { await api(`/agents/${agentId}/memory/${id}`, { method: 'DELETE' }); mem.reload(); toast('Forgotten — they’ll be included next run') } catch (e: any) { toast.error(e.message) }
  }
  const clearMem = async () => {
    try { const r = await api(`/agents/${agentId}/memory`, { method: 'DELETE' }); mem.reload(); setConfirmClear(false); toast(`Cleared ${r.cleared} entries`) } catch (e: any) { toast.error(e.message) }
  }
  const remove = async () => {
    try { await api(`/agents/${agentId}`, { method: 'DELETE' }); toast('Agent deleted'); nav('/agents') } catch (e: any) { toast.error(e.message) }
  }

  if (ag.error) return <ErrorNote message={ag.error} onRetry={ag.reload} />
  if (!a) return <div className="space-y-3"><Skeleton className="h-8 w-80" /><Skeleton className="h-5 w-[480px]" /><Skeleton className="h-[480px]" /></div>
  const wf = a.workflow
  const prompt = a.conversation.find(m => m.kind === 'prompt')
  const live = a.status === 'deployed'

  return (
    <div>
      <Link to="/agents" className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-2 hover:text-ink mb-3"><ArrowLeft className="h-4 w-4" />Agents</Link>
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3"><h1 className="text-[28px] font-semibold leading-tight">{a.name}</h1><AgentStatusPill status={a.status} /></div>
          <p className="mt-1.5 text-ink-2 max-w-[78ch]">{a.goal}</p>
          <div className="flex flex-wrap items-center gap-x-5"><ApproverPicker agent={a} onChange={n => ag.setData(n)} />
          <p className="mt-2 text-[13px] text-ink-2 flex items-center gap-1.5">
            <Radio className="h-3.5 w-3.5 text-f-trigger" />
            {live && a.next_run ? <>Next run <b className="text-ink font-semibold">{untilLabel(a.next_run)}</b></> : a.trigger_label}
            {a.status === 'paused' && <span className="text-ink-3">· schedule is off</span>}
          </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/studio/${a.id}`} className="btn-ghost"><Pencil className="h-4 w-4" />Edit</Link>
          <button className="btn-secondary" onClick={() => act('test')} disabled={!!busy || !wf?.validation.valid}>{busy === 'test' ? <Spinner /> : <FlaskConical className="h-4 w-4" />}Test</button>
          {a.can_run_live && <button className="btn-secondary" onClick={() => act('live')} disabled={!!busy}>{busy === 'live' ? <Spinner /> : <Play className="h-4 w-4" />}Run now</button>}
          {live ? <button className="btn-secondary" onClick={() => act('pause')} disabled={!!busy}>{busy === 'pause' ? <Spinner /> : <Pause className="h-4 w-4" />}Pause</button>
            : <button className="btn-primary" onClick={() => act('deploy')} disabled={!!busy || !a.can_deploy}
              title={a.can_deploy ? undefined : 'Pass a test of the latest version first'}>{busy === 'deploy' ? <Spinner /> : <Radio className="h-4 w-4" />}{a.status === 'paused' ? 'Resume' : 'Go live'}</button>}
        </div>
      </div>
      {!a.can_deploy && !live && a.status !== 'draft' && <p className="mt-3 text-xs text-ink-3">Going live unlocks after a passing test of version {wf?.version}.</p>}
      {a.status === 'draft' && <div className="mt-4"><ErrorNote message="This agent still needs a few details before it can be built." onRetry={() => nav(`/studio/${a.id}`)} /></div>}

      <div className="mt-6">
        <Tabs value={tab} onChange={setTab} items={[
          { value: 'overview', label: 'Overview' },
          { value: 'runs', label: 'Runs', count: runs.data?.length },
          { value: 'memory', label: 'Memory', count: mem.data?.length },
          { value: 'versions', label: 'Versions', count: versions.data?.length },
        ]} />
      </div>

      {tab === 'overview' && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] items-start">
          <div className="space-y-6 min-w-0">
            {prompt && (
              <div className="card p-5">
                <div className="text-2xs font-semibold text-ink-3 mb-1.5">Described as</div>
                <AnnotatedText text={prompt.text} spans={prompt.spans || []} size="md" animate={false} />
              </div>
            )}
            <div className="card divide-y divide-line">
              {a.fields.map(f => (
                <div key={f.label} className="flex items-start gap-3 px-5 py-3">
                  <span className="mt-1.5"><FieldSwatch field={f.field} /></span>
                  <span className="w-[140px] shrink-0 text-[12.5px] font-semibold text-ink-2">{f.label}</span>
                  <span className="text-[13.5px] min-w-0">{f.value || '—'}</span>
                </div>
              ))}
            </div>
            {wf && (
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4"><h2 className="text-[15px] font-semibold">Validation · version {wf.version}</h2><ValidationBadge validation={wf.validation} /></div>
                <ValidationList validation={wf.validation} />
              </div>
            )}
          </div>
          {wf && (
            <div className="card overflow-hidden min-w-0">
              <div className="px-5 h-12 flex items-center border-b border-line"><h2 className="text-[15px] font-semibold">Workflow</h2><span className="ml-2 text-xs text-ink-3">{wf.steps.length} steps</span></div>
              <div className="hidden md:block bg-paper/60"><WorkflowGraph steps={wf.steps} height={wf.steps.length * 104 + 24} /></div>
              <div className="md:hidden p-4"><WorkflowList steps={wf.steps} /></div>
            </div>
          )}
        </div>
      )}

      {tab === 'runs' && (
        <div className="card overflow-hidden">
          {runs.data && !runs.data.length && <EmptyState icon={<Play className="h-5 w-5" />} title="No runs yet" body="Run a safe test to see every step with real data — nothing is sent." action={<button className="btn-primary" onClick={() => act('test')}>Run a test</button>} />}
          <ul>
            {runs.data?.map(r => (
              <li key={r.id}>
                <Link to={`/agents/${a.id}/runs/${r.id}`} className="flex items-center gap-3 px-5 py-3 border-b border-line last:border-0 hover:bg-paper">
                  <ModeTag mode={r.mode} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13.5px] font-medium truncate">{r.status === 'awaiting_approval' ? 'Waiting for your approval — nothing sent yet' : r.summary?.headline || r.error || 'In progress'}</span>
                    <span className="block text-xs text-ink-3">{dateTime(r.started_at)} · v{r.workflow_version}{r.triggered_by === 'schedule' ? ' · scheduled' : ''}</span>
                  </span>
                  <RunStatusPill status={r.status} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === 'memory' && (
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-line flex flex-wrap items-center gap-3">
            <p className="text-[13px] text-ink-2 flex-1 min-w-[240px]">{a.requirement?.memory?.description || 'What this agent remembers between runs.'} Forget someone to include them again next run.</p>
            {!!mem.data?.length && <button className="btn-danger btn-sm" onClick={() => setConfirmClear(true)}>Clear memory</button>}
          </div>
          {mem.data && !mem.data.length && <EmptyState icon={<Brain className="h-5 w-5" />} title="Nothing remembered yet" body="After a live run, everyone who received an email is listed here so the next run skips them." />}
          <ul>
            {mem.data?.map(m => (
              <li key={m.id} className="flex items-center gap-3 px-5 py-2.5 border-b border-line last:border-0">
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] font-semibold truncate">{m.value?.name || m.key}</span>
                  <span className="block text-xs text-ink-3 truncate">{m.key} · {m.namespace} {timeAgo(m.updated_at)}{m.value?.subject ? ` · “${m.value.subject}”` : ''}</span>
                </span>
                <button className="btn-ghost btn-sm" onClick={() => forget(m.id)}><X className="h-3.5 w-3.5" />Forget</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {tab === 'versions' && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <ul>
              {versions.data?.map(v => (
                <li key={v.version} className="flex items-center gap-3 px-5 py-3 border-b border-line last:border-0">
                  <span className="font-display text-[17px] font-semibold w-10">v{v.version}</span>
                  <span className="flex-1 text-[13px] text-ink-2">{v.steps} steps · validation {v.status} · {dateTime(v.created_at)}</span>
                  {v.tested && <span className="text-xs font-semibold text-f-action">Test passed</span>}
                  {v.version === wf?.version && <span className="text-xs font-semibold text-ink">Current</span>}
                </li>
              ))}
            </ul>
          </div>
          <div className="card p-5 flex flex-wrap items-center gap-3">
            <div className="flex-1 min-w-[240px]"><div className="text-[14px] font-semibold">Delete this agent</div><div className="text-[13px] text-ink-2">Removes its schedule, memory and pending approvals. Sent emails stay in the outbox.</div></div>
            <button className="btn-danger" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4" />Delete agent</button>
          </div>
        </div>
      )}

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Delete agent?"
        footer={<><button className="btn-ghost" onClick={() => setConfirmDelete(false)}>Keep it</button><button className="btn bg-f-approval text-white" onClick={remove}>Delete agent</button></>}>
        <p className="text-[14px]">“{a.name}” and its memory will be deleted. This can’t be undone.</p>
      </Modal>
      <Modal open={confirmClear} onClose={() => setConfirmClear(false)} title="Clear memory?"
        footer={<><button className="btn-ghost" onClick={() => setConfirmClear(false)}>Cancel</button><button className="btn bg-f-approval text-white" onClick={clearMem}>Clear {mem.data?.length} entries</button></>}>
        <p className="text-[14px]">The next run will treat everyone as new — people who were already emailed could be emailed again.</p>
      </Modal>
    </div>
  )
}

function ApproverPicker({ agent, onChange }: { agent: Agent; onChange: (a: Agent) => void }) {
  const team = useApi<{ id: string; name: string; title: string }[]>('/team')
  if (!agent.approval_required || !team.data) return null
  const set = async (id: string) => {
    try { const n = await api<Agent>(`/agents/${agent.id}`, { method: 'PATCH', body: { approver_id: id } }); onChange(n); toast.success(`${team.data?.find(t => t.id === id)?.name} now approves this agent`) }
    catch (e: any) { toast.error(e.message) }
  }
  return (
    <label className="mt-2 inline-flex items-center gap-2 text-[13px] text-ink-2">
      <UserCheck className="h-3.5 w-3.5 text-f-approval" />Approved by
      <select className="h-8 rounded-lg border border-line-strong bg-surface px-2 text-[13px] font-semibold text-ink" value={agent.approver_id} onChange={e => set(e.target.value)} aria-label="Approver">
        {team.data.map(m => <option key={m.id} value={m.id}>{m.name}{m.id === agent.owner_id ? ' (built it)' : ''}</option>)}
      </select>
    </label>
  )
}
