import { motion } from 'framer-motion'
import { BG, HEX } from '../lib/fields'
import type { FieldKey, Span } from '../lib/types'

/** The signature element: the user's own sentence, with each phrase marked in
 * the colour of the field it became. Highlights sweep in left to right. */
export function AnnotatedText({ text, spans, animate = true, size = 'lg', active, onHover }: {
  text: string; spans: Span[]; animate?: boolean; size?: 'lg' | 'md'
  active?: FieldKey | null; onHover?: (f: FieldKey | null) => void
}) {
  const parts: { text: string; span?: Span; i: number }[] = []
  let cursor = 0
  const sorted = [...(spans || [])].sort((a, b) => a.start - b.start)
  let n = 0
  for (const s of sorted) {
    if (s.start < cursor) continue
    if (s.start > cursor) parts.push({ text: text.slice(cursor, s.start), i: -1 })
    parts.push({ text: text.slice(s.start, s.end), span: s, i: n++ })
    cursor = s.end
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), i: -1 })

  return (
    <p className={size === 'lg' ? 'text-[19px] leading-[1.95] text-ink' : 'text-[14.5px] leading-[1.9] text-ink'}>
      {parts.map((p, k) => {
        if (!p.span) return <span key={k}>{p.text}</span>
        const f = p.span.field
        const dim = active && active !== f
        return (
          <motion.mark key={k} title={p.span.label}
            onMouseEnter={() => onHover?.(f)} onMouseLeave={() => onHover?.(null)}
            initial={animate ? { backgroundSize: '0% 100%', opacity: 0.4 } : false}
            animate={{ backgroundSize: '100% 100%', opacity: dim ? 0.45 : 1 }}
            transition={{ delay: animate ? 0.1 + p.i * 0.085 : 0, duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
            className="rounded-[4px] px-[3px] -mx-[1px] text-ink bg-no-repeat cursor-default"
            style={{
              backgroundImage: `linear-gradient(${BG[f]}, ${BG[f]})`,
              boxShadow: `inset 0 -2px 0 0 ${HEX[f]}`,
              outline: active === f ? `2px solid ${HEX[f]}` : undefined,
              outlineOffset: 1,
            }}>
            {p.text}
          </motion.mark>
        )
      })}
    </p>
  )
}

export function FieldSwatch({ field, size = 8 }: { field: FieldKey; size?: number }) {
  return <span aria-hidden className="inline-block rounded-full shrink-0"
    style={{ width: size, height: size, background: BG[field], boxShadow: `inset 0 0 0 2px ${HEX[field]}` }} />
}
