import { Bullets, Definitions, PageHeader, Section } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import { STATUS_PATH, isRecord } from '@/lib/api'

type Primitive = string | number | boolean | null

// Top-level scalar fields of the live payload; nested values stay in the JSON block below.
function scalarEntries(value: unknown): [string, Primitive][] {
  if (!isRecord(value)) return []
  const entries: [string, Primitive][] = []
  for (const [key, item] of Object.entries(value)) {
    if (item === null || typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
      entries.push([key, item])
    }
  }
  return entries
}

export function StatusPage() {
  const { state, run } = useRequest()
  const entries = state.phase === 'done' ? scalarEntries(state.result.json) : []

  return (
    <article className="space-y-10">
      <PageHeader title={copy.status.title} lede={copy.status.lede} />

      <Section wide title={copy.status.tryHeading}>
        <RequestPanel path={STATUS_PATH} state={state} onRun={() => run(STATUS_PATH)} />
        {entries.length ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.status.resultsHeading}</h3>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{copy.status.columns.field}</TableHead>
                    <TableHead>{copy.status.columns.value}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell className="font-mono text-[13px]">{key}</TableCell>
                      <TableCell className="whitespace-normal break-all font-mono text-[13px]">{String(value)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ) : null}
      </Section>

      <Section title={copy.status.fieldsHeading}>
        <Definitions
          rows={[
            { name: 'state', note: copy.status.fields.freshness },
            { name: 'resourceCount', type: 'number', note: copy.status.fields.resourceCount },
            { name: 'coverage', note: copy.status.fields.coverage },
          ]}
        />
        <Bullets items={[copy.status.note]} />
      </Section>
    </article>
  )
}
