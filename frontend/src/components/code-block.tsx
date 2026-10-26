import { useId } from 'react'
import { CopyButton } from '@/components/copy-button'
import { cn } from '@/lib/utils'

interface CodeBlockProps {
  code: string
  label: string
  copyText?: string
  tall?: boolean
  className?: string
}

// Code scrolls inside the block so long lines never widen the page.
export function CodeBlock({ code, label, copyText, tall = false, className }: CodeBlockProps) {
  const captionId = useId()
  return (
    <figure className={cn('min-w-0 overflow-hidden rounded-lg border bg-muted/40', className)}>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1.5">
        <figcaption id={captionId} className="truncate text-xs font-medium text-muted-foreground">
          {label}
        </figcaption>
        <CopyButton text={copyText ?? code} describedBy={captionId} />
      </div>
      <pre
        tabIndex={0}
        role="region"
        aria-labelledby={captionId}
        className={cn(
          'overflow-x-auto p-3 font-mono text-[13px] leading-relaxed outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
          tall && 'max-h-[28rem] overflow-y-auto',
        )}
      >
        <code>{code}</code>
      </pre>
    </figure>
  )
}
