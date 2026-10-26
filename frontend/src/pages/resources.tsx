import { useEffect, useRef, useState } from 'react'
import { CodeBlock } from '@/components/code-block'
import { Definitions, PageHeader, Section } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { ResourceRow } from '@/components/resource-row'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { copy, fmt } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  CATEGORIES_PATH,
  LIMIT_OPTIONS,
  LIST_LIMIT_DEFAULT,
  LIST_LIMIT_MAX,
  curlFor,
  listResourcesPath,
  queryString,
  toCategoryList,
  toResourceList,
  type ListParams,
} from '@/lib/api'
import { LIST_SHAPE } from '@/lib/examples'
import { unique } from '@/lib/format'
import { navigate } from '@/lib/router'

interface Filters {
  q: string
  category: string
  kind: string
  audience: string
  limit: number
}

const ANY_CATEGORY = '__any__'
const TEXT_FILTERS = ['q', 'category', 'kind', 'audience'] as const

function fromSearch(search: URLSearchParams): Filters {
  const limit = Number(search.get('limit'))
  return {
    q: search.get('q') ?? '',
    category: search.get('category') ?? '',
    kind: search.get('kind') ?? '',
    audience: search.get('audience') ?? '',
    limit: (LIMIT_OPTIONS as readonly number[]).includes(limit) ? limit : LIST_LIMIT_DEFAULT,
  }
}

function toParams(filters: Filters, cursor: string | null = null): ListParams {
  return {
    q: filters.q.trim() || undefined,
    category: filters.category || undefined,
    kind: filters.kind.trim() || undefined,
    audience: filters.audience.trim() || undefined,
    limit: filters.limit,
    cursor: cursor ?? undefined,
  }
}

function hasFilters(filters: Filters): boolean {
  return TEXT_FILTERS.some((key) => filters[key].trim() !== '')
}

// The page URL mirrors the applied filters (without the cursor) so a filtered view can be shared.
function pageRoute(filters: Filters): string {
  const params = toParams(filters)
  return `/resources${queryString({ ...params, limit: filters.limit === LIST_LIMIT_DEFAULT ? undefined : filters.limit })}`
}

const labelClass = 'text-sm font-medium'

export function ResourcesPage({ search }: { search: URLSearchParams }) {
  const list = useRequest()
  const { state: categoryState, run: loadCategories } = useRequest()
  const [form, setForm] = useState<Filters>(() => fromSearch(search))
  const [applied, setApplied] = useState<Filters | null>(null)
  const started = useRef(false)

  function execute(filters: Filters, cursor: string | null) {
    setApplied(filters)
    navigate(pageRoute(filters), { replace: true })
    list.run(listResourcesPath(toParams(filters, cursor)))
  }

  useEffect(() => {
    loadCategories(CATEGORIES_PATH)
  }, [loadCategories])

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (hasFilters(form)) execute(form, null)
    // Only on first mount: a filtered link (for example from a category) runs immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loading = list.state.phase === 'loading'
  const result = list.state.phase === 'done' ? toResourceList(list.state.result.json) : null
  const categoryList = categoryState.phase === 'done' ? toCategoryList(categoryState.result.json) : null
  const categoriesUnavailable =
    categoryState.phase === 'failed' || (categoryState.phase === 'done' && categoryList === null)
  const categoryKnown = categoryList?.items.some((category) => category.id === form.category) ?? false
  // The draft is what Run sends next; the response pane keeps describing its own completed request.
  const draftPath = listResourcesPath(toParams(form))
  const kinds = unique(result?.items.map((item) => item.kind))
  const audiences = unique(result?.items.flatMap((item) => item.audiences))

  return (
    <article className="space-y-10">
      <PageHeader title={copy.resources.title} lede={copy.resources.lede} />

      <Section wide title={copy.resources.tryHeading} lede={copy.resources.tryLede}>
        <RequestPanel path={draftPath} state={list.state} onRun={() => execute(form, null)}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <label htmlFor="filter-q" className={labelClass}>
                {copy.resources.filters.q}
              </label>
              <Input
                id="filter-q"
                type="search"
                autoComplete="off"
                value={form.q}
                onChange={(event) => setForm({ ...form, q: event.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="filter-category" className={labelClass}>
                {copy.resources.filters.category}
              </label>
              <Select
                value={form.category || ANY_CATEGORY}
                onValueChange={(value) => setForm({ ...form, category: value === ANY_CATEGORY ? '' : value })}
              >
                <SelectTrigger id="filter-category" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY_CATEGORY}>{copy.resources.filters.categoryAny}</SelectItem>
                  {form.category && !categoryKnown ? (
                    <SelectItem value={form.category} className="font-mono text-[13px]">
                      {form.category}
                    </SelectItem>
                  ) : null}
                  {categoryList?.items.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {categoriesUnavailable ? (
                <p className="text-xs text-muted-foreground">{copy.resources.filters.categoryUnavailable}</p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <label htmlFor="filter-limit" className={labelClass}>
                {copy.resources.filters.limit}
              </label>
              <Select value={String(form.limit)} onValueChange={(value) => setForm({ ...form, limit: Number(value) })}>
                <SelectTrigger id="filter-limit" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LIMIT_OPTIONS.map((option) => (
                    <SelectItem key={option} value={String(option)}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="filter-kind" className={labelClass}>
                {copy.resources.filters.kind}
              </label>
              <Input
                id="filter-kind"
                list="filter-kind-options"
                autoComplete="off"
                value={form.kind}
                onChange={(event) => setForm({ ...form, kind: event.target.value })}
              />
              <datalist id="filter-kind-options">
                {kinds.map((kind) => (
                  <option key={kind} value={kind} />
                ))}
              </datalist>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="filter-audience" className={labelClass}>
                {copy.resources.filters.audience}
              </label>
              <Input
                id="filter-audience"
                list="filter-audience-options"
                autoComplete="off"
                value={form.audience}
                onChange={(event) => setForm({ ...form, audience: event.target.value })}
              />
              <datalist id="filter-audience-options">
                {audiences.map((audience) => (
                  <option key={audience} value={audience} />
                ))}
              </datalist>
            </div>
          </div>
        </RequestPanel>

        {loading ? (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : null}

        {result ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.resources.resultsHeading}</h3>
            <p className="text-sm text-muted-foreground">
              {result.total === null
                ? fmt(copy.resources.resultsCount, { count: result.items.length })
                : fmt(copy.resources.resultsSummary, { count: result.items.length, total: result.total })}
              {result.snapshotId ? (
                <>
                  {' · '}
                  {copy.resources.snapshotLabel} <code className="break-all font-mono text-xs">{result.snapshotId}</code>
                </>
              ) : null}
            </p>
            {result.items.length === 0 ? (
              <p className="text-sm">{copy.resources.empty}</p>
            ) : (
              <ul className="divide-y rounded-lg border bg-card">
                {result.items.map((resource) => (
                  <ResourceRow key={resource.id} resource={resource} />
                ))}
              </ul>
            )}
            {result.nextCursor && applied ? (
              <Button type="button" variant="outline" onClick={() => execute(applied, result.nextCursor)}>
                {copy.actions.nextPage}
              </Button>
            ) : null}
          </div>
        ) : null}
      </Section>

      <Section title={copy.resources.paramsHeading}>
        <Definitions
          rows={[
            { name: 'q', type: 'string', note: copy.resources.params.q },
            { name: 'category', type: 'string', note: copy.resources.params.category },
            { name: 'kind', type: 'string', note: copy.resources.params.kind },
            { name: 'audience', type: 'string', note: copy.resources.params.audience },
            { name: 'cursor', type: 'string', note: copy.resources.params.cursor },
            {
              name: 'limit',
              type: 'integer',
              note: fmt(copy.resources.params.limit, { default: LIST_LIMIT_DEFAULT, max: LIST_LIMIT_MAX }),
            },
          ]}
        />
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(listResourcesPath({ limit: 5 }))} />
      </Section>

      <Section title={copy.resources.responseHeading} lede={copy.resources.shapeNote}>
        <Definitions
          rows={[
            { name: 'items', type: 'Resource[]', note: copy.resources.response.items },
            { name: 'nextCursor', type: 'string | null', note: copy.resources.response.nextCursor },
            { name: 'total', type: 'number', note: copy.resources.response.total },
            { name: 'snapshotId', type: 'string', note: copy.resources.response.snapshotId },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={LIST_SHAPE} />
      </Section>
    </article>
  )
}
