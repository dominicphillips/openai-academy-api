import { useCallback, useEffect, useReducer, useRef } from 'react'
import { apiRequest, toResourceList, type Resource, type ResourceList } from '@/lib/api'

export type CatalogError =
  | { kind: 'network'; message: string }
  | { kind: 'http'; status: number; statusText: string; ms: number }
  | { kind: 'shape' }

export interface CatalogState {
  phase: 'idle' | 'loading' | 'done' | 'failed'
  /** Path of the latest request, in flight or completed. */
  path: string | null
  /** The latest request asked for a later page, so existing items stay on screen. */
  appending: boolean
  items: Resource[]
  total: number | null
  nextCursor: string | null
  snapshotId: string | null
  error: CatalogError | null
}

type Action =
  | { type: 'start'; path: string; appending: boolean }
  | { type: 'done'; path: string; appending: boolean; list: ResourceList }
  | { type: 'error'; path: string; appending: boolean; error: CatalogError }

const INITIAL: CatalogState = {
  phase: 'idle',
  path: null,
  appending: false,
  items: [],
  total: null,
  nextCursor: null,
  snapshotId: null,
  error: null,
}

function reducer(state: CatalogState, action: Action): CatalogState {
  switch (action.type) {
    case 'start':
      return action.appending
        ? { ...state, phase: 'loading', path: action.path, appending: true, error: null }
        : { ...INITIAL, phase: 'loading', path: action.path }
    case 'done': {
      // A later page never repeats a card already on screen, so list keys stay unique.
      const seen = new Set(action.appending ? state.items.map((item) => item.id) : [])
      const fresh = action.list.items.filter((item) => {
        if (seen.has(item.id)) return false
        seen.add(item.id)
        return true
      })
      return {
        phase: 'done',
        path: action.path,
        appending: action.appending,
        items: action.appending ? [...state.items, ...fresh] : fresh,
        total: action.list.total,
        nextCursor: action.list.nextCursor,
        snapshotId: action.list.snapshotId,
        error: null,
      }
    }
    case 'error':
      return { ...state, phase: 'failed', path: action.path, appending: action.appending, error: action.error }
  }
}

// Catalog pages from GET /v1/resources: a first page replaces the list, a cursor page extends it.
export function useCatalog() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => () => controller.current?.abort(), [])

  const load = useCallback(async (path: string, appending: boolean) => {
    controller.current?.abort()
    const current = new AbortController()
    controller.current = current
    dispatch({ type: 'start', path, appending })
    try {
      const result = await apiRequest(path, current.signal)
      if (current.signal.aborted) return
      if (!result.ok) {
        dispatch({
          type: 'error',
          path,
          appending,
          error: { kind: 'http', status: result.status, statusText: result.statusText, ms: result.ms },
        })
        return
      }
      const list = toResourceList(result.json)
      if (!list) {
        dispatch({ type: 'error', path, appending, error: { kind: 'shape' } })
        return
      }
      dispatch({ type: 'done', path, appending, list })
    } catch (error) {
      if (current.signal.aborted) return
      dispatch({
        type: 'error',
        path,
        appending,
        error: { kind: 'network', message: error instanceof Error ? error.message : String(error) },
      })
    }
  }, [])

  return { state, load }
}
