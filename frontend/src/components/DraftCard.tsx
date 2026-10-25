import clsx from 'clsx'
import { AlertTriangle, BookOpen } from 'lucide-react'
import type { Draft } from '../lib/types'

export function DraftCard({ d, compact }: { d: Draft; compact?: boolean }) {
  return (
    <article className="rounded-xl border border-line bg-surface overflow-hidden">
      <header className="px-4 py-2.5 border-b border-line bg-paper/50 text-[12.5px]">
        <div className="flex gap-2"><span className="w-14 text-ink-3 shrink-0">To</span><span className="text-ink truncate"><b className="font-semibold">{d.to_name}</b> &lt;{d.to}&gt;</span></div>
        <div className="flex gap-2 mt-0.5"><span className="w-14 text-ink-3 shrink-0">Subject</span><span className="text-ink font-semibold truncate">{d.subject}</span></div>
      </header>
      <pre className={clsx('px-4 py-3 whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed text-ink', compact && 'max-h-[180px] overflow-hidden relative')}>{d.body}</pre>
      {(!!d.citations?.length || !!d.flags?.length) && (
        <footer className="px-4 py-2.5 border-t border-line space-y-1.5">
          {d.flags?.map((f, i) => (
            <div key={i} className={clsx('flex items-center gap-1.5 text-xs', f.level === 'error' ? 'text-f-approval' : 'text-[#8A5D00]')}>
              <AlertTriangle className="h-3.5 w-3.5" />{f.text}
            </div>
          ))}
          {d.citations?.map((c, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-f-knowledge" title={c.text}>
              <BookOpen className="h-3.5 w-3.5 mt-px shrink-0" />
              <span>Grounded in <b className="font-semibold">{c.source_title}</b>{c.section ? ` › ${c.section}` : ''}</span>
            </div>
          ))}
        </footer>
      )}
    </article>
  )
}
