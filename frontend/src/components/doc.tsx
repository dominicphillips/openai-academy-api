import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function PageHeader({ title, lede }: { title: string; lede: string }) {
  return (
    <header className="space-y-3">
      <h1 className="max-w-[28ch] text-[1.75rem] leading-[1.15] font-semibold tracking-[-0.02em] sm:text-[2.125rem]">{title}</h1>
      <p className="max-w-[64ch] text-[15px] leading-6 text-muted-foreground">{lede}</p>
    </header>
  )
}

interface SectionProps {
  id?: string
  title: string
  lede?: string
  /** Full-width content with the heading above it (the live request bench). */
  wide?: boolean
  children: ReactNode
}

// Reference sections read as a ledger on wide screens: heading column left, content right.
export function Section({ id, title, lede, wide = false, children }: SectionProps) {
  return (
    <section
      id={id}
      className={cn('grid scroll-mt-20 gap-4 border-t pt-6', !wide && 'xl:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] xl:gap-x-10')}
    >
      <div className="space-y-1">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {lede ? <p className="max-w-[60ch] text-sm leading-6 text-muted-foreground">{lede}</p> : null}
      </div>
      <div className="min-w-0 space-y-4">{children}</div>
    </section>
  )
}

export interface DefinitionRow {
  name: string
  type?: string
  note: string
}

export function Definitions({ rows }: { rows: DefinitionRow[] }) {
  return (
    <dl className="divide-y rounded-lg border bg-card">
      {rows.map((row) => (
        <div key={row.name} className="grid gap-1 px-4 py-3 sm:grid-cols-[minmax(0,12rem)_1fr] sm:gap-4">
          <dt className="min-w-0 break-words">
            <code className="font-mono text-[13px] font-medium">{row.name}</code>
            {row.type ? <span className="ml-2 font-mono text-xs text-muted-foreground">{row.type}</span> : null}
          </dt>
          <dd className="text-sm leading-6 text-muted-foreground">{row.note}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm break-words">{children}</dd>
    </div>
  )
}

export function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm leading-6">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}
