import { useEffect, useRef, useState } from 'react'
import { CheckIcon, CopyIcon, XIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'

type Phase = 'idle' | 'copied' | 'failed'

interface CopyButtonProps {
  text: string
  describedBy?: string
  className?: string
}

export function CopyButton({ text, describedBy, className }: CopyButtonProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  async function handleCopy() {
    window.clearTimeout(timer.current)
    try {
      if (!navigator.clipboard) throw new Error('Clipboard API unavailable')
      await navigator.clipboard.writeText(text)
      setPhase('copied')
    } catch {
      setPhase('failed')
    }
    timer.current = window.setTimeout(() => setPhase('idle'), 2500)
  }

  const label = phase === 'copied' ? copy.actions.copied : phase === 'failed' ? copy.actions.copyFailed : copy.actions.copy
  const Icon = phase === 'copied' ? CheckIcon : phase === 'failed' ? XIcon : CopyIcon

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={handleCopy}
        aria-describedby={describedBy}
        data-phase={phase}
        className={className}
      >
        <Icon data-icon="inline-start" aria-hidden="true" />
        {label}
      </Button>
      <span role="status" className="sr-only">
        {phase === 'idle' ? '' : label}
      </span>
    </>
  )
}
