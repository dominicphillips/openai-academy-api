import type { ReactNode } from 'react'

export function PageHeader({ title, lede }: { title: string; lede: string }) {
  return (
    <header className="space-y-2">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      <p className="max-w-prose text-muted-foreground">{lede}</p>
    </header>
  )
}

interface SectionProps {
  id?: string
  title: string
  lede?: string
  children: ReactNode
}

export function Section({ id, title, lede, children }: SectionProps) {
  return (
    <section id={id} className="scroll-mt-20 space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {lede ? <p className="max-w-prose text-sm text-muted-foreground">{lede}</p> : null}
      </div>
      {children}
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
    <dl className="divide-y rounded-lg border">
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
