import { useId, useMemo, useState, type CSSProperties } from 'react'
import { WrapTextIcon } from 'lucide-react'
import { CopyButton } from '@/components/copy-button'
import { Button } from '@/components/ui/button'
import { copy, fmt } from '@/copy'
import { tokenizeLines, type Language, type Token } from '@/lib/highlight'
import { cn } from '@/lib/utils'

// Presentation limits: beyond these the viewer shows a prefix and says so; Copy still returns everything.
const MAX_LINES = 400
const MAX_CHARS = 64 * 1024

interface CodeBlockProps {
  code: string
  label: string
  language?: Language
  copyText?: string
  tall?: boolean
  wrapToggle?: boolean
  className?: string
}

interface Preview {
  lines: Token[][]
  shownLines: number
  totalLines: number
  truncated: boolean
}

function countLines(text: string): number {
  let count = 1
  for (let i = 0; i < text.length; i += 1) if (text.charCodeAt(i) === 10) count += 1
  return count
}

function buildPreview(code: string, language: Language): Preview {
  const totalLines = countLines(code)
  let end = code.length
  if (totalLines > MAX_LINES) {
    let index = -1
    for (let line = 0; line < MAX_LINES; line += 1) {
      index = code.indexOf('\n', index + 1)
      if (index === -1) break
    }
    if (index !== -1) end = index
  }
  if (end > MAX_CHARS) {
    const lastBreak = code.lastIndexOf('\n', MAX_CHARS)
    end = lastBreak > 0 ? lastBreak : MAX_CHARS
  }
  const shown = code.slice(0, end)
  return {
    lines: tokenizeLines(shown, language),
    shownLines: countLines(shown),
    totalLines,
    truncated: end < code.length,
  }
}

function LineTokens({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((token, index) =>
        token.kind === 'plain' ? (
          token.text
        ) : (
          <span key={index} className={`tok-${token.kind}`}>
            {token.text}
          </span>
        ),
      )}
    </>
  )
}

// Syntax-coloured, numbered code that scrolls inside its panel; copying returns the exact source text.
export function CodeBlock({ code, label, language = 'text', copyText, tall = false, wrapToggle = true, className }: CodeBlockProps) {
  const captionId = useId()
  const [wrap, setWrap] = useState(false)
  const preview = useMemo(() => buildPreview(code, language), [code, language])
  const numbered = preview.totalLines > 1
  const gutter = numbered ? `${String(preview.shownLines).length + 1}ch` : '0.25rem'

  return (
    <figure className={cn('min-w-0 overflow-hidden rounded-lg border bg-panel', className)}>
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <figcaption id={captionId} className="truncate text-xs font-medium text-muted-foreground">
          {label}
        </figcaption>
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground/80">{language}</span>
        <div className="ml-auto flex shrink-0 items-center gap-1">
          {wrapToggle ? (
            // Like the theme toggle, the label names the action; the tint only mirrors the current mode.
            <Button
              type="button"
              variant="ghost"
              size="sm"
              data-active={wrap}
              onClick={() => setWrap((value) => !value)}
              className="data-[active=true]:bg-muted data-[active=true]:text-foreground"
            >
              <WrapTextIcon data-icon="inline-start" aria-hidden="true" />
              <span className="max-sm:sr-only">{wrap ? copy.code.disableWrap : copy.code.enableWrap}</span>
            </Button>
          ) : null}
          <CopyButton text={copyText ?? code} describedBy={captionId} />
        </div>
      </div>
      <div
        tabIndex={0}
        role="region"
        aria-labelledby={captionId}
        data-wrap={wrap}
        style={{ '--gutter': gutter } as CSSProperties}
        className={cn(
          'code-view overflow-x-auto outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset',
          tall && 'max-h-[40dvh] overflow-y-auto md:max-h-[28rem]',
        )}
      >
        <div className="code-lines">
          {preview.lines.map((tokens, index) => (
            <div key={index} className="code-line">
              <span className="code-ln" aria-hidden="true">
                {numbered ? index + 1 : ''}
              </span>
              <code className="code-text">
                <LineTokens tokens={tokens} />
              </code>
            </div>
          ))}
        </div>
      </div>
      {preview.truncated ? (
        <p className="border-t px-3 py-1.5 text-xs text-muted-foreground">
          {fmt(copy.code.previewTruncated, { shown: preview.shownLines, total: preview.totalLines })}
        </p>
      ) : null}
    </figure>
  )
}
