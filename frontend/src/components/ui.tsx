import clsx from 'clsx'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Check, CircleDashed, Hourglass, Loader2, Pause, Pencil, Radio, X, XCircle } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import type { AgentStatus } from '../lib/types'

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('animate-spin', className || 'h-4 w-4')} aria-hidden />
}

const AGENT_STATUS: Record<string, { label: string; cls: string; icon: ReactNode; hint: string }> = {
  draft: { label: 'Needs details', cls: 'bg-f-triggerbg text-[#8A5D00]', icon: <Pencil className="h-3 w-3" />, hint: 'Answer the open questions to build it' },
  ready: { label: 'Ready to test', cls: 'bg-brand-soft text-brand', icon: <CircleDashed className="h-3 w-3" />, hint: 'Run a test before going live' },
  tested: { label: 'Test passed', cls: 'bg-f-actionbg text-f-action', icon: <Check className="h-3 w-3" />, hint: 'Ready to go live' },
  deployed: { label: 'Live', cls: 'bg-f-action text-white', icon: <Radio className="h-3 w-3" />, hint: 'Running on its schedule' },
  paused: { label: 'Paused', cls: 'bg-ink/[0.07] text-ink-2', icon: <Pause className="h-3 w-3" />, hint: 'Schedule is off' },
}

export function AgentStatusPill({ status, size = 'md' }: { status: AgentStatus | string; size?: 'sm' | 'md' }) {
  const s = AGENT_STATUS[status] || AGENT_STATUS.draft
  return (
    <span title={s.hint} className={clsx('inline-flex items-center gap-1 rounded-full font-semibold whitespace-nowrap', s.cls,
      size === 'sm' ? 'h-5 px-2 text-2xs' : 'h-6 px-2.5 text-xs')}>
      {s.icon}{s.label}
    </span>
  )
}

const RUN_STATUS: Record<string, { label: string; cls: string; icon: ReactNode }> = {
  queued: { label: 'Queued', cls: 'text-ink-2 bg-ink/[0.06]', icon: <CircleDashed className="h-3 w-3" /> },
  running: { label: 'Running', cls: 'text-brand bg-brand-soft', icon: <Spinner className="h-3 w-3" /> },
  awaiting_approval: { label: 'Needs approval', cls: 'text-f-approval bg-f-approvalbg', icon: <Hourglass className="h-3 w-3" /> },
  completed: { label: 'Completed', cls: 'text-f-action bg-f-actionbg', icon: <Check className="h-3 w-3" /> },
  failed: { label: 'Failed', cls: 'text-f-approval bg-f-approvalbg', icon: <XCircle className="h-3 w-3" /> },
  cancelled: { label: 'Cancelled', cls: 'text-ink-2 bg-ink/[0.06]', icon: <X className="h-3 w-3" /> },
}

export function RunStatusPill({ status }: { status: string }) {
  const s = RUN_STATUS[status] || RUN_STATUS.queued
  return <span className={clsx('inline-flex items-center gap-1 h-6 px-2 rounded-full text-xs font-semibold whitespace-nowrap', s.cls)}>{s.icon}{s.label}</span>
}

export function ModeTag({ mode }: { mode: string }) {
  return mode === 'test'
    ? <span className="inline-flex h-5 items-center rounded px-1.5 text-2xs font-semibold border border-dashed border-ink-3/60 text-ink-2">Test</span>
    : <span className="inline-flex h-5 items-center rounded px-1.5 text-2xs font-semibold bg-ink text-white">Live</span>
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="mb-6">
      {back}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] leading-tight font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-ink-2 max-w-[68ch]">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}

export function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center text-center py-14 px-6">
      <div className="h-11 w-11 rounded-xl bg-paper border border-line grid place-items-center text-ink-2 mb-4">{icon}</div>
      <h3 className="text-[17px] font-semibold">{title}</h3>
      <p className="mt-1 text-ink-2 max-w-[46ch]">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-f-approval/25 bg-f-approvalbg/60 p-4 text-[13.5px]">
      <AlertTriangle className="h-4 w-4 text-f-approval mt-0.5 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && <button className="btn-secondary btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string; count?: number }[] }) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-line mb-5 overflow-x-auto thin-scroll">
      {items.map(it => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={clsx('relative h-10 px-3 text-[13.5px] font-semibold whitespace-nowrap transition-colors',
            value === it.value ? 'text-ink' : 'text-ink-3 hover:text-ink-2')}>
          {it.label}{it.count != null && <span className="ml-1.5 tabular text-ink-3 font-medium">{it.count}</span>}
          {value === it.value && <motion.span layoutId="tab-underline" className="absolute left-2 right-2 -bottom-px h-[2px] rounded bg-ink" />}
        </button>
      ))}
    </div>
  )
}

export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} />
          <motion.div role="dialog" aria-modal aria-label={title}
            initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 420, damping: 34 }}
            className={clsx('relative w-full card shadow-pop max-h-[86vh] flex flex-col', wide ? 'max-w-3xl' : 'max-w-lg')}>
            <div className="flex items-center justify-between px-5 h-14 border-b border-line">
              <h2 className="text-[16px] font-semibold">{title}</h2>
              <button className="btn-ghost btn-sm !px-2" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
            </div>
            <div className="p-5 overflow-y-auto thin-scroll">{children}</div>
            {footer && <div className="px-5 py-3 border-t border-line flex justify-end gap-2">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'alert' }) {
  return (
    <div className="card p-4">
      <div className="text-[12.5px] font-semibold text-ink-2">{label}</div>
      <div className={clsx('mt-1 font-display text-[30px] leading-none font-semibold tabular', tone === 'alert' && 'text-f-approval')}>{value}</div>
      {hint && <div className="mt-2 text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('skeleton', className)} />
}

export function DeptTag({ dept }: { dept: string }) {
  const map: Record<string, string> = { sales: 'Sales', hr: 'HR', finance: 'Finance', support: 'Support', general: 'General' }
  return <span className="text-2xs font-semibold text-ink-3">{map[dept] || dept}</span>
}
