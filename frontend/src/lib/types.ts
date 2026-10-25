export type FieldKey = 'trigger' | 'data' | 'audience' | 'action' | 'approval' | 'knowledge' | 'memory' | 'output'

export interface Span { start: number; end: number; text: string; field: FieldKey; label: string }

export interface QuestionOption { value: string; label: string; hint?: string }
export interface Question {
  id: string; field: string; kind: 'choice' | 'file' | 'email' | 'text'; prompt: string; why: string
  options: QuestionOption[]; default?: string | null; blocking: boolean; placeholder?: string
}

export interface Check { id: string; label: string; status: 'pass' | 'warn' | 'fail'; detail: string }
export interface Validation { valid: boolean; status: 'pass' | 'warn' | 'fail'; checks: Check[] }

export interface Step {
  id: string; tool: string; label: string; description: string; why: string; params: Record<string, any>
  depends_on: string[]; category: string; sensitive: boolean; side_effect: boolean
}
export interface Workflow { id: string; version: number; steps: Step[]; validation: Validation; created_at: string }

export interface ConvMessage {
  role: 'user' | 'jerry'; kind: 'prompt' | 'answer' | 'refine' | 'understanding' | 'questions' | 'blueprint'
  text: string; spans?: Span[]; fields?: { field: FieldKey; label: string; value: string | null }[]
  assumptions?: string[]; questions?: Question[]; version?: number; validation?: Validation; was_live?: boolean; at: string
}

export type AgentStatus = 'draft' | 'ready' | 'tested' | 'deployed' | 'paused'

export interface RunBrief {
  id: string; agent_id: string; agent_name?: string; mode: 'test' | 'live'; status: string; triggered_by: string
  workflow_version: number; current_step: string | null; summary: Record<string, any>; error: string | null
  started_at: string; finished_at: string | null; approval_id?: string | null
}
export interface RunLog {
  step_id: string; index: number; tool: string; label: string; status: string; message: string
  output: Record<string, any>; attempts: number; started_at: string | null; finished_at: string | null; duration_ms: number | null
}
export interface Run extends RunBrief { logs: RunLog[] }

export interface AgentBrief {
  id: string; name: string; goal: string; status: AgentStatus; department: string; trigger: Record<string, any>
  trigger_label: string; next_run: string | null; pattern: string | null; purpose: string | null
  source_file: string | null; approval_required: boolean | null; created_at: string; updated_at: string
  deployed_at: string | null; engine: string; approver_id?: string; owner_id?: string
  stats: { live_runs?: number; emails_sent?: number; memory?: number; pending_approvals?: number; last_run?: RunBrief | null }
}
export interface Agent extends AgentBrief {
  prompt: string; requirement: Record<string, any> | null; questions: Question[]
  fields: { field: FieldKey; label: string; value: string | null }[]
  conversation: ConvMessage[]; workflow: Workflow | null; tested_version: number | null
  can_deploy: boolean; can_run_live: boolean; knowledge_ids: string[]
}

export interface Draft {
  key: string; to: string; to_name: string; subject: string; body: string; row: Record<string, string>
  row_number?: number; citations: { source_title: string; section: string; text: string }[]; engine?: string
  flags?: { level: 'error' | 'warn'; text: string }[]
}
export interface ApprovalItem { id: number; idx: number; ref_key: string; payload: Draft; flags: { level: string; text: string }[]; status: 'pending' | 'approved' | 'rejected'; edited: boolean; note: string }
export interface Approval {
  id: string; execution_id: string; agent_id: string; agent_name: string | null; action: string; title: string
  reason: string; status: string; decided_by: string | null; decided_at: string | null; created_at: string
  counts: { total: number; approved: number; rejected: number; pending: number; flagged: number }
  assigned_to: { id: string; name: string } | null; can_decide: boolean; blocked_reason: string | null
  items?: ApprovalItem[]
}

export interface DataFile { id: string; name: string; kind: string; columns: string[]; row_count: number; created_at: string; version?: number; updated_at?: string | null; used_by?: string[]; rows?: Record<string, string>[] }
export interface KnowledgeDoc { id: string; title: string; file_name: string; source_type: string; chunk_count: number; char_count: number; status: string; created_at: string }
export interface Passage { chunk_id: number; source_id: string; source_title: string; section: string; text: string; score: number }
