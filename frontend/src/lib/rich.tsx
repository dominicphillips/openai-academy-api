import { Fragment, type ReactNode } from 'react'

/**
 * Like fmt, but returns nodes, and a span written between double asterisks renders in bold:
 * `Share changes were **{shares} at {name}** after its call.` Placeholders substitute inside and
 * outside the span. Emphasis is the exception: copy marks one or two phrases per card, each a fact
 * with its subject, never a lone number or word.
 */
export function fmtRich(template: string, values: Record<string, string | number>, strongClass = 'font-semibold'): ReactNode {
  const sub = (text: string) => text.replace(/\{(\w+)\}/g, (m, k: string) => (k in values ? String(values[k]) : m))
  const parts = template.split(/\*\*(.+?)\*\*/g)
  return parts.map((part, i) =>
    i % 2 ? (
      <strong key={i} className={strongClass}>
        {sub(part)}
      </strong>
    ) : (
      <Fragment key={i}>{sub(part)}</Fragment>
    ),
  )
}
