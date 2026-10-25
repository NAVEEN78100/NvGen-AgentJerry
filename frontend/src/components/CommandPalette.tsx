import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity, BarChart3, Bot, BookOpen, CornerDownLeft, Database, Gauge, Inbox, LayoutGrid, MailOpen, Play, Plus, Search,
  Send, Settings, Sparkles, Users,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { AgentBrief } from '../lib/types'
import { AgentStatusPill } from './ui'

type Item = { id: string; group: string; label: string; hint?: string; icon: ReactNode; run: () => void; right?: ReactNode }

export function useCommandPalette() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(o => !o) }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])
  return { open, setOpen }
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  const [agents, setAgents] = useState<AgentBrief[]>([])
  const [templates, setTemplates] = useState<{ id: string; title: string; prompt: string }[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    setQ(''); setIdx(0)
    setTimeout(() => inputRef.current?.focus(), 30)
    api<AgentBrief[]>('/agents').then(setAgents).catch(() => {})
    api('/studio/templates').then(setTemplates).catch(() => {})
  }, [open])

  const go = (path: string, state?: any) => () => { onClose(); nav(path, state ? { state } : undefined) }
  const i = 'h-4 w-4'
  const items: Item[] = useMemo(() => {
    const pages: Item[] = [
      { id: 'p-new', group: 'Actions', label: 'Create an agent', hint: 'Describe a task in plain words', icon: <Plus className={i} />, run: go('/studio') },
      ...(q.trim().length > 8 ? [{ id: 'p-build', group: 'Actions', label: `Build an agent: “${q.trim().slice(0, 60)}”`, icon: <Sparkles className={i} />, run: go('/studio', { prompt: q.trim() }) }] : []),
      { id: 'home', group: 'Go to', label: 'Home', icon: <LayoutGrid className={i} />, run: go('/') },
      { id: 'agents', group: 'Go to', label: 'Agents', icon: <Bot className={i} />, run: go('/agents') },
      { id: 'approvals', group: 'Go to', label: 'Approvals', icon: <Inbox className={i} />, run: go('/approvals') },
      { id: 'replies', group: 'Go to', label: 'Replies', icon: <MailOpen className={i} />, run: go('/replies') },
      { id: 'runs', group: 'Go to', label: 'Runs', icon: <Play className={i} />, run: go('/runs') },
      { id: 'insights', group: 'Go to', label: 'Insights', icon: <BarChart3 className={i} />, run: go('/insights') },
      { id: 'data', group: 'Go to', label: 'Data files', icon: <Database className={i} />, run: go('/data') },
      { id: 'knowledge', group: 'Go to', label: 'Knowledge', icon: <BookOpen className={i} />, run: go('/knowledge') },
      { id: 'outbox', group: 'Go to', label: 'Outbox', icon: <Send className={i} />, run: go('/outbox') },
      { id: 'team', group: 'Go to', label: 'Team', icon: <Users className={i} />, run: go('/team') },
      { id: 'activity', group: 'Go to', label: 'Activity log', icon: <Activity className={i} />, run: go('/activity') },
      { id: 'quality', group: 'Go to', label: 'Engine quality', icon: <Gauge className={i} />, run: go('/quality') },
      { id: 'settings', group: 'Go to', label: 'Settings', hint: 'Safety policy, do-not-contact, email', icon: <Settings className={i} />, run: go('/settings') },
    ]
    const ag: Item[] = agents.map(a => ({ id: `a-${a.id}`, group: 'Agents', label: a.name, hint: a.trigger_label, icon: <Bot className={i} />,
      run: go(a.status === 'draft' ? `/studio/${a.id}` : `/agents/${a.id}`), right: <AgentStatusPill status={a.status} size="sm" /> }))
    const tp: Item[] = templates.map(t => ({ id: `t-${t.id}`, group: 'Start from an example', label: t.title, hint: t.prompt, icon: <Sparkles className={i} />, run: go('/studio', { prompt: t.prompt }) }))
    const all = [...pages, ...ag, ...tp]
    const norm = (t: string) => t.toLowerCase().replace(/[-_]/g, ' ').replace(/s\b/g, '')
    const s = norm(q.trim())
    if (!s) return all.filter(x => x.group !== 'Start from an example')
    return all.filter(x => x.id === 'p-build' || norm(`${x.label} ${x.hint || ''} ${x.group}`).includes(s))
  }, [q, agents, templates]) // eslint-disable-line

  useEffect(() => { setIdx(0) }, [q])
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setIdx(x => Math.min(items.length - 1, x + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx(x => Math.max(0, x - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); items[idx]?.run() }
    else if (e.key === 'Escape') onClose()
  }
  let lastGroup = ''

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] flex items-start justify-center p-4 pt-[12vh]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} />
          <motion.div role="dialog" aria-label="Command palette" initial={{ y: -8, scale: 0.98, opacity: 0 }} animate={{ y: 0, scale: 1, opacity: 1 }} exit={{ y: -6, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 36 }} className="relative w-full max-w-[600px] card shadow-pop overflow-hidden">
            <div className="flex items-center gap-3 px-4 border-b border-line">
              <Search className="h-4 w-4 text-ink-3" />
              <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} aria-label="Search or describe a task"
                placeholder="Search, jump to a page, or describe a new task…" className="flex-1 h-14 bg-transparent text-[15px] focus:outline-none placeholder:text-ink-3" />
              <span className="kbd">Esc</span>
            </div>
            <ul className="max-h-[52vh] overflow-y-auto thin-scroll py-2" role="listbox">
              {!items.length && <li className="px-4 py-6 text-center text-[13px] text-ink-3">Nothing matches. Keep typing to build an agent from it.</li>}
              {items.map((it, k) => {
                const header = it.group !== lastGroup ? (lastGroup = it.group) : null
                return (
                  <li key={it.id}>
                    {header && <div className="px-4 pt-2 pb-1 text-2xs font-semibold text-ink-3">{header}</div>}
                    <button role="option" aria-selected={k === idx} onMouseEnter={() => setIdx(k)} onClick={it.run}
                      className={clsx('w-full text-left flex items-center gap-3 px-4 py-2', k === idx ? 'bg-brand-soft/70' : '')}>
                      <span className="text-ink-2">{it.icon}</span>
                      <span className="min-w-0 flex-1"><span className="block text-[13.5px] font-semibold truncate">{it.label}</span>{it.hint && <span className="block text-xs text-ink-3 truncate">{it.hint}</span>}</span>
                      {it.right}
                      {k === idx && <CornerDownLeft className="h-3.5 w-3.5 text-ink-3" />}
                    </button>
                  </li>
                )
              })}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
