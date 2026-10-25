import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity, Bell, Bot, BookOpen, Check, Cpu, Database, Hourglass, Inbox, BarChart3, Gauge, LayoutGrid, LogOut, MailOpen, Menu, Play, Plus, Users,
  Send, Settings, X, XCircle,
} from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'

type Counts = { unread: number; items: { id: number; kind: string; title: string; body: string; link: string; read: boolean; at: string }[] }

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-2" aria-label="AgentJerry home">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden><rect width="32" height="32" rx="9" fill="#26337A" /><path d="M11 9.5h10v2.6h-3.4v8.1c0 2.9-1.7 4.6-4.6 4.6-1 0-1.9-.2-2.6-.5l.5-2.5c.5.2 1 .3 1.6.3 1.2 0 1.8-.7 1.8-2.1v-7.9H11z" fill="#fff" /><circle cx="23" cy="21.5" r="2.3" fill="#F5B83D" /></svg>
      <span className="font-display text-[18px] font-semibold tracking-tight">AgentJerry</span>
    </Link>
  )
}

function NavItem({ to, icon, label, badge, end, tone }: { to: string; icon: ReactNode; label: string; badge?: number; end?: boolean; tone?: 'soft' }) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => clsx(
      'group relative flex items-center gap-2.5 h-9 px-2.5 rounded-lg text-[13.5px] font-semibold transition-colors',
      isActive ? 'bg-ink/[0.06] text-ink' : 'text-ink-2 hover:bg-ink/[0.04] hover:text-ink')}>
      {({ isActive }) => (<>
        {isActive && <motion.span layoutId="nav-active" className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-ink" />}
        <span className={clsx('transition-colors', isActive ? 'text-ink' : 'text-ink-3 group-hover:text-ink-2')}>{icon}</span>
        <span className="flex-1">{label}</span>
        {!!badge && <span className={clsx('min-w-[20px] h-5 px-1.5 rounded-full text-2xs font-bold grid place-items-center tabular', tone === 'soft' ? 'bg-f-action text-white' : 'bg-f-approval text-white')}>{badge}</span>}
      </>)}
    </NavLink>
  )
}

function Sidebar({ pending, replies, onNavigate }: { pending: number; replies: number; onNavigate?: () => void }) {
  const { user, org, logout } = useAuth()
  const i = 'h-[18px] w-[18px]'
  return (
    <div className="flex flex-col h-full" onClick={e => { if ((e.target as HTMLElement).closest('a')) onNavigate?.() }}>
      <div className="h-16 flex items-center px-3"><Logo /></div>
      <div className="px-3">
        <Link to="/studio" className="btn-primary w-full h-10"><Plus className="h-4 w-4" />Create agent</Link>
      </div>
      <nav className="mt-5 px-3 space-y-0.5" aria-label="Main">
        <NavItem to="/" end icon={<LayoutGrid className={i} />} label="Home" />
        <NavItem to="/agents" icon={<Bot className={i} />} label="Agents" />
        <NavItem to="/approvals" icon={<Inbox className={i} />} label="Approvals" badge={pending} />
        <NavItem to="/replies" icon={<MailOpen className={i} />} label="Replies" badge={replies} tone="soft" />
        <NavItem to="/runs" icon={<Play className={i} />} label="Runs" />
        <NavItem to="/insights" icon={<BarChart3 className={i} />} label="Insights" />
      </nav>
      <div className="mt-6 px-5 text-2xs font-semibold text-ink-3">Workspace</div>
      <nav className="mt-1.5 px-3 space-y-0.5" aria-label="Workspace">
        <NavItem to="/data" icon={<Database className={i} />} label="Data files" />
        <NavItem to="/knowledge" icon={<BookOpen className={i} />} label="Knowledge" />
        <NavItem to="/outbox" icon={<Send className={i} />} label="Outbox" />
        <NavItem to="/team" icon={<Users className={i} />} label="Team" />
        <NavItem to="/activity" icon={<Activity className={i} />} label="Activity log" />
        <NavItem to="/quality" icon={<Gauge className={i} />} label="Engine quality" />
        <NavItem to="/settings" icon={<Settings className={i} />} label="Settings" />
      </nav>
      <div className="mt-auto p-3">
        <div className="flex items-center gap-2.5 p-2 rounded-xl border border-line bg-paper/60">
          <div className="h-8 w-8 rounded-full bg-brand text-white grid place-items-center text-xs font-bold shrink-0">
            {user?.name.split(' ').map(s => s[0]).slice(0, 2).join('')}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold truncate">{user?.name}</div>
            <div className="text-2xs text-ink-3 truncate">{user?.title} · {org?.name}</div>
          </div>
          <button className="btn-ghost btn-sm !px-1.5" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut className="h-4 w-4" /></button>
        </div>
      </div>
    </div>
  )
}

const KIND_ICON: Record<string, ReactNode> = {
  approval: <Hourglass className="h-3.5 w-3.5 text-f-approval" />,
  run_completed: <Check className="h-3.5 w-3.5 text-f-action" />,
  run_failed: <XCircle className="h-3.5 w-3.5 text-f-approval" />,
  info: <Bell className="h-3.5 w-3.5 text-ink-3" />,
  reply: <MailOpen className="h-3.5 w-3.5 text-f-action" />,
}

function Notifications({ data, reload }: { data?: Counts; reload: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const nav = useNavigate()
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const toggle = async () => {
    setOpen(o => !o)
    if (!open && data?.unread) { await api('/notifications/read', { method: 'POST' }); reload() }
  }
  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost !px-2 relative" onClick={toggle} aria-label={`Notifications${data?.unread ? `, ${data.unread} unread` : ''}`}>
        <Bell className="h-[18px] w-[18px]" />
        {!!data?.unread && <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-f-approval ring-2 ring-paper" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }} className="absolute right-0 mt-2 w-[360px] max-w-[calc(100vw-24px)] card shadow-pop z-40 overflow-hidden origin-top-right">
            <div className="px-4 h-11 flex items-center border-b border-line text-[13.5px] font-semibold">Notifications</div>
            <div className="max-h-[420px] overflow-y-auto thin-scroll">
              {!data?.items.length && <div className="p-6 text-center text-ink-3 text-[13px]">You’re all caught up.</div>}
              {data?.items.map(n => (
                <button key={n.id} onClick={() => { setOpen(false); if (n.link) nav(n.link) }}
                  className="w-full text-left flex gap-3 px-4 py-3 hover:bg-paper border-b border-line last:border-0">
                  <span className="mt-0.5">{KIND_ICON[n.kind] || KIND_ICON.info}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-semibold text-ink">{n.title}</span>
                    {n.body && <span className="block text-xs text-ink-2 line-clamp-2">{n.body}</span>}
                    <span className="block text-2xs text-ink-3 mt-0.5">{timeAgo(n.at)}</span>
                  </span>
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function EngineBadge() {
  const { engine } = useAuth()
  const on = engine?.enabled
  return (
    <span title={on ? `Using ${engine?.model}` : 'Deterministic offline engine — works without internet. Add an API key to use Claude.'}
      className="hidden sm:inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full border border-line bg-surface text-xs font-semibold text-ink-2">
      <Cpu className="h-3.5 w-3.5" />{on ? 'Claude engine' : 'Offline engine'}
      <span className={clsx('h-1.5 w-1.5 rounded-full', on ? 'bg-f-action' : 'bg-f-trigger')} />
    </span>
  )
}

export function Layout() {
  const [drawer, setDrawer] = useState(false)
  const loc = useLocation()
  const notes = useApi<Counts>('/notifications', { poll: 5000 })
  const approvals = useApi<any[]>('/approvals?status=pending&mine=true', { poll: 5000 })
  const pending = approvals.data?.length || 0
  const replyCounts = useApi<{ open_counts: Record<string, number> }>('/replies?status=open', { poll: 8000 })
  const replies = Object.values(replyCounts.data?.open_counts || {}).reduce((a, b) => a + b, 0)
  useEffect(() => { setDrawer(false); window.scrollTo(0, 0) }, [loc.pathname])
  useEffect(() => { approvals.reload(); notes.reload(); replyCounts.reload() }, [loc.pathname]) // eslint-disable-line

  return (
    <div className="min-h-screen lg:pl-[248px]">
      <aside className="hidden lg:block fixed inset-y-0 left-0 w-[248px] bg-surface border-r border-line z-30">
        <Sidebar pending={pending} replies={replies} />
      </aside>
      <AnimatePresence>
        {drawer && (
          <motion.div className="fixed inset-0 z-50 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-ink/30" onClick={() => setDrawer(false)} />
            <motion.aside initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }} transition={{ type: 'spring', stiffness: 400, damping: 38 }}
              className="absolute inset-y-0 left-0 w-[272px] bg-surface shadow-pop">
              <button className="absolute top-4 right-3 btn-ghost btn-sm !px-2" onClick={() => setDrawer(false)} aria-label="Close menu"><X className="h-4 w-4" /></button>
              <Sidebar pending={pending} replies={replies} onNavigate={() => setDrawer(false)} />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
      <header className="sticky top-0 z-20 h-14 flex items-center gap-2 px-4 sm:px-6 bg-paper/85 backdrop-blur border-b border-line/70">
        <button className="lg:hidden btn-ghost !px-2" onClick={() => setDrawer(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
        <div className="lg:hidden"><Logo /></div>
        <div className="flex-1" />
        <EngineBadge />
        <Notifications data={notes.data} reload={notes.reload} />
      </header>
      <main className="px-4 sm:px-6 lg:px-8 py-6 lg:py-8 max-w-[1320px]">
        <Outlet />
      </main>
    </div>
  )
}
