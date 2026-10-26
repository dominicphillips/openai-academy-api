import { useSyncExternalStore } from 'react'

// Browser theme preference: light on a first visit or without a valid saved choice, persisted locally once the visitor chooses.
// public/theme-init.js applies the same storage key and root attributes before the first paint.

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'academy-theme'

const listeners = new Set<() => void>()

function readStored(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : null
  } catch {
    return null
  }
}

function apply(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  root.dataset.theme = theme
}

let current: Theme = readStored() ?? 'light'
apply(current)

function notify() {
  for (const listener of listeners) listener()
}

// Another tab changed the preference: follow it so the choice stays consistent per browser.
window.addEventListener('storage', (event) => {
  if (event.key !== THEME_STORAGE_KEY && event.key !== null) return
  const stored = readStored() ?? 'light'
  if (stored === current) return
  current = stored
  apply(current)
  notify()
})

export function setTheme(theme: Theme) {
  if (theme === current) return
  current = theme
  apply(theme)
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Storage unavailable: the choice still applies for this page session.
  }
  notify()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function snapshot(): Theme {
  return current
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, snapshot)
}
