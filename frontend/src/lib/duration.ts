import { copy, fmt } from '@/copy'
import type { ResourceDuration } from '@/lib/api'

export interface DurationEntry {
  key: keyof ResourceDuration
  label: string
  value: string
}

export function formatMinutes(minutes: number): string {
  return fmt(copy.units.minutes, { minutes })
}

export function formatSeconds(seconds: number): string {
  if (seconds < 60) return fmt(copy.units.seconds, { seconds })
  return fmt(copy.units.minutesSeconds, { minutes: Math.floor(seconds / 60), seconds: seconds % 60 })
}

// The duration field that measures a resource of this kind as a whole.
const KIND_DURATION: Partial<Record<string, keyof ResourceDuration>> = {
  course: 'courseMinutes',
  'learning-path': 'pathMinutes',
  video: 'videoSeconds',
}

/**
 * One duration for compact views such as course cards, preferring the field that matches the kind.
 * `matchesKind` is false when the value measures another scope (for example only a course duration
 * on a learning path), so the view must show its label. Detail and reference views list every field.
 */
export function primaryDuration(kind: string, duration: ResourceDuration): { entry: DurationEntry; matchesKind: boolean } | null {
  const entries = durationEntries(duration)
  const match = entries.find((entry) => entry.key === KIND_DURATION[kind])
  if (match) return { entry: match, matchesKind: true }
  return entries.length ? { entry: entries[0], matchesKind: false } : null
}

// A learning path and its course keep distinct durations, so each known value is listed separately.
export function durationEntries(duration: ResourceDuration): DurationEntry[] {
  const entries: DurationEntry[] = []
  if (duration.courseMinutes !== null) {
    entries.push({ key: 'courseMinutes', label: copy.resource.view.courseMinutes, value: formatMinutes(duration.courseMinutes) })
  }
  if (duration.pathMinutes !== null) {
    entries.push({ key: 'pathMinutes', label: copy.resource.view.pathMinutes, value: formatMinutes(duration.pathMinutes) })
  }
  if (duration.videoSeconds !== null) {
    entries.push({ key: 'videoSeconds', label: copy.resource.view.videoSeconds, value: formatSeconds(duration.videoSeconds) })
  }
  return entries
}
