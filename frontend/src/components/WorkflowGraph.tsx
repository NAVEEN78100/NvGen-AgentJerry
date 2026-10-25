import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import clsx from 'clsx'
import {
  BarChart3, Bell, BookOpen, Bookmark, Check, FileCheck2, FileSpreadsheet, FileText, Filter, History, Hourglass, Lock, UserX,
  PenLine, Send, ShieldCheck, UserCheck, X,
} from 'lucide-react'
import { memo, useMemo } from 'react'
import { BG, CATEGORY_FIELD, HEX } from '../lib/fields'
import type { Step } from '../lib/types'
import { Spinner } from './ui'

export const TOOL_ICON: Record<string, typeof Send> = {
  'spreadsheet.read': FileSpreadsheet, 'data.filter': Filter, 'memory.exclude': History,
  'knowledge.retrieve': BookOpen, 'ai.draft': PenLine, 'data.summarize': BarChart3, 'ai.draft_report': FileText,
  'safety.check': ShieldCheck, 'approval.request': UserCheck, 'email.send': Send, 'memory.record': Bookmark,
  'notify.summary': Bell, 'compliance.suppress': UserX, 'spreadsheet.update': FileCheck2,
}

type NodeData = { step: Step; index: number; status?: string; selected?: boolean; message?: string }

const StepNode = memo(({ data }: NodeProps) => {
  const { step, index, status, selected, message } = data as unknown as NodeData
  const field = CATEGORY_FIELD[step.category] || 'action'
  const Icon = TOOL_ICON[step.tool] || PenLine
  const done = status === 'passed'
  const failed = status === 'failed'
  const running = status === 'running'
  const waiting = status === 'waiting'
  const skipped = status === 'skipped'
  return (
    <div className={clsx('w-[340px] rounded-xl bg-surface border transition-all duration-300 cursor-pointer',
      selected ? 'border-ink shadow-pop' : 'border-line shadow-card hover:border-line-strong',
      running && 'ring-4 ring-brand/15 border-brand', waiting && 'ring-4 ring-f-approval/15 border-f-approval',
      failed && 'border-f-approval', skipped && 'opacity-45')}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-start gap-3 p-3">
        <div className="relative h-9 w-9 rounded-lg grid place-items-center shrink-0" style={{ background: BG[field], color: HEX[field] }}>
          <Icon className="h-[18px] w-[18px]" strokeWidth={2} />
          {status && status !== 'pending' && (
            <span className={clsx('absolute -right-1.5 -bottom-1.5 h-[18px] w-[18px] rounded-full grid place-items-center border-2 border-surface text-white',
              done && 'bg-f-action', failed && 'bg-f-approval', running && 'bg-brand', waiting && 'bg-f-approval', skipped && 'bg-ink-3')}>
              {done && <Check className="h-2.5 w-2.5" strokeWidth={3.5} />}
              {failed && <X className="h-2.5 w-2.5" strokeWidth={3.5} />}
              {running && <Spinner className="h-2.5 w-2.5" />}
              {waiting && <Hourglass className="h-2.5 w-2.5" strokeWidth={3} />}
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-2xs font-semibold text-ink-3 tabular">{index + 1}</span>
            <span className="text-[13.5px] font-semibold text-ink truncate">{step.label}</span>
            {step.sensitive && <Lock className="h-3 w-3 text-f-approval shrink-0" aria-label="Sensitive action" />}
          </div>
          <p className="mt-0.5 text-xs text-ink-2 leading-snug line-clamp-2">{message || step.description}</p>
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
})

const nodeTypes = { step: StepNode }

export function WorkflowGraph({ steps, statuses, messages, selected, onSelect, height = 620 }: {
  steps: Step[]; statuses?: Record<string, string>; messages?: Record<string, string>
  selected?: string | null; onSelect?: (id: string) => void; height?: number
}) {
  const GAP = 104
  const nodes: Node[] = useMemo(() => steps.map((s, i) => ({
    id: s.id, type: 'step', position: { x: 0, y: i * GAP }, draggable: false,
    data: { step: s, index: i, status: statuses?.[s.id], selected: selected === s.id, message: messages?.[s.id] },
  })), [steps, statuses, messages, selected])
  const edges: Edge[] = useMemo(() => steps.flatMap(s => s.depends_on.map(d => ({
    id: `${d}-${s.id}`, source: d, target: s.id, type: 'smoothstep',
    animated: statuses?.[s.id] === 'running' || statuses?.[d] === 'running',
  }))), [steps, statuses])

  return (
    <div style={{ height }} className="w-full">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.03, maxZoom: 1 }}
        minZoom={0.4} maxZoom={1.4} nodesConnectable={false} elementsSelectable={false}
        panOnScroll={false} zoomOnScroll={false} zoomOnPinch={false} panOnDrag={false} preventScrolling={false} zoomOnDoubleClick={false}
        onNodeClick={(_, n) => onSelect?.(n.id)} proOptions={{ hideAttribution: true }}>
        <Background gap={20} size={1} color="#DADDE5" />
      </ReactFlow>
    </div>
  )
}

/** Compact list version for narrow spaces / mobile */
export function WorkflowList({ steps, statuses }: { steps: Step[]; statuses?: Record<string, string> }) {
  return (
    <ol className="space-y-1.5">
      {steps.map((s, i) => {
        const field = CATEGORY_FIELD[s.category] || 'action'
        const Icon = TOOL_ICON[s.tool] || PenLine
        return (
          <li key={s.id} className="flex items-center gap-2.5 text-[13px]">
            <span className="h-6 w-6 rounded-md grid place-items-center shrink-0" style={{ background: BG[field], color: HEX[field] }}><Icon className="h-3.5 w-3.5" /></span>
            <span className="tabular text-ink-3 w-4">{i + 1}</span>
            <span className="truncate">{s.label}</span>
            {s.sensitive && <Lock className="h-3 w-3 text-f-approval" />}
            {statuses?.[s.id] === 'passed' && <Check className="h-3.5 w-3.5 text-f-action ml-auto" />}
          </li>
        )
      })}
    </ol>
  )
}
