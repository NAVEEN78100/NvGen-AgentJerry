import clsx from 'clsx'
import { motion } from 'framer-motion'
import { ArrowRight, Check, FileSpreadsheet, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { api } from '../lib/api'
import type { Question } from '../lib/types'
import { Spinner } from './ui'

/** One clarification question. Choice/file questions answer on click; email/text on submit. */
export function QuestionCard({ q, index, onAnswer, busy }: { q: Question; index: number; onAnswer: (id: string, value: string) => void; busy: boolean }) {
  const [text, setText] = useState(q.default || '')
  const [picked, setPicked] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const pick = (v: string) => { if (busy) return; setPicked(v); onAnswer(q.id, v) }

  const upload = async (f: File) => {
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', f)
      const r = await api('/files', { form })
      toast.success(`Uploaded ${r.name} — ${r.row_count} rows`)
      pick(r.id)
    } catch (e: any) { toast.error(e.message) } finally { setUploading(false) }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 * index }}
      className="rounded-xl border border-line bg-surface p-4">
      <div className="text-[14.5px] font-semibold text-ink">{q.prompt}</div>
      <p className="mt-0.5 text-[12.5px] text-ink-2">{q.why}</p>

      {(q.kind === 'choice' || q.kind === 'file') && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {q.options.map(o => (
            <button key={o.value} onClick={() => pick(o.value)} disabled={busy}
              className={clsx('group text-left rounded-lg border px-3 py-2.5 transition-all flex items-start gap-2.5',
                picked === o.value ? 'border-ink bg-ink/[0.03]' : 'border-line hover:border-line-strong hover:bg-paper')}>
              <span className={clsx('mt-0.5 h-4 w-4 rounded-full border grid place-items-center shrink-0 transition-colors',
                picked === o.value ? 'bg-ink border-ink text-white' : 'border-line-strong group-hover:border-ink-3')}>
                {picked === o.value && (busy ? <Spinner className="h-2.5 w-2.5" /> : <Check className="h-2.5 w-2.5" strokeWidth={3.5} />)}
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-[13.5px] font-semibold text-ink">
                  {q.kind === 'file' && <FileSpreadsheet className="h-3.5 w-3.5 text-f-data shrink-0" />}
                  <span className="truncate">{o.label}</span>
                </span>
                {o.hint && <span className="block text-xs text-ink-3">{o.hint}</span>}
              </span>
            </button>
          ))}
          {q.kind === 'file' && (
            <>
              <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
              <button onClick={() => fileRef.current?.click()} disabled={busy || uploading}
                className="rounded-lg border border-dashed border-line-strong px-3 py-2.5 flex items-center gap-2 text-[13.5px] font-semibold text-ink-2 hover:bg-paper hover:text-ink">
                {uploading ? <Spinner /> : <Upload className="h-4 w-4" />} Upload a spreadsheet
              </button>
            </>
          )}
        </div>
      )}

      {(q.kind === 'email' || q.kind === 'text') && (
        <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); if (text.trim()) onAnswer(q.id, text.trim()) }}>
          <input className="input" type={q.kind === 'email' ? 'email' : 'text'} placeholder={q.placeholder} value={text}
            onChange={e => setText(e.target.value)} required autoFocus />
          <button className="btn-primary h-10" disabled={busy || !text.trim()}>{busy ? <Spinner /> : <ArrowRight className="h-4 w-4" />}</button>
        </form>
      )}
    </motion.div>
  )
}
