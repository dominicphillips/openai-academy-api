import { LoaderCircleIcon, PlayIcon, RotateCcwIcon } from 'lucide-react'
import { CodeBlock } from '@/components/code-block'
import { CopyButton } from '@/components/copy-button'
import { Button } from '@/components/ui/button'
import { copy, fmt } from '@/copy'
import type { RequestState } from '@/hooks/use-request'
import { API_BASE } from '@/lib/api'
import { prettyJson } from '@/lib/format'

interface RequestPanelProps {
  path: string
  state: RequestState
  onRun?: () => void
  showRun?: boolean
}

const STATUS_NOTES: Record<number, () => string> = {
  400: () => copy.errors.badRequest,
  404: () => copy.errors.notFound,
  409: () => copy.errors.obsoleteSnapshot,
  503: () => copy.errors.noSnapshot,
}

function statusNote(status: number): string | null {
  const known = STATUS_NOTES[status]
  if (known) return known()
  return status >= 400 ? copy.errors.unexpected : null
}

export function RequestPanel({ path, state, onRun, showRun = true }: RequestPanelProps) {
  const url = `${API_BASE}${path}`
  const loading = state.phase === 'loading'
  const buttonLabel =
    state.phase === 'loading'
      ? copy.actions.running
      : state.phase === 'failed'
        ? copy.actions.retry
        : state.phase === 'done'
          ? copy.actions.runAgain
          : copy.actions.run
  const ButtonIcon = state.phase === 'loading' ? LoaderCircleIcon : state.phase === 'idle' ? PlayIcon : RotateCcwIcon

  return (
    <div className="min-w-0 space-y-3">
      <div className="min-w-0 rounded-lg border">
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">{copy.labels.requestUrl}</span>
          <div className="ml-auto flex items-center gap-2">
            <CopyButton text={url} />
            {showRun ? (
              <Button type="button" size="sm" onClick={onRun} aria-disabled={loading}>
                <ButtonIcon data-icon="inline-start" aria-hidden="true" className={loading ? 'animate-spin' : undefined} />
                {buttonLabel}
              </Button>
            ) : null}
          </div>
        </div>
        <p className="px-3 py-2 font-mono text-[13px] break-all">
          <span className="text-muted-foreground">GET </span>
          {url}
        </p>
        <div className="border-t px-3 py-2 text-sm" role="status" aria-live="polite">
          {state.phase === 'idle' ? <p className="text-muted-foreground">{copy.request.idle}</p> : null}
          {state.phase === 'loading' ? <p className="text-muted-foreground">{copy.request.loading}</p> : null}
          {state.phase === 'failed' ? (
            <div className="space-y-1">
              <p className="text-destructive">{copy.request.failed}</p>
              <pre className="overflow-x-auto font-mono text-xs text-muted-foreground">{state.message}</pre>
            </div>
          ) : null}
          {state.phase === 'done' ? (
            <div className="space-y-1">
              <p>
                {fmt(copy.request.statusLine, {
                  status: state.result.statusText ? `${state.result.status} ${state.result.statusText}` : state.result.status,
                  ms: state.result.ms,
                })}
              </p>
              {statusNote(state.result.status) ? (
                <p className="text-muted-foreground">{statusNote(state.result.status)}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      {state.phase === 'done' ? (
        <CodeBlock
          label={copy.labels.response}
          code={state.result.isJson ? prettyJson(state.result.json) : state.result.text || copy.request.emptyBody}
          tall
        />
      ) : null}
    </div>
  )
}
