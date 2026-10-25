import clsx from 'clsx'
import { motion } from 'framer-motion'
import { AlertTriangle, Check, X } from 'lucide-react'
import type { Validation } from '../lib/types'

export function ValidationList({ validation, animate = false }: { validation: Validation; animate?: boolean }) {
  return (
    <ul className="space-y-2">
      {validation.checks.map((c, i) => (
        <motion.li key={c.id} initial={animate ? { opacity: 0, x: -6 } : false} animate={{ opacity: 1, x: 0 }}
          transition={{ delay: animate ? 0.05 * i : 0 }} className="flex items-start gap-2.5">
          <span className={clsx('mt-0.5 h-[18px] w-[18px] rounded-full grid place-items-center shrink-0 text-white',
            c.status === 'pass' && 'bg-f-action', c.status === 'warn' && 'bg-f-trigger', c.status === 'fail' && 'bg-f-approval')}>
            {c.status === 'pass' && <Check className="h-3 w-3" strokeWidth={3.5} />}
            {c.status === 'warn' && <AlertTriangle className="h-2.5 w-2.5" strokeWidth={3} />}
            {c.status === 'fail' && <X className="h-3 w-3" strokeWidth={3.5} />}
          </span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-ink">{c.label}</div>
            <div className="text-xs text-ink-2">{c.detail}</div>
          </div>
        </motion.li>
      ))}
    </ul>
  )
}

export function ValidationBadge({ validation }: { validation: Validation }) {
  const passed = validation.checks.filter(c => c.status === 'pass').length
  return (
    <span className={clsx('inline-flex items-center gap-1 h-6 px-2 rounded-full text-xs font-semibold',
      validation.status === 'pass' ? 'bg-f-actionbg text-f-action' : validation.status === 'warn' ? 'bg-f-triggerbg text-[#8A5D00]' : 'bg-f-approvalbg text-f-approval')}>
      {validation.status === 'fail' ? <X className="h-3 w-3" /> : <Check className="h-3 w-3" />}
      {passed}/{validation.checks.length} checks passed
    </span>
  )
}
