import { Copy, KeyRound, UserPlus, Users } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorNote, Modal, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'

type Member = {
  id: string; name: string; email: string; role: string; title: string; agents_built: number; approves_for: string[]
  approvals_decided: number; approvals_pending: number; joined_at: string; is_me: boolean
}

function Avatar({ name }: { name: string }) {
  return <span className="h-10 w-10 rounded-full bg-brand text-white grid place-items-center text-sm font-bold shrink-0">{name.split(' ').map(s => s[0]).slice(0, 2).join('')}</span>
}

export function Team() {
  const { user } = useAuth()
  const admin = user?.role === 'admin'
  const team = useApi<Member[]>('/team')
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', title: '', role: 'member' })
  const [created, setCreated] = useState<{ name: string; email: string; temporary_password: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [pw, setPw] = useState({ current: '', new: '' })

  const add = async () => {
    setBusy(true)
    try { const r = await api('/team', { body: form }); setCreated(r); setAdding(false); setForm({ name: '', email: '', title: '', role: 'member' }); team.reload() }
    catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }
  const setRole = async (m: Member, role: string) => {
    try { await api(`/team/${m.id}`, { method: 'PATCH', body: { role } }); toast.success(`${m.name} is now ${role === 'admin' ? 'an admin' : 'a member'}`); team.reload() }
    catch (e: any) { toast.error(e.message); team.reload() }
  }
  const changePw = async () => {
    setBusy(true)
    try { await api('/auth/password', { body: pw }); toast.success('Password changed'); setPw({ current: '', new: '' }) }
    catch (e: any) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="max-w-[960px]">
      <PageHeader title="Team" subtitle="Who builds agents and who approves what they send. Assign an approver on any agent; turn on the four-eyes rule in Settings to require a second person."
        actions={admin && <button className="btn-primary" onClick={() => setAdding(true)}><UserPlus className="h-4 w-4" />Add member</button>} />
      {team.error && <ErrorNote message={team.error} onRetry={team.reload} />}
      {!team.data && !team.error && <Skeleton className="h-64" />}
      <div className="card divide-y divide-line">
        {team.data?.map(m => (
          <div key={m.id} className="flex flex-wrap items-center gap-4 p-4">
            <Avatar name={m.name} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2"><span className="text-[14.5px] font-semibold">{m.name}</span>{m.is_me && <span className="text-2xs font-semibold text-ink-3">You</span>}</div>
              <div className="text-xs text-ink-2">{m.title || '—'} · {m.email} · joined {timeAgo(m.joined_at)}</div>
              {!!m.approves_for.length && <div className="mt-1 text-xs text-ink-2">Approves: <span className="text-ink">{m.approves_for.join(', ')}</span></div>}
            </div>
            <div className="flex gap-5 text-center text-xs text-ink-3">
              <div><div className="font-display text-[18px] font-semibold text-ink tabular">{m.agents_built}</div>agents built</div>
              <div><div className="font-display text-[18px] font-semibold text-ink tabular">{m.approvals_decided}</div>decisions</div>
              <div><div className={`font-display text-[18px] font-semibold tabular ${m.approvals_pending ? 'text-f-approval' : 'text-ink'}`}>{m.approvals_pending}</div>waiting</div>
            </div>
            {admin ? (
              <select aria-label={`Role for ${m.name}`} className="input h-9 w-[120px]" value={m.role} onChange={e => setRole(m, e.target.value)}>
                <option value="admin">Admin</option><option value="member">Member</option>
              </select>
            ) : <span className="text-xs font-semibold text-ink-2 w-[120px] text-right">{m.role === 'admin' ? 'Admin' : 'Member'}</span>}
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-3"><b>Admins</b> change safety policy, email delivery and the team, and can approve anything. <b>Members</b> build agents and approve what’s assigned to them.</p>

      <section className="card p-5 mt-6 max-w-[520px]">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold"><KeyRound className="h-4 w-4 text-ink-2" />Change your password</h2>
        <form className="mt-3 grid gap-3" onSubmit={e => { e.preventDefault(); changePw() }}>
          <div><label className="label" htmlFor="cur">Current password</label><input id="cur" type="password" className="input" value={pw.current} onChange={e => setPw(p => ({ ...p, current: e.target.value }))} required autoComplete="current-password" /></div>
          <div><label className="label" htmlFor="new">New password</label><input id="new" type="password" className="input" minLength={8} value={pw.new} onChange={e => setPw(p => ({ ...p, new: e.target.value }))} required autoComplete="new-password" /><p className="mt-1 text-xs text-ink-3">At least 8 characters.</p></div>
          <div><button className="btn-secondary" disabled={busy || pw.new.length < 8}>Change password</button></div>
        </form>
      </section>

      <Modal open={adding} onClose={() => setAdding(false)} title="Add a team member"
        footer={<><button className="btn-ghost" onClick={() => setAdding(false)}>Cancel</button><button className="btn-primary" onClick={add} disabled={busy || !form.name || !form.email}>{busy && <Spinner />}Add member</button></>}>
        <div className="grid gap-3">
          {([['name', 'Full name', 'Divya Nair'], ['email', 'Work email', 'divya@brightpath.example'], ['title', 'Job title', 'Sales Executive']] as const).map(([k, l, ph]) => (
            <div key={k}><label className="label" htmlFor={k}>{l}</label><input id={k} className="input" placeholder={ph} value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} /></div>
          ))}
          <div><label className="label" htmlFor="role">Role</label><select id="role" className="input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}><option value="member">Member</option><option value="admin">Admin</option></select></div>
        </div>
      </Modal>
      <Modal open={!!created} onClose={() => setCreated(null)} title={`${created?.name} can sign in now`} footer={<button className="btn-primary" onClick={() => setCreated(null)}>Done</button>}>
        <p className="text-[14px]">Share these sign-in details. The temporary password is shown only once.</p>
        <div className="mt-3 rounded-lg bg-paper border border-line p-3 text-[13px] space-y-1">
          <div><span className="text-ink-3">Email</span> <b>{created?.email}</b></div>
          <div className="flex items-center gap-2"><span className="text-ink-3">Password</span> <code className="font-semibold">{created?.temporary_password}</code>
            <button className="btn-ghost btn-sm !px-2" aria-label="Copy password" onClick={() => { navigator.clipboard?.writeText(created?.temporary_password || ''); toast('Copied') }}><Copy className="h-3.5 w-3.5" /></button></div>
        </div>
      </Modal>
      {team.data && team.data.length === 1 && <div className="mt-4 text-[13px] text-ink-2 flex items-center gap-2"><Users className="h-4 w-4" />Add a colleague to route approvals to them.</div>}
    </div>
  )
}
