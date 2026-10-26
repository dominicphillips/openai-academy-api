import { useEffect, useId, useState, type FormEvent } from 'react'
import { ArrowRightIcon, LoaderCircleIcon, RotateCcwIcon, SearchIcon } from 'lucide-react'
import { CourseCard } from '@/components/course-card'
import { Link } from '@/components/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { copy, fmt } from '@/copy'
import { useCatalog, type CatalogError } from '@/hooks/use-catalog'
import { useRequest } from '@/hooks/use-request'
import { CATEGORIES_PATH, GITHUB_URL, OPENAPI_PATH, listResourcesPath, queryString, toCategoryList } from '@/lib/api'
import { navigate } from '@/lib/router'
import { statusNote } from '@/lib/status-note'

const PAGE_SIZE = 12
const SEARCH_MAX_LENGTH = 200
// Prefix category values so the non-empty all-categories sentinel cannot collide with a URL category id.
const ALL_CATEGORIES = '__all__'

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

// Course overview: the author note, then the live catalog from GET /v1/resources.
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
  const activeCategory = categoryList?.items.find((category) => category.id === applied.category)
  // An active URL category the list cannot confirm (loading, unavailable or unknown) stays listed by its raw id.
  const unlistedCategory = applied.category !== '' && activeCategory === undefined
  // The menu offers only categories that hold resources (the reference keeps the full coverage list);
  // the active category stays visible so it can be cleared.
  const categoryOptions = categoryList?.items.filter((category) => category.count !== 0 || category.id === applied.category) ?? []
  const filtered = applied.q.trim() !== '' || applied.category !== ''
  const summary =
    state.items.length === 0
      ? null
      : state.total === null
        ? fmt(copy.resources.resultsCount, { count: state.items.length })
        : fmt(copy.resources.resultsSummary, { count: state.items.length, total: state.total })

  return (
    <div className="space-y-12">
      <header className="max-w-2xl space-y-4">
        <figure className="relative rounded-xl border bg-panel py-5 pr-5 pl-6">
          <span className="absolute inset-y-5 left-0 w-0.5 rounded-full bg-signal" aria-hidden="true" />
          <blockquote className="text-base leading-7 sm:text-[17px]">
            <p>{copy.home.authorNote}</p>
          </blockquote>
          <figcaption className="mt-3 flex items-center gap-3 text-sm text-muted-foreground">
            <img src="/dominic-phillips-avatar.jpg" alt="" width={40} height={40} className="size-10 shrink-0 rounded-full object-cover ring-1 ring-border" />
            <span>{copy.home.authorByline}</span>
          </figcaption>
        </figure>
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
      </header>

      <section aria-labelledby={headingId} className="space-y-5 border-t pt-8">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h1 id={headingId} className="text-xl font-semibold tracking-tight">
            {copy.home.catalogHeading}
          </h1>
          <Link
            to={`/resources${queryString(filterParams(applied))}`}
            className="min-w-0 rounded-sm font-mono text-[11px] leading-5 break-all text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <span className="font-semibold text-signal">GET</span> {pathFor(applied)}
          </Link>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:items-center lg:w-auto">
            <form role="search" onSubmit={onSearch} className="flex min-w-0 gap-2 sm:flex-1 lg:w-96 lg:flex-none">
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
            <Select value={applied.category ? `category:${applied.category}` : ALL_CATEGORIES} onValueChange={(value) => applyFilters({ q: applied.q, category: value === ALL_CATEGORIES ? '' : value.slice('category:'.length) })}>
              <SelectTrigger aria-label={copy.resources.filters.category} className="w-full min-w-0 data-[size=default]:h-9 sm:w-56">
                <SelectValue>
                  {applied.category === '' ? (
                    copy.resources.filters.categoryAny
                  ) : activeCategory ? (
                    activeCategory.label
                  ) : (
                    <span className="truncate font-mono text-xs">{applied.category}</span>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent position="popper" align="start" sideOffset={4}>
                <SelectItem value={ALL_CATEGORIES}>{copy.resources.filters.categoryAny}</SelectItem>
                {unlistedCategory ? (
                  <SelectItem value={`category:${applied.category}`}>
                    <span className="font-mono text-xs">{applied.category}</span>
                  </SelectItem>
                ) : null}
                {categoryOptions.map((category) => (
                  <SelectItem key={category.id} value={`category:${category.id}`} textValue={category.label}>
                    {category.label}
                    {category.count !== null ? <span className="ml-1.5 text-xs text-muted-foreground tabular-nums">{category.count}</span> : null}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <p role="status" className="min-h-5 text-sm text-muted-foreground">
            {summary}
            {loading ? <span className="sr-only">{copy.request.loading}</span> : null}
          </p>
        </div>
        {categoriesUnavailable ? <p className="text-xs text-muted-foreground">{copy.resources.filters.categoryUnavailable}</p> : null}

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
