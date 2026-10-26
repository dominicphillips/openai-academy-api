import { copy } from '@/copy'

const STATUS_NOTES: Record<number, () => string> = {
  400: () => copy.errors.badRequest,
  404: () => copy.errors.notFound,
  409: () => copy.errors.obsoleteSnapshot,
  503: () => copy.errors.noSnapshot,
}

// Existing explanation for a documented HTTP error status; null for success statuses.
export function statusNote(status: number): string | null {
  const known = STATUS_NOTES[status]
  if (known) return known()
  return status >= 400 ? copy.errors.unexpected : null
}
