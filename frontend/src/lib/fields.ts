import type { FieldKey } from './types'

/** One colour language across the product: the colour a phrase gets in the
 * annotated sentence is the colour of the field it became and of the workflow
 * steps that use it. */
export const FIELD: Record<FieldKey, { fg: string; bg: string; ring: string; name: string }> = {
  trigger:   { fg: 'text-f-trigger',   bg: 'bg-f-triggerbg',   ring: 'decoration-f-trigger',   name: 'When' },
  data:      { fg: 'text-f-data',      bg: 'bg-f-databg',      ring: 'decoration-f-data',      name: 'Data' },
  audience:  { fg: 'text-f-audience',  bg: 'bg-f-audiencebg',  ring: 'decoration-f-audience',  name: 'Who' },
  action:    { fg: 'text-f-action',    bg: 'bg-f-actionbg',    ring: 'decoration-f-action',    name: 'Does' },
  approval:  { fg: 'text-f-approval',  bg: 'bg-f-approvalbg',  ring: 'decoration-f-approval',  name: 'Safety' },
  knowledge: { fg: 'text-f-knowledge', bg: 'bg-f-knowledgebg', ring: 'decoration-f-knowledge', name: 'Knows' },
  memory:    { fg: 'text-f-memory',    bg: 'bg-f-memorybg',    ring: 'decoration-f-memory',    name: 'Remembers' },
  output:    { fg: 'text-f-output',    bg: 'bg-f-outputbg',    ring: 'decoration-f-output',    name: 'Output' },
}

/** Workflow tool category -> field colour */
export const CATEGORY_FIELD: Record<string, FieldKey> = {
  data: 'data', audience: 'audience', memory: 'memory', knowledge: 'knowledge', ai: 'action',
  safety: 'approval', approval: 'approval', action: 'output', output: 'output',
}

export const HEX: Record<FieldKey, string> = {
  trigger: '#C98A0B', data: '#2C7BD6', audience: '#7656E3', action: '#178A63',
  approval: '#D2405A', knowledge: '#13899A', memory: '#A0458B', output: '#C4612A',
}

export const BG: Record<FieldKey, string> = {
  trigger: '#FFF2D6', data: '#E2EEFD', audience: '#EEE9FF', action: '#DDF4EA',
  approval: '#FFE6EA', knowledge: '#DBF3F5', memory: '#F9E4F3', output: '#FCE9DC',
}
