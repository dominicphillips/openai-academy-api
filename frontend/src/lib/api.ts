// Code facts about the API: paths, shapes and constants. Prose about them lives in src/copy.

export const API_BASE = 'https://openai-academy.deployedwork.com'
export const GITHUB_URL = 'https://github.com/dominicphillips/openai-academy-api'
export const DEPLOYEDWORK_URL = 'https://deployedwork.com'

export const OPENAPI_PATH = '/openapi.json'
export const HEALTH_PATH = '/health'
export const CATEGORIES_PATH = '/v1/categories'
export const STATUS_PATH = '/v1/status'
export const RESOURCES_PATH = '/v1/resources'

export const LIST_LIMIT_DEFAULT = 20
export const LIST_LIMIT_MAX = 100
export const LIMIT_OPTIONS = [10, 20, 50, 100] as const

// Official cover artwork is public source metadata, separate from license-controlled media. Only
// images under the verified upload path on this host are shown, and only when the artwork's source
// page is an official Academy page listed in the resource's own provenance.
export const ARTWORK_ORIGIN = 'https://d2xo500swnpgl1.cloudfront.net'
export const ARTWORK_PATH_PREFIX = '/uploads/oaiacademy/'
export const ACADEMY_ORIGIN = 'https://academy.openai.com'

const URL_MAX_LENGTH = 2000
const ALT_MAX_LENGTH = 500

export interface ResourceDuration {
  courseMinutes: number | null
  pathMinutes: number | null
  videoSeconds: number | null
}

export interface ResourceDetail {
  audience: string | null
  prerequisites: string[]
  objectives: string[]
  sections: unknown[]
}

export interface Provenance {
  sourceUrls: string[]
  fetchedAt: string | null
  contentHash: string | null
  method: string | null
}

export interface ArtworkReference {
  url: string
  alt: string | null
  sourceUrl: string
}

export interface Resource {
  id: string
  title: string
  url: string
  kind: string
  categoryIds: string[]
  audiences: string[]
  tags: string[]
  summary: string | null
  level: string | null
  duration: ResourceDuration
  detail: ResourceDetail
  media: unknown
  artwork: ArtworkReference | null
  provenance: Provenance
}

export interface ResourceList {
  items: Resource[]
  nextCursor: string | null
  total: number | null
  snapshotId: string | null
}

export interface Category {
  id: string
  label: string
  count: number | null
}

export interface CategoryList {
  items: Category[]
  snapshotId: string | null
}

export type ListParams = {
  q?: string
  category?: string
  kind?: string
  audience?: string
  cursor?: string
  limit?: number
}

type QueryValue = string | number | null | undefined

export function queryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export function listResourcesPath(params: ListParams = {}): string {
  return `${RESOURCES_PATH}${queryString(params)}`
}

export function resourcePath(id: string): string {
  return `${RESOURCES_PATH}/${encodeURIComponent(id)}`
}

export function curlFor(path: string): string {
  return `curl "${API_BASE}${path}"`
}

export interface RequestResult {
  path: string
  status: number
  statusText: string
  ok: boolean
  ms: number
  contentType: string | null
  text: string
  json: unknown
  isJson: boolean
}

// Same-origin request with a root-relative path. The Vite dev server proxies these to the API.
export async function apiRequest(path: string, signal?: AbortSignal): Promise<RequestResult> {
  const started = performance.now()
  const response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  const text = await response.text()
  const ms = Math.round(performance.now() - started)
  let json: unknown
  let isJson = false
  if (text) {
    try {
      json = JSON.parse(text)
      isJson = true
    } catch {
      isJson = false
    }
  }
  return {
    path,
    status: response.status,
    statusText: response.statusText,
    ok: response.ok,
    ms,
    contentType: response.headers.get('content-type'),
    text,
    json,
    isJson,
  }
}

// Tolerant readers so an unexpected payload degrades to the raw JSON view instead of a crash.
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

export function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

// Control characters and backslashes; spaces too, except in an already decoded path.
function hasUnsafeCharacter(value: string, allowSpace = false): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i)
    if (code < 32 || code === 127 || code === 92 || (code === 32 && !allowSpace)) return true
  }
  return false
}

// Repeated decoding exposes encoded traversal, empty segments and smuggled delimiters, as on the server.
function hasSafePath(rawPath: string): boolean {
  let decoded = rawPath
  for (let round = 0; round < 3; round += 1) {
    try {
      decoded = decodeURIComponent(decoded)
    } catch {
      return false
    }
  }
  if (hasUnsafeCharacter(decoded, true) || decoded.includes('//')) return false
  return decoded.split('/').every((segment) => segment !== '.' && segment !== '..')
}

// An HTTPS URL on exactly this origin (default port, no credentials or fragment) under the path prefix.
function allowedUrl(value: string, origin: string, pathPrefix = '/'): URL | null {
  if (value.length > URL_MAX_LENGTH || hasUnsafeCharacter(value) || !value.startsWith(`${origin}${pathPrefix}`)) return null
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return null
  }
  if (url.origin !== origin || url.username || url.password || url.hash || !url.pathname.startsWith(pathPrefix)) return null
  return hasSafePath(value.slice(origin.length).split(/[?#]/, 1)[0]) ? url : null
}

// Optional and additive: older snapshots omit artwork, and a value failing these checks counts as absent.
export function toArtwork(value: unknown, sourceUrls: readonly string[]): ArtworkReference | null {
  if (!isRecord(value) || typeof value.url !== 'string' || typeof value.sourceUrl !== 'string') return null
  const image = allowedUrl(value.url, ARTWORK_ORIGIN, ARTWORK_PATH_PREFIX)
  if (!image || image.pathname.length <= ARTWORK_PATH_PREFIX.length) return null
  if (!sourceUrls.includes(value.sourceUrl) || !allowedUrl(value.sourceUrl, ACADEMY_ORIGIN)) return null
  const alt = typeof value.alt === 'string' ? value.alt.trim() : ''
  return { url: image.href, alt: alt && alt.length <= ALT_MAX_LENGTH ? alt : null, sourceUrl: value.sourceUrl }
}

export function toResource(value: unknown): Resource | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.title !== 'string') return null
  const duration = isRecord(value.duration) ? value.duration : {}
  const detail = isRecord(value.detail) ? value.detail : {}
  const provenance = isRecord(value.provenance) ? value.provenance : {}
  const sourceUrls = stringArray(provenance.sourceUrls)
  return {
    id: value.id,
    title: value.title,
    url: stringOrNull(value.url) ?? '',
    kind: stringOrNull(value.kind) ?? '',
    categoryIds: stringArray(value.categoryIds),
    audiences: stringArray(value.audiences),
    tags: stringArray(value.tags),
    summary: stringOrNull(value.summary),
    level: stringOrNull(value.level),
    duration: {
      courseMinutes: numberOrNull(duration.courseMinutes),
      pathMinutes: numberOrNull(duration.pathMinutes),
      videoSeconds: numberOrNull(duration.videoSeconds),
    },
    detail: {
      audience: stringOrNull(detail.audience),
      prerequisites: stringArray(detail.prerequisites),
      objectives: stringArray(detail.objectives),
      sections: Array.isArray(detail.sections) ? detail.sections : [],
    },
    media: value.media ?? null,
    artwork: toArtwork(value.artwork, sourceUrls),
    provenance: {
      sourceUrls,
      fetchedAt: stringOrNull(provenance.fetchedAt),
      contentHash: stringOrNull(provenance.contentHash),
      method: stringOrNull(provenance.method),
    },
  }
}

export function toResourceList(value: unknown): ResourceList | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null
  const items = value.items.map(toResource).filter((item): item is Resource => item !== null)
  return {
    items,
    nextCursor: stringOrNull(value.nextCursor),
    total: numberOrNull(value.total),
    snapshotId: stringOrNull(value.snapshotId),
  }
}

export function toCategoryList(value: unknown): CategoryList | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null
  const items: Category[] = []
  for (const item of value.items) {
    if (!isRecord(item) || typeof item.id !== 'string') continue
    items.push({ id: item.id, label: stringOrNull(item.label) ?? item.id, count: numberOrNull(item.count) })
  }
  return { items, snapshotId: stringOrNull(value.snapshotId) }
}

// A section entry may be a plain string or an object with a title; anything else has no label.
export function sectionLabel(section: unknown): string | null {
  if (typeof section === 'string') return section
  if (isRecord(section) && typeof section.title === 'string') return section.title
  return null
}
