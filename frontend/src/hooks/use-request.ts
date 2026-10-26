import { useCallback, useRef, useState } from 'react'
import { apiRequest, type RequestResult } from '@/lib/api'

export type RequestState =
  | { phase: 'idle' }
  | { phase: 'loading'; path: string }
  | { phase: 'done'; path: string; result: RequestResult }
  | { phase: 'failed'; path: string; message: string }

// One in-flight request at a time; a new run aborts the previous one.
export function useRequest() {
  const [state, setState] = useState<RequestState>({ phase: 'idle' })
  const controller = useRef<AbortController | null>(null)

  const run = useCallback(async (path: string) => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    setState({ phase: 'loading', path })
    try {
      const result = await apiRequest(path, current.signal)
      if (current.signal.aborted) return
      setState({ phase: 'done', path, result })
    } catch (error) {
      if (current.signal.aborted) return
      setState({ phase: 'failed', path, message: error instanceof Error ? error.message : String(error) })
    }
  }, [])

  return { state, run }
}
