export function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? ''
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

export function shortHash(hash: string, length = 16): string {
  return hash.length > length ? `${hash.slice(0, length)}…` : hash
}

// Display form of an API enum value on browsing surfaces ("learning-path" -> "Learning path"); the
// reference views keep the raw value.
export function enumLabel(value: string): string {
  const spaced = value.replace(/-/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

// Only absolute http(s) URLs from API data become link targets.
export function safeHttpUrl(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

export function unique(values: readonly string[] | undefined): string[] {
  return values ? Array.from(new Set(values.filter((value) => value !== ''))).sort() : []
}
