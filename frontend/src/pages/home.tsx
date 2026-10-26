import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowRightIcon, LoaderCircleIcon, RotateCcwIcon, SearchIcon } from 'lucide-react'
import { CourseCard } from '@/components/course-card'
import { Link } from '@/components/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { copy, fmt } from '@/copy'
import { useCatalog, type CatalogError } from '@/hooks/use-catalog'
import { useRequest } from '@/hooks/use-request'
import { CATEGORIES_PATH, GITHUB_URL, OPENAPI_PATH, listResourcesPath, queryString, toCategoryList } from '@/lib/api'
import { navigate } from '@/lib/router'
import { statusNote } from '@/lib/status-note'

const PAGE_SIZE = 12
const SEARCH_MAX_LENGTH = 200

interface CatalogFilters {
  q: string
  category: string
}

function filtersFromSearch(search: URLSearchParams): CatalogFilters {
  return { q: search.get('q') ?? '', category: search.get('category') ?? '' }
}

function filterParams(filters: CatalogFilters) {
  return { q: filters.q.trim() || undefined, category: filters.category || undefined }
}

function pathFor(filters: CatalogFilters, cursor: string | null = null): string {
  return listResourcesPath({ ...filterParams(filters), limit: PAGE_SIZE, cursor: cursor ?? undefined })
}

// The page URL mirrors the applied filters so a filtered catalog can be shared and restored.
function homeRoute(filters: CatalogFilters): string {
  return `/${queryString(filterParams(filters))}`
}

function errorText(error: CatalogError): string {
  if (error.kind === 'network') return copy.request.failed
  if (error.kind === 'shape') return copy.errors.unexpected
  return statusNote(error.status) ?? copy.errors.unexpected
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className="inline-flex h-7 items-center rounded-full border px-3 text-[13px] text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:border-signal aria-pressed:bg-signal-soft aria-pressed:text-foreground"
    >
      {children}
    </button>
  )
}

function CardSkeletons() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="overflow-hidden rounded-xl border bg-card">
          <Skeleton className="aspect-[5/3] rounded-none" />
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  )
}

function CatalogFailure({ error, onRetry }: { error: CatalogError; onRetry: () => void }) {
  return (
    <div role="alert" className="space-y-3 rounded-lg border border-destructive/40 bg-card p-4 text-sm">
      <p>{errorText(error)}</p>
      {error.kind === 'network' ? <pre className="overflow-x-auto font-mono text-xs text-muted-foreground">{error.message}</pre> : null}
      {error.kind === 'http' ? (
        <p className="font-mono text-xs text-muted-foreground">
          {fmt(copy.request.statusLine, { status: error.statusText ? `${error.status} ${error.statusText}` : error.status, ms: error.ms })}
        </p>
      ) : null}
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>
        <RotateCcwIcon data-icon="inline-start" aria-hidden="true" />
        {copy.actions.retry}
      </Button>
    </div>
  )
}

// Course overview: a short introduction and author note, then the live catalog from GET /v1/resources.
export function HomePage({ search }: { search: URLSearchParams }) {
  const { state, load } = useCatalog()
  const { state: categoryState, run: loadCategories } = useRequest()
  const searchKey = search.toString()
  const applied = filtersFromSearch(search)
  const [draft, setDraft] = useState(applied.q)
  const [draftFor, setDraftFor] = useState(searchKey)
  const headingId = useId()
  const searchId = useId()

  // A new URL (filter change, history navigation or the Courses link) resets the search draft
  // (state adjusted during render, no effect needed).
  if (draftFor !== searchKey) {
    setDraftFor(searchKey)
    setDraft(applied.q)
  }

  useEffect(() => {
    loadCategories(CATEGORIES_PATH)
  }, [loadCategories])

  // The URL is the source of truth: filter changes navigate, and each new URL loads its first page.
  useEffect(() => {
    load(pathFor(filtersFromSearch(new URLSearchParams(searchKey))), false)
  }, [searchKey, load])

  function applyFilters(next: CatalogFilters) {
    const route = homeRoute(next)
    if (route === homeRoute(applied)) load(pathFor(next), false)
    else navigate(route, { replace: true })
  }

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    applyFilters({ q: draft, category: applied.category })
  }

  const loading = state.phase === 'loading'
  const firstLoad = state.phase === 'idle' || (loading && !state.appending)

  function loadMore() {
    if (state.nextCursor && !loading) load(pathFor(applied, state.nextCursor), true)
  }

  // A rejected cursor (400) or a changed snapshot (409) cannot continue paging, so retry from page one.
  function retry() {
    const { error } = state
    if (state.appending && error?.kind === 'http' && (error.status === 400 || error.status === 409)) load(pathFor(applied), false)
    else if (state.path) load(state.path, state.appending)
  }

  const categoryList = categoryState.phase === 'done' ? toCategoryList(categoryState.result.json) : null
  const categoriesUnavailable = categoryState.phase === 'failed' || (categoryState.phase === 'done' && categoryList === null)
  const categoryKnown = categoryList?.items.some((category) => category.id === applied.category) ?? false
  const unknownCategory = applied.category !== '' && (categoryList !== null || categoriesUnavailable) && !categoryKnown
  // Chips offer only categories that hold resources (the reference keeps the full coverage list);
  // the active category stays visible so it can be cleared.
  const chipCategories = categoryList?.items.filter((category) => category.count !== 0 || category.id === applied.category) ?? []
  const filtered = applied.q.trim() !== '' || applied.category !== ''
  const summary =
    state.items.length === 0
      ? null
      : state.total === null
        ? fmt(copy.resources.resultsCount, { count: state.items.length })
        : fmt(copy.resources.resultsSummary, { count: state.items.length, total: state.total })

  return (
    <div className="space-y-12">
      <header className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:items-end lg:gap-12">
        <div className="space-y-4">
          <h1 className="max-w-[22ch] text-[2rem] leading-[1.1] font-semibold tracking-[-0.025em] sm:text-[2.5rem]">{copy.home.title}</h1>
          <p className="max-w-[62ch] text-base leading-7 text-muted-foreground">{copy.home.lede}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button asChild>
              <Link to="/reference">
                {copy.nav.reference}
                <ArrowRightIcon data-icon="inline-end" aria-hidden="true" />
              </Link>
            </Button>
            <Button asChild variant="outline">
              <a href={OPENAPI_PATH}>{copy.nav.openapi}</a>
            </Button>
            <Button asChild variant="ghost">
              <a href={GITHUB_URL} target="_blank" rel="noreferrer">
                {copy.nav.github}
              </a>
            </Button>
          </div>
        </div>
        <figure className="relative rounded-xl border bg-panel py-5 pr-5 pl-6">
          <span className="absolute inset-y-5 left-0 w-0.5 rounded-full bg-signal" aria-hidden="true" />
          <blockquote className="text-sm leading-6 sm:text-[15px] sm:leading-7">
            <p>{copy.home.authorNote}</p>
          </blockquote>
          <figcaption className="mt-3 text-sm text-muted-foreground">{copy.home.authorByline}</figcaption>
        </figure>
      </header>

      <section aria-labelledby={headingId} className="space-y-5 border-t pt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h2 id={headingId} className="text-xl font-semibold tracking-tight">
            {copy.home.catalogHeading}
          </h2>
          <Link
            to={`/resources${queryString(filterParams(applied))}`}
            className="min-w-0 rounded-sm font-mono text-[11px] leading-5 break-all text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <span className="font-semibold text-signal">GET</span> {pathFor(applied)}
          </Link>
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <form role="search" onSubmit={onSearch} className="flex w-full min-w-0 gap-2 lg:max-w-md">
            <label htmlFor={searchId} className="sr-only">
              {copy.home.searchLabel}
            </label>
            <div className="relative min-w-0 flex-1">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                id={searchId}
                type="search"
                name="q"
                autoComplete="off"
                maxLength={SEARCH_MAX_LENGTH}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="h-9 pl-8"
              />
            </div>
            <Button type="submit" variant="outline" className="h-9">
              {copy.home.searchAction}
            </Button>
          </form>
          <div role="group" aria-label={copy.resources.filters.category} className="flex flex-wrap gap-2">
            <Chip active={applied.category === ''} onClick={() => applyFilters({ q: applied.q, category: '' })}>
              {copy.resources.filters.categoryAny}
            </Chip>
            {unknownCategory ? (
              <Chip active onClick={() => applyFilters({ q: applied.q, category: '' })}>
                <span className="font-mono text-xs">{applied.category}</span>
              </Chip>
            ) : null}
            {chipCategories.map((category) => (
              <Chip
                key={category.id}
                active={applied.category === category.id}
                onClick={() => applyFilters({ q: applied.q, category: applied.category === category.id ? '' : category.id })}
              >
                {category.label}
                {category.count !== null ? <span className="ml-1.5 text-xs text-muted-foreground tabular-nums">{category.count}</span> : null}
              </Chip>
            ))}
          </div>
        </div>
        {categoriesUnavailable ? <p className="text-xs text-muted-foreground">{copy.resources.filters.categoryUnavailable}</p> : null}

        <p role="status" className="min-h-5 text-sm text-muted-foreground">
          {summary}
          {loading ? <span className="sr-only">{copy.request.loading}</span> : null}
        </p>

        {firstLoad ? <CardSkeletons /> : null}

        {state.items.length > 0 ? (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {state.items.map((resource) => (
              <li key={resource.id} className="grid min-w-0">
                <CourseCard resource={resource} />
              </li>
            ))}
          </ul>
        ) : null}

        {state.phase === 'done' && state.items.length === 0 ? (
          <div className="space-y-3 rounded-xl border border-dashed px-6 py-10 text-center">
            <p className="mx-auto max-w-[52ch] text-sm leading-6 text-muted-foreground">{copy.home.empty}</p>
            {filtered ? (
              <Button type="button" variant="outline" size="sm" onClick={() => applyFilters({ q: '', category: '' })}>
                {copy.home.clearFilters}
              </Button>
            ) : null}
          </div>
        ) : null}

        {state.phase === 'failed' && state.error ? <CatalogFailure error={state.error} onRetry={retry} /> : null}

        {state.nextCursor && state.phase !== 'failed' ? (
          <div className="flex justify-center pt-2">
            <Button type="button" variant="outline" aria-disabled={loading} onClick={loadMore}>
              {loading && state.appending ? (
                <LoaderCircleIcon data-icon="inline-start" className="animate-spin" aria-hidden="true" />
              ) : null}
              {copy.home.loadMore}
            </Button>
          </div>
        ) : null}
      </section>
    </div>
  )
}
