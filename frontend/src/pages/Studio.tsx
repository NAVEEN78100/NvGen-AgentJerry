import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRight, ArrowUp, Check, ChevronDown, CornerDownLeft, FileSpreadsheet, FlaskConical, Info, Lock, Radio,
  ShieldCheck, Sparkles,
} from 'lucide-react'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AnnotatedText, FieldSwatch } from '../components/Annotated'
import { QuestionCard } from '../components/QuestionCard'
import { ValidationBadge, ValidationList } from '../components/Validation'
import { TOOL_ICON, WorkflowGraph, WorkflowList } from '../components/WorkflowGraph'
import { AgentStatusPill, ErrorNote, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { BG, CATEGORY_FIELD, HEX } from '../lib/fields'
import { useApi } from '../lib/hooks'
import type { Agent, ConvMessage, DataFile, FieldKey, Step } from '../lib/types'

const FIELD_LABEL: Record<FieldKey, string> = {
  trigger: 'When it runs', data: 'Where the data is', audience: 'Who it targets', action: 'What it does',
  approval: 'Safety check', knowledge: 'Knowledge it uses', memory: 'What it remembers', output: 'Output',
}

const THINKING = ['Reading your instruction', 'Checking for anything missing', 'Planning the steps', 'Running safety checks']

function Thinking() {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setI(x => Math.min(x + 1, THINKING.length - 1)), 420)
    return () => clearInterval(t)
  }, [])
  return (
    <div className="space-y-2.5 py-1" aria-live="polite">
      {THINKING.map((s, k) => (
        <motion.div key={s} initial={{ opacity: 0, x: -4 }} animate={{ opacity: k <= i ? 1 : 0.35, x: 0 }} transition={{ delay: k * 0.05 }}
          className="flex items-center gap-2.5 text-[13.5px]">
          <span className={clsx('h-5 w-5 rounded-full grid place-items-center', k < i ? 'bg-f-action text-white' : k === i ? 'bg-brand-soft text-brand' : 'bg-paper text-ink-3')}>
            {k < i ? <Check className="h-3 w-3" strokeWidth={3} /> : k === i ? <Spinner className="h-3 w-3" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
          </span>
          <span className={k <= i ? 'text-ink font-medium' : 'text-ink-3'}>{s}</span>
        </motion.div>
      ))}
    </div>
  )
}

function JerryAvatar() {
  return <span className="h-7 w-7 rounded-full bg-brand text-white grid place-items-center text-[12px] font-bold shrink-0 font-display">J</span>
}

function Bubble({ m, active, setActive, last, animate }: { m: ConvMessage; active: FieldKey | null; setActive: (f: FieldKey | null) => void; last: boolean; animate: boolean }) {
  if (m.role === 'user') {
    if (m.kind === 'prompt') return null // rendered as the hero sentence
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-ink text-white px-3.5 py-2 text-[13.5px]">
          {m.kind === 'refine' ? <span>{m.text}</span> : <span><span className="opacity-60">Answered: </span>{m.text}</span>}
        </div>
      </div>
    )
  }
  if (m.kind === 'understanding') {
    return (
      <div className="flex gap-3">
        <JerryAvatar />
        <div className="flex-1 min-w-0">
          <div className="text-[13.5px] text-ink-2 mb-2">{m.text}</div>
          <div className="rounded-xl border border-line bg-surface divide-y divide-line">
            {m.fields?.map((f, i) => (
              <motion.div key={f.label} initial={animate ? { opacity: 0, y: 4 } : false} animate={{ opacity: 1, y: 0 }} transition={{ delay: animate ? 0.25 + i * 0.06 : 0 }}
                onMouseEnter={() => setActive(f.field)} onMouseLeave={() => setActive(null)}
                className={clsx('flex items-start gap-3 px-3.5 py-2.5 transition-colors', active === f.field && 'bg-paper')}>
                <span className="mt-1.5"><FieldSwatch field={f.field} /></span>
                <span className="w-[128px] shrink-0 text-[12.5px] font-semibold text-ink-2">{f.label}</span>
                <span className={clsx('text-[13.5px] min-w-0', f.value ? 'text-ink' : 'text-ink-3 italic')}>{f.value || 'Not set yet'}</span>
              </motion.div>
            ))}
          </div>
          {!!m.assumptions?.length && (
            <div className="mt-2.5 flex gap-2 text-xs text-ink-2">
              <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-3" />
              <div>
                <span className="font-semibold">I assumed:</span> {m.assumptions.join(' · ')}. <span className="text-ink-3">Say so below if any are wrong.</span>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }
  if (m.kind === 'questions') {
    return (
      <div className="flex gap-3">
        <JerryAvatar />
        <div className={clsx('text-[13.5px] pt-1', last ? 'text-ink font-semibold' : 'text-ink-2')}>{m.text}</div>
      </div>
    )
  }
  if (m.kind === 'blueprint') {
    return (
      <div className="flex gap-3">
        <JerryAvatar />
        <div className="flex-1">
          <div className="text-[13.5px] text-ink pt-1">{m.text}</div>
          {m.was_live && <div className="mt-1 text-xs text-f-approval">This agent was live. It’s offline until the new version passes a test.</div>}
          {m.validation && <div className="mt-2"><ValidationBadge validation={m.validation} /></div>}
          {m.version && <div className="mt-1 text-2xs text-ink-3">Version {m.version}</div>}
        </div>
      </div>
    )
  }
  return null
}

function StepInspector({ step, index }: { step: Step; index: number }) {
  const field = CATEGORY_FIELD[step.category] || 'action'
  const Icon = TOOL_ICON[step.tool]
  const params = Object.entries(step.params).filter(([k, v]) => v !== null && v !== '' && !['roles', 'source_ids', 'entity', 'label'].includes(k) && typeof v !== 'object')
  return (
    <motion.div key={step.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2.5">
        <span className="h-8 w-8 rounded-lg grid place-items-center" style={{ background: BG[field], color: HEX[field] }}>{Icon && <Icon className="h-4 w-4" />}</span>
        <div className="min-w-0">
          <div className="text-2xs font-semibold text-ink-3">Step {index + 1} · {step.tool}</div>
          <div className="text-[14px] font-semibold truncate">{step.label}</div>
        </div>
        {step.sensitive && <span className="ml-auto inline-flex items-center gap-1 text-2xs font-semibold text-f-approval bg-f-approvalbg h-5 px-1.5 rounded"><Lock className="h-3 w-3" />Sensitive</span>}
      </div>
      <p className="mt-3 text-[13px] text-ink">{step.description}</p>
      <p className="mt-1.5 text-[12.5px] text-ink-2"><span className="font-semibold">Why this step: </span>{step.why}</p>
      {!!params.length && (
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {params.map(([k, v]) => (<Fragment key={k}><dt className="text-ink-3">{k.replace(/_/g, ' ')}</dt><dd className="text-ink truncate">{String(v)}</dd></Fragment>))}
        </dl>
      )}
    </motion.div>
  )
}

function Blueprint({ agent, onTest, testing, onRename }: { agent: Agent; onTest: () => void; testing: boolean; onRename: (n: string) => void }) {
  const wf = agent.workflow
  const [sel, setSel] = useState<string | null>(null)
  const [showChecks, setShowChecks] = useState(false)
  const [name, setName] = useState(agent.name)
  useEffect(() => setName(agent.name), [agent.name])
  const selStep = wf?.steps.find(s => s.id === sel)
  const req = agent.requirement || {}
  const building = !wf || agent.questions.length > 0

  return (
    <div className="card overflow-hidden">
      <div className="p-5 border-b border-line">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <input value={name} onChange={e => setName(e.target.value)} onBlur={() => name.trim() && name !== agent.name && onRename(name.trim())}
              onKeyDown={e => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
              aria-label="Agent name" className="w-full font-display text-[21px] font-semibold bg-transparent rounded-md -ml-1 px-1 hover:bg-paper focus:bg-paper focus:outline-none" />
            <p className="mt-1 text-[13px] text-ink-2 leading-relaxed">{agent.goal || 'Answer the questions on the left and the goal will appear here.'}</p>
          </div>
          <AgentStatusPill status={agent.status} />
        </div>
        {req.purpose && (
          <div className="mt-3.5 flex flex-wrap gap-2 text-xs">
            <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg font-semibold" style={{ background: BG.trigger, color: '#8A5D00' }}><Radio className="h-3.5 w-3.5" />{agent.trigger_label}</span>
            {agent.source_file && <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg font-semibold" style={{ background: BG.data, color: HEX.data }}><FileSpreadsheet className="h-3.5 w-3.5" />{agent.source_file}</span>}
            <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg font-semibold" style={{ background: BG.approval, color: HEX.approval }}><ShieldCheck className="h-3.5 w-3.5" />{agent.approval_required ? 'You approve before sending' : 'Sends automatically'}</span>
          </div>
        )}
      </div>

      <div className="relative bg-paper/60">
        {building ? (
          <div className="p-8 h-[420px] flex flex-col items-center justify-center text-center">
            <div className="space-y-3 w-[260px] opacity-70">
              {[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-12 rounded-xl" style={{ animationDelay: `${i * 120}ms` }} />)}
            </div>
            <p className="mt-6 text-[13px] text-ink-2 max-w-[34ch]">The workflow appears here as soon as I have what I need.</p>
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <WorkflowGraph steps={wf!.steps} selected={sel} onSelect={id => setSel(s => s === id ? null : id)} height={wf!.steps.length * 104 + 24} />
            </div>
            <div className="md:hidden p-4"><WorkflowList steps={wf!.steps} /></div>
            <div className="hidden md:block absolute top-3 right-3 text-2xs text-ink-3 bg-surface/90 rounded-md px-2 py-1 border border-line">Click a step for details</div>
          </>
        )}
      </div>

      {!building && wf && (
        <div className="p-5 border-t border-line space-y-4">
          <AnimatePresence mode="wait">{selStep && <StepInspector step={selStep} index={wf.steps.indexOf(selStep)} />}</AnimatePresence>
          <div>
            <button onClick={() => setShowChecks(s => !s)} className="w-full flex items-center justify-between gap-2" aria-expanded={showChecks}>
              <span className="text-[13.5px] font-semibold">Validation</span>
              <span className="flex items-center gap-2"><ValidationBadge validation={wf.validation} /><ChevronDown className={clsx('h-4 w-4 text-ink-3 transition-transform', showChecks && 'rotate-180')} /></span>
            </button>
            <AnimatePresence>
              {showChecks && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                  <div className="pt-3"><ValidationList validation={wf.validation} animate /></div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {wf.validation.valid && (
              <button className="btn-primary btn-lg flex-1 min-w-[180px]" onClick={onTest} disabled={testing}>
                {testing ? <Spinner /> : <FlaskConical className="h-4 w-4" />}
                {agent.tested_version === wf.version ? 'Run the test again' : 'Run a safe test'}
              </button>
            )}
            <Link to={`/agents/${agent.id}`} className="btn-secondary btn-lg">Open agent <ArrowRight className="h-4 w-4" /></Link>
          </div>
          <p className="text-xs text-ink-3">A test reads your real data and writes real drafts, but sends nothing and remembers nothing.</p>
        </div>
      )}
    </div>
  )
}

export function Studio() {
  const { agentId } = useParams()
  const nav = useNavigate()
  const { user } = useAuth()
  const [agent, setAgent] = useState<Agent | null>(null)
  const loc = useLocation()
  const [prompt, setPrompt] = useState<string>((loc.state as any)?.prompt || '')
  const [phase, setPhase] = useState<'idle' | 'thinking' | 'ready'>(agentId ? 'ready' : 'idle')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refine, setRefine] = useState('')
  const [active, setActive] = useState<FieldKey | null>(null)
  const [testing, setTesting] = useState(false)
  const [freshIds, setFreshIds] = useState<number>(0)
  const templates = useApi<{ id: string; title: string; prompt: string; department: string }[]>(agentId ? null : '/studio/templates')
  const files = useApi<DataFile[]>(agentId ? null : '/files')
  const bottomRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!agentId) { setAgent(null); setPhase('idle'); return }
    if (agent?.id === agentId) return
    api<Agent>(`/agents/${agentId}`).then(a => { setAgent(a); setPhase('ready'); setFreshIds(a.conversation.length) }).catch(e => setError(e.message))
  }, [agentId]) // eslint-disable-line

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [agent?.conversation.length])

  const withMinDelay = async <T,>(p: Promise<T>, ms = 1500) => {
    const [r] = await Promise.all([p, new Promise(res => setTimeout(res, ms))])
    return r
  }

  const start = async (text?: string) => {
    const t = (text ?? prompt).trim()
    if (t.length < 3) return
    setPrompt(t); setPhase('thinking'); setError(null)
    try {
      const a = await withMinDelay(api<Agent>('/studio', { body: { prompt: t } }), 1700)
      setFreshIds(0)
      setAgent(a); setPhase('ready')
      nav(`/studio/${a.id}`, { replace: true })
    } catch (e: any) { setError(e.message); setPhase('idle') }
  }

  const answer = async (id: string, value: string) => {
    if (!agent) return
    setBusy(true)
    try {
      const prevLen = agent.conversation.length
      const a = await withMinDelay(api<Agent>(`/studio/${agent.id}/answer`, { body: { answers: { [id]: value } } }), 600)
      setFreshIds(prevLen); setAgent(a)
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  const sendRefine = async () => {
    if (!agent || refine.trim().length < 2) return
    setBusy(true)
    try {
      const prevLen = agent.conversation.length
      const a = await withMinDelay(api<Agent>(`/studio/${agent.id}/refine`, { body: { text: refine.trim() } }), 700)
      setFreshIds(prevLen); setAgent(a); setRefine('')
    } catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  const rename = async (name: string) => {
    if (!agent) return
    try { const a = await api<Agent>(`/agents/${agent.id}`, { method: 'PATCH', body: { name } }); setAgent(a); toast.success('Renamed') } catch (e: any) { toast.error(e.message) }
  }

  const test = async () => {
    if (!agent) return
    setTesting(true)
    try {
      const r = await api(`/agents/${agent.id}/runs`, { body: { mode: 'test' } })
      nav(`/agents/${agent.id}/runs/${r.id}`)
    } catch (e: any) { toast.error(e.message); setTesting(false) }
  }

  const promptMsg = agent?.conversation.find(m => m.kind === 'prompt')
  const lastQIndex = useMemo(() => agent ? agent.conversation.map(m => m.kind).lastIndexOf('questions') : -1, [agent])

  // ---------------------------------------------------------------- idle
  if (phase !== 'ready' || !agent) {
    return (
      <div className="max-w-[860px] mx-auto pt-4 lg:pt-10">
        <h1 className="font-display text-[34px] sm:text-[42px] leading-[1.08] font-semibold tracking-tight">
          {phase === 'thinking' ? 'Working it out…' : `What should your agent do, ${user?.name.split(' ')[0]}?`}
        </h1>
        <p className="mt-2 text-ink-2 text-[15.5px] max-w-[60ch]">
          Describe a task you repeat, the way you’d explain it to a new colleague: when it happens, where the data lives, and what should come out.
        </p>
        <div className={clsx('mt-7 card p-2 transition-shadow', phase === 'thinking' ? 'opacity-90' : 'focus-within:shadow-pop focus-within:border-line-strong')}>
          <textarea ref={taRef} value={prompt} onChange={e => setPrompt(e.target.value)} rows={4} disabled={phase === 'thinking'} autoFocus
            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) start() }}
            placeholder="e.g. Every Monday at 9am, read my sales spreadsheet, find new leads, draft follow-up emails and show them to me before sending."
            className="w-full resize-none bg-transparent px-3 pt-2.5 text-[17px] leading-relaxed placeholder:text-ink-3 focus:outline-none" aria-label="Describe your task" />
          <div className="flex items-center justify-between gap-2 px-2 pb-1">
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-ink-3"><span className="kbd">Ctrl</span><span className="kbd"><CornerDownLeft className="h-3 w-3" /></span> to build</span>
            <button className="btn-primary h-10 ml-auto" disabled={prompt.trim().length < 3 || phase === 'thinking'} onClick={() => start()}>
              {phase === 'thinking' ? <Spinner /> : <Sparkles className="h-4 w-4" />} Build my agent
            </button>
          </div>
        </div>
        {error && <div className="mt-4"><ErrorNote message={error} /></div>}

        <AnimatePresence mode="wait">
          {phase === 'thinking' ? (
            <motion.div key="t" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="mt-8 card p-5 max-w-[420px]"><Thinking /></motion.div>
          ) : (
            <motion.div key="i" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <h2 className="mt-10 text-[15px] font-semibold">Start from an example</h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {templates.data?.map(t => (
                  <button key={t.id} onClick={() => { setPrompt(t.prompt); taRef.current?.focus() }}
                    className="text-left card p-4 hover:border-line-strong hover:shadow-pop transition-all group">
                    <div className="flex items-center justify-between">
                      <span className="text-[14px] font-semibold">{t.title}</span>
                      <span className="text-2xs font-semibold text-ink-3 uppercase-none">{({ sales: 'Sales', finance: 'Finance', hr: 'HR' } as any)[t.department] || t.department}</span>
                    </div>
                    <p className="mt-1.5 text-[13px] text-ink-2 line-clamp-2">{t.prompt}</p>
                    <span className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand opacity-0 group-hover:opacity-100 transition-opacity">Use this <ArrowUp className="h-3 w-3" /></span>
                  </button>
                ))}
              </div>
              {!!files.data?.length && (
                <p className="mt-6 text-[13px] text-ink-2">
                  Jerry can read your files: {files.data.slice(0, 4).map(f => f.name).join(', ')}{files.data.length > 4 ? '…' : ''}. <Link to="/data" className="font-semibold text-brand hover:underline">Manage files</Link>
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    )
  }

  // ---------------------------------------------------------------- conversation + blueprint
  const hasPurpose = !!agent.requirement?.purpose
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] items-start">
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-3 mb-4">
          <h1 className="text-[22px] font-semibold">Agent Studio</h1>
          <Link to="/studio" className="btn-ghost btn-sm">Start over</Link>
        </div>
        {promptMsg && (
          <div className="card p-5">
            <div className="text-2xs font-semibold text-ink-3 mb-1.5">You asked</div>
            <AnnotatedText text={promptMsg.text} spans={promptMsg.spans || []} active={active} onHover={setActive} animate={freshIds === 0} />
            {!!promptMsg.spans?.length && (
              <div className="mt-3 flex flex-wrap gap-x-3.5 gap-y-1">
                {Array.from(new Set(promptMsg.spans.map(s => s.field))).map(f => [f, FIELD_LABEL[f]] as const).map(([f, l]) => (
                  <button key={f} onMouseEnter={() => setActive(f)} onMouseLeave={() => setActive(null)} className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-2 hover:text-ink">
                    <FieldSwatch field={f} />{l}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="mt-5 space-y-4">
          {agent.conversation.map((m, i) => (
            <motion.div key={i} initial={i >= freshIds ? { opacity: 0, y: 8 } : false} animate={{ opacity: 1, y: 0 }} transition={{ delay: i >= freshIds ? 0.15 * (i - freshIds) : 0 }}>
              <Bubble m={m} active={active} setActive={setActive} last={i === lastQIndex} animate={i >= freshIds} />
            </motion.div>
          ))}
          {agent.questions.length > 0 && (
            <div className="pl-10 space-y-3">
              {agent.questions.map((q, i) => <QuestionCard key={q.id + agent.conversation.length} q={q} index={i} onAnswer={answer} busy={busy} />)}
            </div>
          )}
          {busy && <div className="pl-10 flex items-center gap-2 text-[13px] text-ink-2"><Spinner />Updating the agent…</div>}
          <div ref={bottomRef} />
        </div>

        {hasPurpose && (
          <form className="mt-6 sticky bottom-4" onSubmit={e => { e.preventDefault(); sendRefine() }}>
            <div className="card shadow-pop flex items-center gap-2 p-1.5 pl-3.5">
              <input value={refine} onChange={e => setRefine(e.target.value)} disabled={busy} aria-label="Change something"
                placeholder="Change anything: “make it formal”, “run on Fridays at 4pm”, “mention our free pilot”"
                className="flex-1 min-w-0 bg-transparent text-[14px] placeholder:text-ink-3 focus:outline-none h-9" />
              <button className="btn-primary h-9 !px-3" disabled={busy || refine.trim().length < 2} aria-label="Apply change">{busy ? <Spinner /> : <ArrowUp className="h-4 w-4" />}</button>
            </div>
          </form>
        )}
      </div>

      <div className="min-w-0">
        <Blueprint agent={agent} onTest={test} testing={testing} onRename={rename} />
      </div>
    </div>
  )
}
