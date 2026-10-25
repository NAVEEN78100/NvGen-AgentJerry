import { Database, Download, FileSpreadsheet, History, RefreshCw, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { EmptyState, ErrorNote, Modal, PageHeader, Skeleton, Spinner } from '../components/ui'
import { api, getToken } from '../lib/api'
import { timeAgo } from '../lib/format'
import { useApi } from '../lib/hooks'
import type { DataFile } from '../lib/types'

export function DataFiles() {
  const list = useApi<DataFile[]>('/files')
  const [uploading, setUploading] = useState(false)
  const [preview, setPreview] = useState<DataFile | null>(null)
  const [drag, setDrag] = useState(false)
  const ref = useRef<HTMLInputElement>(null)
  const replaceRef = useRef<HTMLInputElement>(null)
  const [replacing, setReplacing] = useState<DataFile | null>(null)
  const [versions, setVersions] = useState<{ file: DataFile; items: { version: number; row_count: number; source: string; note: string; created_by: string; created_at: string; current: boolean }[] } | null>(null)

  const download = async (f: DataFile, version?: number) => {
    try {
      const res = await fetch(`/api/files/${f.id}/download${version ? `?version=${version}` : ''}`, { headers: { Authorization: `Bearer ${getToken()}` } })
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${f.name.replace(/\.[^.]+$/, '')}_v${version || f.version}.${f.kind}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e: any) { toast.error(e.message) }
  }
  const showVersions = async (f: DataFile) => { try { setVersions({ file: f, items: await api(`/files/${f.id}/versions`) }) } catch (e: any) { toast.error(e.message) } }
  const replace = async (file: File) => {
    if (!replacing) return
    setUploading(true)
    try {
      const form = new FormData(); form.append('file', file)
      const r = await api<DataFile & { triggered: { agent_name: string }[] }>(`/files/${replacing.id}/replace`, { form })
      toast.success(`${r.name} is now version ${r.version}` + (r.triggered.length ? ` — started ${r.triggered.map(t => t.agent_name).join(', ')}` : ''))
      list.reload()
    } catch (e: any) { toast.error(e.message) } finally { setUploading(false); setReplacing(null) }
  }

  const upload = async (f: File) => {
    setUploading(true)
    try {
      const form = new FormData(); form.append('file', f)
      const r = await api<DataFile>('/files', { form })
      toast.success(`${r.name}: ${r.row_count} rows, ${r.columns.length} columns`)
      list.reload()
    } catch (e: any) { toast.error(e.message) } finally { setUploading(false) }
  }
  const open = async (f: DataFile) => { try { setPreview(await api<DataFile>(`/files/${f.id}`)) } catch (e: any) { toast.error(e.message) } }
  const remove = async (f: DataFile) => {
    try { await api(`/files/${f.id}`, { method: 'DELETE' }); toast(`Deleted ${f.name}`); list.reload() } catch (e: any) { toast.error(e.message) }
  }

  return (
    <div>
      <PageHeader title="Data files" subtitle="Spreadsheets your agents read. Jerry recognises columns like email, name, status, amount and due date automatically."
        actions={<><input ref={ref} type="file" accept=".csv,.xlsx" className="hidden" onChange={e => { e.target.files?.[0] && upload(e.target.files[0]); e.target.value = '' }} />
          <button className="btn-primary" onClick={() => ref.current?.click()} disabled={uploading}>{uploading ? <Spinner /> : <Upload className="h-4 w-4" />}Upload spreadsheet</button></>} />
      <div onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; f && upload(f) }}
        className={`mb-5 rounded-xl border-2 border-dashed px-5 py-4 text-[13px] text-center transition-colors ${drag ? 'border-focus bg-brand-soft/50 text-ink' : 'border-line-strong text-ink-3'}`}>
        Drop a .csv or .xlsx file here — the first row should be column names.
      </div>
      {list.error && <ErrorNote message={list.error} onRetry={list.reload} />}
      {!list.data && !list.error && <Skeleton className="h-64" />}
      {list.data && !list.data.length && <div className="card"><EmptyState icon={<Database className="h-5 w-5" />} title="No spreadsheets yet" body="Upload a spreadsheet of leads, invoices or candidates to get started." /></div>}
      <div className="grid gap-3 md:grid-cols-2">
        {list.data?.map(f => (
          <div key={f.id} className="card p-4 flex gap-3">
            <span className="h-10 w-10 rounded-xl grid place-items-center bg-f-databg text-f-data shrink-0"><FileSpreadsheet className="h-5 w-5" /></span>
            <div className="min-w-0 flex-1">
              <button className="text-[14.5px] font-semibold hover:underline text-left truncate max-w-full" onClick={() => open(f)}>{f.name}</button>
              <div className="text-xs text-ink-3">{f.row_count} rows · {f.columns.length} columns · {(f as any).version > 1 ? <>version {(f as any).version}, updated {timeAgo((f as any).updated_at)}</> : <>added {timeAgo(f.created_at)}</>}</div>
              <div className="mt-2 flex flex-wrap gap-1">{f.columns.slice(0, 7).map(c => <span key={c} className="h-5 px-1.5 rounded bg-paper border border-line text-2xs font-medium inline-flex items-center">{c}</span>)}{f.columns.length > 7 && <span className="text-2xs text-ink-3">+{f.columns.length - 7}</span>}</div>
              {!!f.used_by?.length && <div className="mt-2 text-xs text-ink-2">Read by {f.used_by.join(', ')}</div>}
            </div>
            <div className="flex flex-col gap-1 items-end">
              <button className="btn-ghost btn-sm" onClick={() => open(f)}>Preview</button>
              <button className="btn-ghost btn-sm" onClick={() => showVersions(f)}><History className="h-3.5 w-3.5" />v{(f as any).version || 1}</button>
              <button className="btn-ghost btn-sm" onClick={() => { setReplacing(f); replaceRef.current?.click() }} title="Upload a new version of this file"><RefreshCw className="h-3.5 w-3.5" />New version</button>
              <button className="btn-ghost btn-sm !px-2" onClick={() => remove(f)} aria-label={`Delete ${f.name}`} disabled={!!f.used_by?.length} title={f.used_by?.length ? 'In use by an agent' : 'Delete'}><Trash2 className="h-4 w-4" /></button>
            </div>
          </div>
        ))}
      </div>
      <input ref={replaceRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={e => { e.target.files?.[0] && replace(e.target.files[0]); e.target.value = '' }} />
      <Modal open={!!versions} onClose={() => setVersions(null)} title={`Versions of ${versions?.file.name || ''}`}>
        <p className="text-[13px] text-ink-2 mb-3">Nothing is ever overwritten. Agents that update the sheet create a new version, and so does uploading a new file.</p>
        <ul className="divide-y divide-line rounded-lg border border-line">
          {versions?.items.map(v => (
            <li key={v.version} className="flex items-center gap-3 px-3 py-2.5">
              <span className="font-display font-semibold w-8">v{v.version}</span>
              <span className="min-w-0 flex-1"><span className="block text-[13px]">{v.note}</span><span className="block text-xs text-ink-3">{v.source === 'agent' ? 'By agent' : 'Upload'} · {v.created_by} · {timeAgo(v.created_at)} · {v.row_count} rows{v.current ? ' · current' : ''}</span></span>
              <button className="btn-ghost btn-sm" onClick={() => versions && download(versions.file, v.version)}><Download className="h-3.5 w-3.5" />Download</button>
            </li>
          ))}
        </ul>
      </Modal>
      <Modal open={!!preview} onClose={() => setPreview(null)} title={preview?.name || ''} wide>
        {preview?.rows && (
          <div className="overflow-auto thin-scroll max-h-[60vh] rounded-lg border border-line">
            <table className="text-xs w-full">
              <thead className="bg-paper sticky top-0"><tr>{preview.columns.map(c => <th key={c} className="text-left font-semibold px-2.5 py-2 whitespace-nowrap">{c}</th>)}</tr></thead>
              <tbody>{preview.rows.map((r, i) => <tr key={i} className="border-t border-line">{preview.columns.map(c => <td key={c} className="px-2.5 py-1.5 whitespace-nowrap">{r[c]}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  )
}
