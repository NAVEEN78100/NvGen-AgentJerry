import { Ban, Copy, Cpu, Lock, Mail, RotateCcw, ShieldCheck, Webhook, Wrench, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { TOOL_ICON } from '../components/WorkflowGraph'
import { ErrorNote, Modal, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { BG, CATEGORY_FIELD, HEX } from '../lib/fields'
import { useApi } from '../lib/hooks'

type S = {
  org: { name: string }; is_admin: boolean
  policy: { require_approval_external: boolean; require_approval_internal: boolean; max_emails_per_run: number }
  smtp: { enabled?: boolean; host?: string; port?: number; username?: string; password?: string; from_email?: string; from_name?: string }
  engine: { provider: string; model: string | null; enabled: boolean }
  inbound_key: string | null
  tools: { name: string; label: string; category: string; description: string; sensitive: boolean; integration: string }[]
}

function Toggle({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label: string }) {
  return (
    <button role="switch" aria-checked={checked} aria-label={label} disabled={disabled} onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition-colors shrink-0 disabled:opacity-50 ${checked ? 'bg-f-action' : 'bg-line-strong'}`}>
      <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  )
}

export function SettingsPage() {
  const s = useApi<S>('/settings')
  const [smtp, setSmtp] = useState<S['smtp']>({})
  const [saving, setSaving] = useState(false)
  const [reset, setReset] = useState(false)
  const [resetting, setResetting] = useState(false)
  useEffect(() => { if (s.data) setSmtp({ port: 587, ...s.data.smtp }) }, [s.data])

  const patch = async (body: any, msg: string) => {
    setSaving(true)
    try { s.setData(await api<S>('/settings', { method: 'PATCH', body })); toast.success(msg) } catch (e: any) { toast.error(e.message) } finally { setSaving(false) }
  }
  const doReset = async () => {
    setResetting(true)
    try { await api('/demo/reset', { method: 'POST' }); toast.success('Demo workspace reset'); setTimeout(() => window.location.assign('/'), 400) } catch (e: any) { toast.error(e.message); setResetting(false) }
  }

  if (s.error) return <ErrorNote message={s.error} onRetry={s.reload} />
  if (!s.data) return <Skeleton className="h-96" />
  const d = s.data
  const admin = d.is_admin

  return (
    <div className="max-w-[900px]">
      <PageHeader title="Settings" subtitle={`Workspace rules for ${d.org.name}. ${admin ? '' : 'Only admins can change these.'}`} />
      <section className="card p-5">
        <h2 className="flex items-center gap-2 text-[16px] font-semibold"><ShieldCheck className="h-4 w-4" style={{ color: HEX.approval }} />Safety policy</h2>
        <div className="mt-4 divide-y divide-line">
          <div className="flex items-start gap-4 py-3">
            <div className="flex-1"><div className="text-[14px] font-semibold">Approve emails to people outside the company</div><div className="text-[13px] text-ink-2">Every agent must stop and show drafts to a person before emailing customers, candidates or vendors. Strongly recommended.</div></div>
            <Toggle label="Approve external emails" checked={d.policy.require_approval_external} disabled={!admin || saving} onChange={v => patch({ policy: { require_approval_external: v } }, v ? 'External emails now need approval' : 'External approval turned off')} />
          </div>
          <div className="flex items-start gap-4 py-3">
            <div className="flex-1"><div className="text-[14px] font-semibold">Approve internal emails too</div><div className="text-[13px] text-ink-2">Also require approval for reports and emails to colleagues at your own domain.</div></div>
            <Toggle label="Approve internal emails" checked={d.policy.require_approval_internal} disabled={!admin || saving} onChange={v => patch({ policy: { require_approval_internal: v } }, 'Policy updated')} />
          </div>
          <div className="flex items-center gap-4 py-3">
            <div className="flex-1"><div className="text-[14px] font-semibold">Most emails per run</div><div className="text-[13px] text-ink-2">A run never drafts more than this. The rest are picked up on the next run.</div></div>
            <input type="number" min={1} max={500} defaultValue={d.policy.max_emails_per_run} disabled={!admin} className="input w-24 h-9 tabular"
              onBlur={e => { const v = Number(e.target.value); if (v && v !== d.policy.max_emails_per_run) patch({ policy: { max_emails_per_run: v } }, `Limit set to ${v}`) }} />
          </div>
        </div>
        <p className="mt-2 text-xs text-ink-3">Policy changes apply the next time an agent is built or edited.</p>
      </section>

      <section className="card p-5 mt-5">
        <h2 className="flex items-center gap-2 text-[16px] font-semibold"><Mail className="h-4 w-4" style={{ color: HEX.output }} />Email delivery</h2>
        <p className="mt-1 text-[13px] text-ink-2">{smtp.enabled ? 'Approved emails are delivered through your SMTP server.' : 'Sandbox mode: approved emails are stored in the Outbox and never leave this machine. Ideal for demos and pilots.'}</p>
        <div className="mt-4 flex items-center gap-3"><Toggle label="Use SMTP" checked={!!smtp.enabled} disabled={!admin} onChange={v => setSmtp(x => ({ ...x, enabled: v }))} /><span className="text-[13.5px] font-semibold">Deliver real email via SMTP</span></div>
        {smtp.enabled && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {([['host', 'SMTP host', 'smtp.gmail.com'], ['port', 'Port', '587'], ['username', 'Username', ''], ['password', 'Password or app password', ''], ['from_email', 'From address', 'sales@yourcompany.com'], ['from_name', 'From name', 'Priya at Brightpath']] as const).map(([k, l, ph]) => (
              <div key={k}><label className="label" htmlFor={k}>{l}</label>
                <input id={k} className="input" type={k === 'password' ? 'password' : k === 'port' ? 'number' : 'text'} placeholder={ph} value={(smtp as any)[k] ?? ''} disabled={!admin}
                  onChange={e => setSmtp(x => ({ ...x, [k]: k === 'port' ? Number(e.target.value) : e.target.value }))} /></div>
            ))}
          </div>
        )}
        {admin && <div className="mt-4"><button className="btn-primary" disabled={saving} onClick={() => patch({ smtp: { enabled: false, host: '', port: 587, username: '', from_email: '', from_name: '', ...smtp } }, smtp.enabled ? 'SMTP saved' : 'Using sandbox delivery')}>{saving ? <Spinner /> : null}Save delivery settings</button></div>}
      </section>

      <DoNotContact />

      {d.inbound_key && (
        <section className="card p-5 mt-5">
          <h2 className="flex items-center gap-2 text-[16px] font-semibold"><Webhook className="h-4 w-4 text-ink-2" />Inbound replies</h2>
          <p className="mt-1 text-[13px] text-ink-2">Point your email provider’s inbound-parse webhook (SendGrid, Mailgun, Postmark) here so replies are sorted automatically. In sandbox mode, use “Simulate a reply” in the Outbox.</p>
          <div className="mt-3 grid gap-2 text-[13px]">
            {[['POST', `${window.location.origin}/api/inbound/email`], ['Header', `X-AgentJerry-Key: ${d.inbound_key}`], ['Body (JSON)', '{ "from_email", "from_name", "subject", "text" }']].map(([k, v]) => (
              <div key={k} className="flex items-center gap-3 rounded-lg bg-paper border border-line px-3 py-2">
                <span className="w-24 shrink-0 text-xs font-semibold text-ink-3">{k}</span>
                <code className="flex-1 min-w-0 truncate text-xs">{v}</code>
                <button className="btn-ghost btn-sm !px-2" aria-label={`Copy ${k}`} onClick={() => { navigator.clipboard?.writeText(v); toast('Copied') }}><Copy className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card p-5 mt-5">
        <h2 className="flex items-center gap-2 text-[16px] font-semibold"><Cpu className="h-4 w-4 text-brand" />AI engine</h2>
        <p className="mt-1 text-[13.5px]">{d.engine.enabled ? <>Using <b>{d.engine.model}</b> for understanding and writing, with the offline engine as an automatic fallback.</> : <>Using the <b>offline engine</b>: deterministic understanding and grounded templates, no internet needed. Set <code className="text-xs bg-paper px-1 rounded">ANTHROPIC_API_KEY</code> on the server to use Claude.</>}</p>
        <p className="mt-1 text-xs text-ink-3">Either way, the AI only proposes. Validation, safety checks and execution are deterministic code.</p>
      </section>

      <section className="card p-5 mt-5">
        <h2 className="flex items-center gap-2 text-[16px] font-semibold"><Wrench className="h-4 w-4 text-ink-2" />Tools agents can use</h2>
        <p className="mt-1 text-[13px] text-ink-2">Agents can only take these actions. Sensitive tools always sit behind the safety policy.</p>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {d.tools.map(t => { const f = CATEGORY_FIELD[t.category] || 'action'; const I = TOOL_ICON[t.name]; return (
            <li key={t.name} className="flex items-start gap-3 rounded-lg border border-line p-3">
              <span className="h-8 w-8 rounded-lg grid place-items-center shrink-0" style={{ background: BG[f], color: HEX[f] }}>{I && <I className="h-4 w-4" />}</span>
              <span className="min-w-0"><span className="flex items-center gap-1.5 text-[13.5px] font-semibold">{t.label}{t.sensitive && <Lock className="h-3 w-3 text-f-approval" />}</span><span className="block text-xs text-ink-2">{t.description}</span></span>
            </li>) })}
        </ul>
      </section>

      {admin && (
        <section className="card p-5 mt-5 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[240px]"><div className="text-[14px] font-semibold">Reset demo workspace</div><div className="text-[13px] text-ink-2">Restore the sample files, knowledge and finance agent. Deletes everything else.</div></div>
          <button className="btn-danger" onClick={() => setReset(true)}><RotateCcw className="h-4 w-4" />Reset workspace</button>
        </section>
      )}
      <Modal open={reset} onClose={() => setReset(false)} title="Reset the demo workspace?"
        footer={<><button className="btn-ghost" onClick={() => setReset(false)}>Cancel</button><button className="btn bg-f-approval text-white" onClick={doReset} disabled={resetting}>{resetting && <Spinner />}Reset everything</button></>}>
        <p className="text-[14px]">All agents, runs, approvals, memory and uploads are deleted and the sample data is restored. You’ll sign in again with the demo account.</p>
      </Modal>
    </div>
  )
}

type Supp = { id: number; email: string; reason: string; source: string; created_by: string; created_at: string }

function DoNotContact() {
  const list = useApi<Supp[]>('/suppressions')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const add = async () => {
    setBusy(true)
    try { const r = await api('/suppressions', { body: { emails: text, reason: 'Added manually' } }); toast.success(`Added ${r.added}${r.already_listed ? ` · ${r.already_listed} already listed` : ''}`); setText(''); list.reload() }
    catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }
  const remove = async (s: Supp) => { try { await api(`/suppressions/${s.id}`, { method: 'DELETE' }); toast(`${s.email} can be emailed again`); list.reload() } catch (e: any) { toast.error(e.message) } }
  return (
    <section className="card p-5 mt-5">
      <h2 className="flex items-center gap-2 text-[16px] font-semibold"><Ban className="h-4 w-4" style={{ color: HEX.approval }} />Do-not-contact list</h2>
      <p className="mt-1 text-[13px] text-ink-2">No agent will ever email these people. It’s checked before drafting and again at the moment of sending. Unsubscribe replies are added automatically.</p>
      <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); text.trim() && add() }}>
        <input className="input" placeholder="name@company.com, another@company.com" value={text} onChange={e => setText(e.target.value)} aria-label="Emails to add" />
        <button className="btn-primary h-10" disabled={busy || !text.trim()}>{busy ? <Spinner /> : 'Add'}</button>
      </form>
      <ul className="mt-3 divide-y divide-line rounded-lg border border-line">
        {!list.data?.length && <li className="px-3 py-3 text-[13px] text-ink-3">Nobody yet.</li>}
        {list.data?.map(s => (
          <li key={s.id} className="flex items-center gap-3 px-3 py-2">
            <span className="min-w-0 flex-1"><span className="block text-[13.5px] font-semibold truncate">{s.email}</span><span className="block text-xs text-ink-3 truncate">{s.reason} · {s.source === 'reply' ? 'from a reply' : `added by ${s.created_by}`}</span></span>
            <button className="btn-ghost btn-sm !px-2" onClick={() => remove(s)} aria-label={`Remove ${s.email}`}><X className="h-4 w-4" /></button>
          </li>
        ))}
      </ul>
    </section>
  )
}
