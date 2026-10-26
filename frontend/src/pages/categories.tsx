import { CodeBlock } from '@/components/code-block'
import { Link } from '@/components/link'
import { Definitions, PageHeader, Section } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import { CATEGORIES_PATH, toCategoryList } from '@/lib/api'
import { CATEGORIES_SHAPE } from '@/lib/examples'
import { categoryRoute } from '@/lib/routes'

export function CategoriesPage() {
  const { state, run } = useRequest()
  const result = state.phase === 'done' ? toCategoryList(state.result.json) : null
  const response = copy.categories.response

  return (
    <article className="space-y-10">
      <PageHeader title={copy.categories.title} lede={copy.categories.lede} />

      <Section wide title={copy.categories.tryHeading}>
        <RequestPanel path={CATEGORIES_PATH} state={state} onRun={() => run(CATEGORIES_PATH)} />
        {state.phase === 'loading' ? <Skeleton className="h-32 w-full" aria-hidden="true" /> : null}
        {result ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.categories.resultsHeading}</h3>
            {result.items.length === 0 ? (
              <p className="text-sm">{copy.categories.empty}</p>
            ) : (
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{copy.categories.columns.label}</TableHead>
                      <TableHead>{copy.categories.columns.id}</TableHead>
                      <TableHead className="text-right">{copy.categories.columns.count}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.items.map((category) => (
                      <TableRow key={category.id}>
                        <TableCell className="whitespace-normal">
                          <Link
                            to={categoryRoute(category.id)}
                            className="font-medium underline-offset-4 hover:underline"
                          >
                            {category.label}
                          </Link>
                        </TableCell>
                        <TableCell className="font-mono text-[13px] text-muted-foreground">{category.id}</TableCell>
                        <TableCell className="text-right tabular-nums">{category.count ?? ''}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        ) : null}
      </Section>

      <Section title={copy.categories.responseHeading} lede={copy.categories.shapeNote}>
        <Definitions
          rows={[
            { name: 'items', type: 'Category[]', note: response.items },
            { name: 'items[].id', type: 'string', note: response.id },
            { name: 'items[].label', type: 'string', note: response.label },
            { name: 'items[].count', type: 'number', note: response.count },
            { name: 'snapshotId', type: 'string', note: response.snapshotId },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={CATEGORIES_SHAPE} />
      </Section>
    </article>
  )
}
