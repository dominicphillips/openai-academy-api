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

export function unique(values: readonly string[] | undefined): string[] {
  return values ? Array.from(new Set(values.filter((value) => value !== ''))).sort() : []
}
