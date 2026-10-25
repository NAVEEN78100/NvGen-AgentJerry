import clsx from 'clsx'
import { Check, Gauge, X } from 'lucide-react'
import { useState } from 'react'
import { AnnotatedText } from '../components/Annotated'
import { ErrorNote, PageHeader, Skeleton, Tabs } from '../components/ui'
import { useApi } from '../lib/hooks'
import type { Span } from '../lib/types'

type Field = { field: string; label: string; correct: number; total: number; accuracy: number }
type Case = { id: number; text: string; spans: Span[]; ok: boolean; results: { field: string; label: string; expected: any; got: any; ok: boolean }[] }
type Set = { cases: number; cases_fully_correct: number; field_accuracy: number; checks: number; per_field: Field[]; results: Case[] }
type Q = Set & { ms: number; held_out: Set; llm: { enabled: boolean; model: string | null } }

const show = (v: any) => v === null || v === undefined ? 'nothing' : v === true ? 'yes' : v === false ? 'no (auto-send)' : String(v)

function Score({ title, s, note }: { title: string; s: Set; note: string }) {
  return (
    <div className="card p-5">
      <div className="text-[13px] font-semibold text-ink-2">{title}</div>
      <div className="mt-1 flex items-baseline gap-3">
        <span className="font-display text-[40px] leading-none font-semibold tabular">{(s.field_accuracy * 100).toFixed(1)}%</span>
        <span className="text-[13px] text-ink-2">of {s.checks} checks</span>
      </div>
      <div className="mt-2 text-[13px] text-ink-2">{s.cases_fully_correct} of {s.cases} instructions fully correct</div>
      <p className="mt-3 text-xs text-ink-3">{note}</p>
    </div>
  )
}

export function Quality() {
  const q = useApi<Q>('/quality')
  const [set, setSet] = useState<'held' | 'tune'>('held')
  const [failOnly, setFailOnly] = useState(false)
  if (q.error) return <ErrorNote message={q.error} onRetry={q.reload} />
  if (!q.data) return <Skeleton className="h-96" />
  const cur = set === 'held' ? q.data.held_out : q.data
  const rows = cur.results.filter(c => !failOnly || !c.ok)
  return (
    <div>
      <PageHeader title="Engine quality" subtitle="How accurately Jerry turns a sentence into the right settings, measured against labelled instructions with known correct answers. Runs live on every page load — and as an automated test on every change." />
      <div className="grid gap-4 md:grid-cols-2">
        <Score title="New phrasing (held-out set)" s={q.data.held_out} note="Written after the engine was tuned and never used to adjust it — the honest estimate for sentences it hasn’t seen." />
        <Score title="Tuning set" s={q.data} note="Used while building the engine. A drop here means a change broke something that used to work (regression)." />
      </div>
      <p className="mt-3 text-xs text-ink-3 flex items-center gap-1.5"><Gauge className="h-3.5 w-3.5" />Offline engine, {q.data.ms} ms for all {q.data.cases + q.data.held_out.cases} instructions. {q.data.llm.enabled ? `Claude (${q.data.llm.model}) is also enabled for live requests.` : 'With an API key, Claude handles open-ended phrasing the rules miss.'}</p>

      <div className="mt-6">
        <Tabs value={set} onChange={setSet} items={[{ value: 'held', label: 'Held-out set', count: q.data.held_out.cases }, { value: 'tune', label: 'Tuning set', count: q.data.cases }]} />
      </div>
      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)] items-start">
        <div className="card p-5">
          <h2 className="text-[15px] font-semibold mb-3">Accuracy by field</h2>
          <ul className="space-y-2.5">
            {cur.per_field.map(f => (
              <li key={f.field}>
                <div className="flex justify-between text-[13px]"><span className="text-ink-2">{f.label}</span><span className="tabular"><b className="font-semibold">{f.correct}</b>/{f.total}</span></div>
                <div className="mt-1 h-1.5 rounded-full bg-paper overflow-hidden"><div className="h-full rounded-full" style={{ width: `${f.accuracy * 100}%`, background: f.accuracy === 1 ? '#178A63' : '#C98A0B' }} /></div>
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0">
          <label className="mb-3 inline-flex items-center gap-2 text-[13px] font-semibold text-ink-2"><input type="checkbox" checked={failOnly} onChange={e => setFailOnly(e.target.checked)} />Show only mistakes ({cur.results.filter(c => !c.ok).length})</label>
          <ul className="space-y-3">
            {rows.map(c => (
              <li key={c.id} className={clsx('card p-4', !c.ok && 'border-f-trigger/50')}>
                <div className="flex items-start gap-3">
                  <span className={clsx('mt-1 h-5 w-5 rounded-full grid place-items-center text-white shrink-0', c.ok ? 'bg-f-action' : 'bg-f-trigger')}>{c.ok ? <Check className="h-3 w-3" strokeWidth={3} /> : <X className="h-3 w-3" strokeWidth={3} />}</span>
                  <div className="min-w-0 flex-1">
                    <AnnotatedText text={c.text} spans={c.spans} size="md" animate={false} />
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {c.results.map(r => (
                        <span key={r.field} title={r.ok ? `${r.label}: ${show(r.got)}` : `${r.label}: expected ${show(r.expected)}, got ${show(r.got)}`}
                          className={clsx('h-6 px-2 rounded-md text-xs font-medium inline-flex items-center gap-1', r.ok ? 'bg-f-actionbg text-f-action' : 'bg-f-triggerbg text-[#8A5D00]')}>
                          {r.ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}{r.label}{!r.ok && <span className="opacity-80">: wanted {show(r.expected)}, got {show(r.got)}</span>}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
