// App routes derived from API identifiers.

export function resourceRoute(id: string): string {
  return `/resources/${encodeURIComponent(id)}`
}

export function categoryRoute(id: string): string {
  return `/resources?category=${encodeURIComponent(id)}`
}
