import { BookOpen, FileText, Search, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { EmptyState, ErrorNote, Modal, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { HEX } from '../lib/fields'
import { timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { KnowledgeDoc, Passage } from '../lib/types'

function highlight(text: string, q: string) {
  const words = q.toLowerCase().split(/\W+/).filter(w => w.length > 3)
  if (!words.length) return text
  const re = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  return text.split(re).map((p, i) => re.test(p) ? <mark key={i} className="bg-f-knowledgebg text-ink rounded px-0.5">{p}</mark> : <span key={i}>{p}</span>)
}

export function Knowledge() {
  const list = useApi<KnowledgeDoc[]>('/knowledge')
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Passage[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [doc, setDoc] = useState<(KnowledgeDoc & { chunks: { idx: number; section: string; text: string }[] }) | null>(null)
  const ref = useRef<HTMLInputElement>(null)

  const search = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (q.trim().length < 2) return
    setSearching(true)
    try { setHits(await api<Passage[]>('/knowledge/search', { body: { query: q.trim() } })) } catch (err: any) { toast.error(err.message) } finally { setSearching(false) }
  }
  const upload = async (f: File) => {
    setUploading(true)
    try { const form = new FormData(); form.append('file', f); const r = await api<KnowledgeDoc>('/knowledge', { form }); toast.success(`${r.title}: ${r.chunk_count} passages indexed`); list.reload() }
    catch (e: any) { toast.error(e.message) } finally { setUploading(false) }
  }
  const remove = async (d: KnowledgeDoc) => { try { await api(`/knowledge/${d.id}`, { method: 'DELETE' }); toast(`Removed ${d.title}`); list.reload() } catch (e: any) { toast.error(e.message) } }

  return (
    <div>
      <PageHeader title="Knowledge" subtitle="Documents agents look things up in before they write, so every email uses your real facts — prices, policies, product details — instead of generic text."
        actions={<><input ref={ref} type="file" accept=".pdf,.txt,.md" className="hidden" onChange={e => { e.target.files?.[0] && upload(e.target.files[0]); e.target.value = '' }} />
          <button className="btn-primary" onClick={() => ref.current?.click()} disabled={uploading}>{uploading ? <Spinner /> : <Upload className="h-4 w-4" />}Add document</button></>} />

      <form onSubmit={search} className="card p-1.5 pl-3.5 flex items-center gap-2">
        <Search className="h-4 w-4 text-ink-3" />
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Try it: “late fee on unpaid invoices” or “stock-outs before festivals”" aria-label="Search knowledge"
          className="flex-1 min-w-0 bg-transparent h-9 text-[14px] focus:outline-none placeholder:text-ink-3" />
        <button className="btn-primary h-9" disabled={searching || q.trim().length < 2}>{searching ? <Spinner /> : 'Search'}</button>
      </form>
      {hits && (
        <div className="mt-3 space-y-2">
          {!hits.length && <div className="card p-4 text-[13px] text-ink-2">No passage matches that. Agents would write without extra grounding for this topic.</div>}
          {hits.map(h => (
            <div key={h.chunk_id} className="card p-4">
              <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: HEX.knowledge }}><BookOpen className="h-3.5 w-3.5" />{h.source_title}{h.section && ` › ${h.section}`}<span className="ml-auto text-ink-3 font-medium tabular">relevance {h.score.toFixed(1)}</span></div>
              <p className="mt-1.5 text-[13.5px] text-ink-2 leading-relaxed">{highlight(h.text, q)}</p>
            </div>
          ))}
        </div>
      )}

      <h2 className="mt-8 mb-3 text-[15px] font-semibold">Documents</h2>
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-40" />}
      {list.data && !list.data.length && <div className="card"><EmptyState icon={<BookOpen className="h-5 w-5" />} title="No documents yet" body="Add a product brief, price list or policy (PDF, TXT or Markdown)." /></div>}
      <div className="grid gap-3 md:grid-cols-3">
        {list.data?.map(d => (
          <div key={d.id} className="card p-4">
            <div className="flex items-start gap-3">
              <span className="h-10 w-10 rounded-xl grid place-items-center bg-f-knowledgebg text-f-knowledge shrink-0"><FileText className="h-5 w-5" /></span>
              <div className="min-w-0 flex-1">
                <button className="text-[14px] font-semibold hover:underline text-left" onClick={async () => setDoc(await api(`/knowledge/${d.id}`))}>{d.title}</button>
                <div className="text-xs text-ink-3">{d.source_type.toUpperCase()} · {d.chunk_count} passages · {timeAgo(d.created_at)}</div>
              </div>
              <button className="btn-ghost btn-sm !px-2" onClick={() => remove(d)} aria-label={`Remove ${d.title}`}><Trash2 className="h-4 w-4" /></button>
            </div>
          </div>
        ))}
      </div>
      <Modal open={!!doc} onClose={() => setDoc(null)} title={doc?.title || ''} wide>
        <p className="text-xs text-ink-3 mb-3">Split into {doc?.chunk_count} passages so the agent retrieves only what’s relevant.</p>
        <div className="space-y-2">{doc?.chunks.map(c => <div key={c.idx} className="rounded-lg border border-line p-3"><div className="text-2xs font-semibold text-ink-3">#{c.idx + 1} {c.section}</div><p className="text-[13px] mt-1">{c.text}</p></div>)}</div>
      </Modal>
    </div>
  )
}
