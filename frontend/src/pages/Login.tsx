import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { AnnotatedText, FieldSwatch } from '../components/Annotated'
import { Spinner } from '../components/ui'
import { useAuth } from '../lib/auth'
import type { FieldKey, Span } from '../lib/types'

function spansFor(text: string, marks: [string, FieldKey, string][]): Span[] {
  return marks.map(([t, field, label]) => {
    const start = text.indexOf(t)
    return { start, end: start + t.length, text: t, field, label }
  })
}

const EXAMPLES = [
  {
    text: 'Every Monday, read my sales spreadsheet, find new leads, draft follow-up emails and show them to me first.',
    marks: [['Every Monday', 'trigger', 'When'], ['my sales spreadsheet', 'data', 'Data'], ['new leads', 'audience', 'Who'],
      ['draft follow-up emails', 'action', 'Does'], ['show them to me first', 'approval', 'Safety']] as [string, FieldKey, string][],
  },
  {
    text: 'Every weekday at 10am, check the invoices sheet for overdue invoices and send a polite reminder after I approve.',
    marks: [['Every weekday', 'trigger', 'When'], ['at 10am', 'trigger', 'When'], ['the invoices sheet', 'data', 'Data'],
      ['overdue invoices', 'audience', 'Who'], ['send a polite reminder', 'action', 'Does'], ['after I approve', 'approval', 'Safety']] as [string, FieldKey, string][],
  },
  {
    text: 'Find shortlisted candidates in the candidates spreadsheet and draft interview invitations for me to review.',
    marks: [['shortlisted candidates', 'audience', 'Who'], ['the candidates spreadsheet', 'data', 'Data'],
      ['draft interview invitations', 'action', 'Does'], ['for me to review', 'approval', 'Safety']] as [string, FieldKey, string][],
  },
]

export function Login() {
  const { user, login } = useAuth()
  const [email, setEmail] = useState('priya@brightpath.example')
  const [password, setPassword] = useState('demo1234')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ex, setEx] = useState(0)

  useEffect(() => {
    const t = window.setInterval(() => setEx(e => (e + 1) % EXAMPLES.length), 5200)
    return () => clearInterval(t)
  }, [])

  if (user) return <Navigate to="/" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try { await login(email, password) } catch (err: any) { setError(err.message) } finally { setBusy(false) }
  }
  const cur = EXAMPLES[ex]
  const legend = Array.from(new Map(cur.marks.map(m => [m[1], m[2]])).entries())

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.15fr_1fr] bg-surface">
      <section className="relative hidden lg:flex flex-col justify-between p-12 bg-paper border-r border-line overflow-hidden">
        <div className="flex items-center gap-2.5">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="9" fill="#26337A" /><path d="M11 9.5h10v2.6h-3.4v8.1c0 2.9-1.7 4.6-4.6 4.6-1 0-1.9-.2-2.6-.5l.5-2.5c.5.2 1 .3 1.6.3 1.2 0 1.8-.7 1.8-2.1v-7.9H11z" fill="#fff" /><circle cx="23" cy="21.5" r="2.3" fill="#F5B83D" /></svg>
          <span className="font-display text-[19px] font-semibold">AgentJerry</span>
        </div>
        <div className="max-w-[560px]">
          <h1 className="font-display text-[44px] leading-[1.05] font-semibold tracking-tight">
            Say what you do every week.<br />Jerry turns it into an agent.
          </h1>
          <p className="mt-4 text-ink-2 text-[16px] max-w-[48ch]">
            No triggers, APIs or flowcharts. Describe the job in your own words, test it safely, and approve anything that leaves the building.
          </p>
          <div className="mt-10 card p-6 min-h-[188px]">
            <AnimatePresence mode="wait">
              <motion.div key={ex} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.3 }}>
                <AnnotatedText text={cur.text} spans={spansFor(cur.text, cur.marks)} size="lg" />
                <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5">
                  {legend.map(([f, l], i) => (
                    <motion.span key={f} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.7 + i * 0.08 }}
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-2"><FieldSwatch field={f} />{l}</motion.span>
                  ))}
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
        <p className="text-xs text-ink-3">Every sensitive action waits for a person. Every run is logged.</p>
      </section>

      <section className="flex items-center justify-center p-6 sm:p-12">
        <form onSubmit={submit} className="w-full max-w-[380px]">
          <div className="lg:hidden flex items-center gap-2.5 mb-10">
            <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="9" fill="#26337A" /><path d="M11 9.5h10v2.6h-3.4v8.1c0 2.9-1.7 4.6-4.6 4.6-1 0-1.9-.2-2.6-.5l.5-2.5c.5.2 1 .3 1.6.3 1.2 0 1.8-.7 1.8-2.1v-7.9H11z" fill="#fff" /><circle cx="23" cy="21.5" r="2.3" fill="#F5B83D" /></svg>
            <span className="font-display text-[19px] font-semibold">AgentJerry</span>
          </div>
          <h2 className="text-[26px] font-semibold">Sign in</h2>
          <p className="mt-1 text-ink-2">to the Brightpath Software workspace.</p>
          <div className="mt-8 space-y-4">
            <div>
              <label className="label" htmlFor="email">Work email</label>
              <input id="email" className="input" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <div>
              <label className="label" htmlFor="pw">Password</label>
              <input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required />
            </div>
            {error && <p role="alert" className="text-[13px] text-f-approval">{error}</p>}
            <button className="btn-primary btn-lg w-full" disabled={busy}>{busy ? <Spinner /> : <>Sign in <ArrowRight className="h-4 w-4" /></>}</button>
          </div>
          <div className="mt-8 rounded-xl bg-paper border border-line p-4 text-[12.5px] text-ink-2">
            <div className="font-semibold text-ink mb-1">Demo accounts</div>
            <button type="button" className="block hover:text-ink" onClick={() => setEmail('priya@brightpath.example')}>priya@brightpath.example — Sales Lead, admin</button>
            <button type="button" className="block hover:text-ink" onClick={() => setEmail('arun@brightpath.example')}>arun@brightpath.example — Finance</button>
            <div className="mt-1 text-ink-3">Password for both: demo1234</div>
          </div>
        </form>
      </section>
    </div>
  )
}
