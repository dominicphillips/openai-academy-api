import { useMemo, useSyncExternalStore } from 'react'

// Minimal History API router: enough for a handful of documentation routes without a dependency.

const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
  }
}

function snapshot(): string {
  return `${window.location.pathname}${window.location.search}`
}

export function navigate(to: string, options: { replace?: boolean } = {}) {
  if (to === snapshot()) return
  window.history[options.replace ? 'replaceState' : 'pushState'](null, '', to)
  for (const listener of listeners) listener()
  if (!options.replace) {
    window.scrollTo(0, 0)
    requestAnimationFrame(() => document.getElementById('main')?.focus({ preventScroll: true }))
  }
}

export interface Location {
  pathname: string
  search: URLSearchParams
}

export function useLocation(): Location {
  const href = useSyncExternalStore(subscribe, snapshot)
  return useMemo(() => {
    const url = new URL(href, window.location.origin)
    const pathname = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, '') : url.pathname
    return { pathname, search: url.searchParams }
  }, [href])
}
