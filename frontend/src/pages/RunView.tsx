import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronDown, Hourglass, Radio, RotateCcw, Square, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { DraftCard } from '../components/DraftCard'
import { TOOL_ICON } from '../components/WorkflowGraph'
import { ErrorNote, Modal, ModeTag, RunStatusPill, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { BG, CATEGORY_FIELD, HEX } from '../lib/fields'
import { dateTime, duration, timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { Agent, Draft, Run, RunLog } from '../lib/types'

const ACTIVE = ['queued', 'running']

function StepOutput({ log, onPreview }: { log: RunLog; onPreview: (d: Draft[]) => void }) {
  const o = log.output || {}
  switch (log.tool) {
    case 'spreadsheet.read': {
      const cols: string[] = (o.columns || []).slice(0, 6)
      return (
        <div className="overflow-x-auto thin-scroll rounded-lg border border-line">
          <table className="w-full text-xs">
            <thead className="bg-paper"><tr>{cols.map(c => <th key={c} className="text-left font-semibold text-ink-2 px-2.5 py-1.5 whitespace-nowrap">{c}</th>)}</tr></thead>
            <tbody>{(o.preview || []).map((r: any, i: number) => <tr key={i} className="border-t border-line">{cols.map(c => <td key={c} className="px-2.5 py-1.5 whitespace-nowrap max-w-[180px] truncate">{r[c]}</td>)}</tr>)}</tbody>
          </table>
          <div className="px-2.5 py-1.5 text-2xs text-ink-3 border-t border-line bg-paper/60">Showing {Math.min(6, o.count)} of {o.count} rows · {o.columns?.length} columns</div>
        </div>
      )
    }
    case 'data.filter':
      return (
        <div className="text-[13px]">
          <div className="text-ink-2">Rule: <b className="text-ink font-semibold">{o.rule}</b> · kept {o.kept}, set aside {o.removed}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">{(o.sample || []).map((n: string) => <span key={n} className="h-6 px-2 rounded-md text-xs font-medium inline-flex items-center" style={{ background: BG.audience, color: HEX.audience }}>{n}</span>)}</div>
        </div>
      )
    case 'memory.exclude':
      return o.skipped?.length ? (
        <div>
          <div className="text-[13px] text-ink-2 mb-2">Already handled in earlier runs:</div>
          <div className="flex flex-wrap gap-1.5">{o.skipped.map((s: any) => <span key={s.key} title={s.key} className="h-6 px-2 rounded-md text-xs font-medium inline-flex items-center line-through decoration-1" style={{ background: BG.memory, color: HEX.memory }}>{s.name}</span>)}</div>
        </div>
      ) : <div className="text-[13px] text-ink-2">Memory holds {o.memory_size ?? 0} entries — no one here was handled before.</div>
    case 'knowledge.retrieve':
      return o.example ? (
        <div className="rounded-lg border border-line p-3 text-[13px]">
          <div className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: HEX.knowledge }}><BookOpen className="h-3.5 w-3.5" />{o.example.source_title}{o.example.section && ` › ${o.example.section}`}</div>
          <p className="mt-1 text-ink-2 line-clamp-3">{o.example.text}</p>
        </div>
      ) : null
    case 'ai.draft':
    case 'ai.draft_report':
      return o.samples?.length ? (
        <div className="space-y-2">
          <DraftCard d={o.samples[0]} compact />
          {o.count > 1 && <button className="btn-secondary btn-sm" onClick={() => onPreview(o.samples)}>See {Math.min(3, o.count)} sample drafts</button>}
        </div>
      ) : null
    case 'safety.check':
      return o.issues?.length ? (
        <ul className="space-y-1 text-[13px]">{o.issues.map((x: any, i: number) => <li key={i}><b className="font-semibold">{x.to}</b>: <span className="text-ink-2">{x.flags.map((f: any) => f.text).join(' ')}</span></li>)}</ul>
      ) : <div className="text-[13px] text-ink-2">No invalid addresses, placeholders or risky wording.</div>
    case 'approval.request':
      return o.drafts?.length ? <button className="btn-secondary btn-sm" onClick={() => onPreview(o.drafts)}>Preview all {o.drafts.length} drafts</button>
        : o.approved != null ? <div className="text-[13px] text-ink-2">{o.approved} approved · {o.rejected} rejected{o.edited ? ` · ${o.edited} edited` : ''} · by {o.decided_by}</div> : null
    case 'email.send':
      return o.recipients?.length ? <div className="flex flex-wrap gap-1.5">{o.recipients.map((n: string) => <span key={n} className="h-6 px-2 rounded-md text-xs font-medium inline-flex items-center" style={{ background: BG.output, color: HEX.output }}>{n}</span>)}</div> : null
    default:
      return null
  }
}

function StepRow({ log, isLast, onPreview }: { log: RunLog; isLast: boolean; onPreview: (d: Draft[]) => void }) {
  const [open, setOpen] = useState(false)
  const field = CATEGORY_FIELD[{ 'spreadsheet.read': 'data', 'data.filter': 'audience', 'memory.exclude': 'memory', 'memory.record': 'memory', 'knowledge.retrieve': 'knowledge', 'ai.draft': 'ai', 'data.summarize': 'ai', 'ai.draft_report': 'ai', 'safety.check': 'safety', 'approval.request': 'approval', 'email.send': 'action', 'notify.summary': 'output' }[log.tool] || 'ai']
  const Icon = TOOL_ICON[log.tool]
  const hasOutput = ['passed', 'waiting'].includes(log.status) && Object.keys(log.output || {}).length > 0 && log.tool !== 'notify.summary' && log.tool !== 'memory.record'
  useEffect(() => { if (log.status === 'waiting') setOpen(false) }, [log.status])
  const st = log.status
  return (
    <li className="relative pl-12">
      {!isLast && <span className={clsx('absolute left-[17px] top-10 bottom-0 w-px', st === 'passed' ? 'bg-f-action/40' : 'bg-line')} />}
      <div className="absolute left-0 top-1.5">
        <motion.span layout className={clsx('relative h-9 w-9 rounded-xl grid place-items-center transition-all', st === 'pending' || st === 'skipped' ? 'opacity-40' : '')}
          style={{ background: BG[field], color: HEX[field] }}>
          {Icon && <Icon className="h-4 w-4" />}
          <AnimatePresence>
            {st !== 'pending' && (
              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 500, damping: 22 }}
                className={clsx('absolute -right-1.5 -bottom-1.5 h-[18px] w-[18px] rounded-full grid place-items-center border-2 border-surface text-white',
                  st === 'passed' && 'bg-f-action', st === 'failed' && 'bg-f-approval', st === 'running' && 'bg-brand', st === 'waiting' && 'bg-f-approval', st === 'skipped' && 'bg-ink-3')}>
                {st === 'passed' && <Check className="h-2.5 w-2.5" strokeWidth={3.5} />}
                {st === 'failed' && <X className="h-2.5 w-2.5" strokeWidth={3.5} />}
                {st === 'running' && <Spinner className="h-2.5 w-2.5" />}
                {st === 'waiting' && <Hourglass className="h-2.5 w-2.5" strokeWidth={3} />}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.span>
      </div>
      <div className={clsx('pb-5', st === 'pending' && 'opacity-50')}>
        <button className="w-full text-left flex items-start gap-3 min-h-[44px] pt-1" onClick={() => hasOutput && setOpen(o => !o)} aria-expanded={open} disabled={!hasOutput}>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[14px] font-semibold text-ink">{log.label}</span>
              {st === 'running' && <span className="text-xs text-brand font-semibold">Working…</span>}
            </div>
            <AnimatePresence mode="wait">
              <motion.p key={log.message} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={clsx('text-[13px] mt-0.5', st === 'failed' ? 'text-f-approval' : st === 'waiting' ? 'text-f-approval font-medium' : 'text-ink-2')}>
                {log.message || (st === 'pending' ? 'Waiting to start' : '')}
              </motion.p>
            </AnimatePresence>
          </div>
          <span className="flex items-center gap-2 text-2xs text-ink-3 tabular pt-1 shrink-0">
            {log.duration_ms != null && duration(log.duration_ms)}
            {hasOutput && <ChevronDown className={clsx('h-4 w-4 transition-transform', open && 'rotate-180')} />}
          </span>
        </button>
        <AnimatePresence initial={false}>
          {open && hasOutput && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="pt-2.5"><StepOutput log={log} onPreview={onPreview} /></div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </li>
  )
}

export function RunView() {
  const { agentId, runId } = useParams()
  const nav = useNavigate()
  const run = useApi<Run>(`/runs/${runId}`, { poll: d => (!d || ACTIVE.includes(d.status) ? 500 : d.status === 'awaiting_approval' ? 4000 : false) })
  const agent = useApi<Agent>(`/agents/${agentId}`)
  const [preview, setPreview] = useState<Draft[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const r = run.data
  const a = agent.data

  useEffect(() => { if (r && !ACTIVE.includes(r.status)) agent.reload() }, [r?.status]) // eslint-disable-line

  if (run.error) return <ErrorNote message={run.error} onRetry={run.reload} />
  if (!r) return <div className="space-y-3 max-w-3xl"><Skeleton className="h-8 w-64" /><Skeleton className="h-4 w-96" /><Skeleton className="h-64 w-full" /></div>

  const done = r.logs.filter(l => l.status === 'passed').length
  const pct = Math.round((done / Math.max(1, r.logs.length)) * 100)
  const s = r.summary || {}

  const act = async (kind: 'deploy' | 'live' | 'test' | 'cancel') => {
    setBusy(kind)
    try {
      if (kind === 'deploy') { await api(`/agents/${agentId}/deploy`, { method: 'POST' }); toast.success('Agent is live'); nav(`/agents/${agentId}`) }
      if (kind === 'live' || kind === 'test') { const n = await api(`/agents/${agentId}/runs`, { body: { mode: kind } }); nav(`/agents/${agentId}/runs/${n.id}`) }
      if (kind === 'cancel') { await api(`/runs/${r.id}/cancel`, { method: 'POST' }); toast('Run cancelled'); run.reload() }
    } catch (e: any) { toast.error(e.message) } finally { setBusy(null) }
  }
  const approvalDrafts = r.logs.find(l => l.tool === 'approval.request')?.output?.drafts as Draft[] | undefined

  return (
    <div>
      <Link to={`/agents/${agentId}`} className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-2 hover:text-ink mb-3"><ArrowLeft className="h-4 w-4" />{r.agent_name}</Link>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-[26px] font-semibold">{r.mode === 'test' ? 'Test run' : 'Live run'}</h1>
        <ModeTag mode={r.mode} /><RunStatusPill status={r.status} />
        <span className="text-[13px] text-ink-3">Started {timeAgo(r.started_at)} · version {r.workflow_version}{r.triggered_by === 'schedule' ? ' · by schedule' : ''}</span>
        {(ACTIVE.includes(r.status) || r.status === 'awaiting_approval') && (
          <button className="btn-ghost btn-sm ml-auto" onClick={() => act('cancel')} disabled={!!busy}><Square className="h-3.5 w-3.5" />Cancel run</button>
        )}
      </div>
      <div className="mt-4 h-1.5 rounded-full bg-line overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <motion.div className={clsx('h-full rounded-full', r.status === 'failed' ? 'bg-f-approval' : r.status === 'awaiting_approval' ? 'bg-f-approval' : 'bg-f-action')}
          animate={{ width: `${pct}%` }} transition={{ type: 'spring', stiffness: 120, damping: 20 }} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] items-start">
        <ol className="card p-5 sm:p-6" aria-label="Steps">
          {r.logs.map((l, i) => <StepRow key={l.step_id} log={l} isLast={i === r.logs.length - 1} onPreview={setPreview} />)}
        </ol>

        <aside className="lg:sticky lg:top-20 space-y-4">
          <AnimatePresence mode="wait">
            {r.status === 'awaiting_approval' && (
              <motion.div key="ap" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5 border-f-approval/40 ring-4 ring-f-approval/10">
                <div className="flex items-center gap-2 text-f-approval font-semibold text-[13.5px]"><Hourglass className="h-4 w-4" />Waiting for you</div>
                <p className="mt-2 text-[14px] text-ink">Nothing has been sent. Review each draft — approve, edit or reject — and the run continues on its own.</p>
                <Link to={`/approvals/${r.approval_id}`} className="btn-primary btn-lg w-full mt-4">Review drafts <ArrowRight className="h-4 w-4" /></Link>
              </motion.div>
            )}
            {r.status === 'completed' && r.mode === 'test' && (
              <motion.div key="tp" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
                <div className="flex items-center gap-2 text-f-action font-semibold text-[13.5px]"><Check className="h-4 w-4" />Test passed</div>
                <p className="mt-2 text-[14px] text-ink">{s.headline}</p>
                <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                  {[['Loaded', s.loaded], ['Matched', s.matched ?? s.loaded], ['Drafts', s.drafted]].map(([k, v]) => (
                    <div key={k as string} className="rounded-lg bg-paper py-2"><dd className="font-display text-[22px] font-semibold tabular">{v ?? '—'}</dd><dt className="text-2xs text-ink-3 font-semibold">{k}</dt></div>
                  ))}
                </dl>
                {approvalDrafts?.length ? <button className="btn-secondary w-full mt-3" onClick={() => setPreview(approvalDrafts)}>Preview the drafts</button> : null}
                {a && a.tested_version === r.workflow_version && (
                  <div className="mt-4 pt-4 border-t border-line space-y-2">
                    {a.status !== 'deployed' && a.trigger?.type === 'schedule' && (
                      <button className="btn-primary btn-lg w-full" onClick={() => act('deploy')} disabled={!!busy}>{busy === 'deploy' ? <Spinner /> : <Radio className="h-4 w-4" />}Go live · {a.trigger_label}</button>
                    )}
                    {a.status !== 'deployed' && a.trigger?.type !== 'schedule' && (
                      <button className="btn-primary btn-lg w-full" onClick={() => act('deploy')} disabled={!!busy}>{busy === 'deploy' ? <Spinner /> : <Radio className="h-4 w-4" />}Go live</button>
                    )}
                    <button className="btn-secondary w-full" onClick={() => act('live')} disabled={!!busy}>{busy === 'live' ? <Spinner /> : <ArrowRight className="h-4 w-4" />}Run it for real now</button>
                    <p className="text-xs text-ink-3">Real runs still stop for your approval before anything is sent.</p>
                  </div>
                )}
              </motion.div>
            )}
            {r.status === 'completed' && r.mode === 'live' && (
              <motion.div key="lv" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
                <div className="flex items-center gap-2 text-f-action font-semibold text-[13.5px]"><Check className="h-4 w-4" />Run finished</div>
                <p className="mt-2 text-[14px] text-ink">{s.headline}</p>
                <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                  {[['Sent', s.sent], ['Rejected', s.rejected ?? 0], ['Skipped', s.skipped_memory ?? 0]].map(([k, v]) => (
                    <div key={k as string} className="rounded-lg bg-paper py-2"><dd className="font-display text-[22px] font-semibold tabular">{v ?? 0}</dd><dt className="text-2xs text-ink-3 font-semibold">{k}</dt></div>
                  ))}
                </dl>
                <div className="mt-4 flex gap-2">
                  <Link to="/outbox" className="btn-secondary flex-1">Open outbox</Link>
                  <Link to={`/agents/${agentId}?tab=memory`} className="btn-ghost flex-1">Agent memory</Link>
                </div>
              </motion.div>
            )}
            {r.status === 'failed' && (
              <motion.div key="f" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5">
                <div className="flex items-center gap-2 text-f-approval font-semibold text-[13.5px]"><X className="h-4 w-4" />Run stopped</div>
                <p className="mt-2 text-[14px] text-ink">{r.error}</p>
                <p className="mt-1 text-xs text-ink-3">Nothing after the failed step ran.</p>
                <div className="mt-4 flex gap-2">
                  <button className="btn-secondary flex-1" onClick={() => act('test')} disabled={!!busy}><RotateCcw className="h-4 w-4" />Test again</button>
                  <Link to={`/studio/${agentId}`} className="btn-ghost flex-1">Edit agent</Link>
                </div>
              </motion.div>
            )}
            {ACTIVE.includes(r.status) && (
              <motion.div key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card p-5">
                <div className="flex items-center gap-2 text-brand font-semibold text-[13.5px]"><Spinner />Running step {Math.min(done + 1, r.logs.length)} of {r.logs.length}</div>
                <p className="mt-2 text-[13px] text-ink-2">{r.mode === 'test' ? 'Test mode: real data, real drafts, no emails sent and nothing remembered.' : 'Live run. It will pause before anything is sent.'}</p>
              </motion.div>
            )}
          </AnimatePresence>
          <div className="card p-4 text-xs text-ink-2 space-y-1">
            <div className="flex justify-between"><span>Started</span><span className="text-ink">{dateTime(r.started_at)}</span></div>
            <div className="flex justify-between"><span>Finished</span><span className="text-ink">{dateTime(r.finished_at)}</span></div>
            <div className="flex justify-between"><span>Run ID</span><span className="text-ink font-mono text-2xs">{r.id}</span></div>
          </div>
        </aside>
      </div>

      <Modal open={!!preview} onClose={() => setPreview(null)} title={`Draft preview · ${preview?.length || 0}`} wide>
        <div className="space-y-4">{preview?.map((d, i) => <DraftCard key={i} d={d} />)}</div>
      </Modal>
    </div>
  )
}
