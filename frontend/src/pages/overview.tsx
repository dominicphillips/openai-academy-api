import { useState } from 'react'
import { CodeBlock } from '@/components/code-block'
import { Link } from '@/components/link'
import { Bullets, PageHeader, Section } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  API_BASE,
  CATEGORIES_PATH,
  DEPLOYEDWORK_URL,
  GITHUB_URL,
  HEALTH_PATH,
  OPENAPI_PATH,
  STATUS_PATH,
  curlFor,
  listResourcesPath,
} from '@/lib/api'

const QUICK_START_PATH = listResourcesPath({ limit: 5 })
const TRY_PATHS = [QUICK_START_PATH, CATEGORIES_PATH, STATUS_PATH, HEALTH_PATH]

type EndpointKey = keyof typeof copy.endpoints

const ENDPOINTS: { path: string; to: string; key: EndpointKey }[] = [
  { path: '/v1/resources', to: '/resources', key: 'listResources' },
  { path: '/v1/resources/{id}', to: '/resource', key: 'getResource' },
  { path: '/v1/categories', to: '/categories', key: 'categories' },
  { path: '/v1/status', to: '/status', key: 'status' },
]

const SUPPORT_ENDPOINTS: { path: string; key: EndpointKey }[] = [
  { path: HEALTH_PATH, key: 'health' },
  { path: OPENAPI_PATH, key: 'openapi' },
]

const linkClass = 'underline-offset-4 hover:underline'

export function OverviewPage() {
  const { state, run } = useRequest()
  const [path, setPath] = useState<string>(TRY_PATHS[0])
  const conventions = copy.overview.conventions

  return (
    <article className="space-y-10">
      <PageHeader title={copy.overview.title} lede={copy.overview.lede} />

      <Section wide title={copy.overview.tryHeading} lede={copy.overview.tryLede}>
        <RequestPanel path={path} state={state} onRun={() => run(path)}>
          <div className="space-y-1.5">
            <label htmlFor="try-endpoint" className="text-sm font-medium">
              {copy.overview.endpointLabel}
            </label>
            <Select value={path} onValueChange={setPath}>
              <SelectTrigger id="try-endpoint" className="w-full font-mono text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRY_PATHS.map((option) => (
                  <SelectItem key={option} value={option} className="font-mono text-[13px]">
                    GET {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </RequestPanel>
      </Section>

      <Section title={copy.overview.baseUrlHeading} lede={copy.overview.baseUrlLede}>
        <CodeBlock label={copy.labels.baseUrl} code={API_BASE} wrapToggle={false} />
      </Section>

      <Section title={copy.overview.quickStartHeading} lede={copy.overview.quickStartLede}>
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(QUICK_START_PATH)} />
      </Section>

      <Section title={copy.overview.endpointsHeading} lede={copy.overview.endpointsLede}>
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{copy.overview.endpointColumnPath}</TableHead>
                <TableHead>{copy.overview.endpointColumnDescription}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ENDPOINTS.map((endpoint) => (
                <TableRow key={endpoint.path}>
                  <TableCell className="font-mono text-[13px]">
                    <Link to={endpoint.to} className={linkClass}>
                      <span className="text-muted-foreground">GET </span>
                      {endpoint.path}
                    </Link>
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">{copy.endpoints[endpoint.key]}</TableCell>
                </TableRow>
              ))}
              {SUPPORT_ENDPOINTS.map((endpoint) => (
                <TableRow key={endpoint.path}>
                  <TableCell className="font-mono text-[13px]">
                    <a href={endpoint.path} className={linkClass}>
                      <span className="text-muted-foreground">GET </span>
                      {endpoint.path}
                    </a>
                  </TableCell>
                  <TableCell className="whitespace-normal text-muted-foreground">{copy.endpoints[endpoint.key]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section title={copy.overview.conventionsHeading}>
        <Bullets
          items={[
            conventions.readOnly,
            conventions.cursors,
            conventions.nulls,
            conventions.durations,
            conventions.sources,
            conventions.notExposed,
          ]}
        />
      </Section>

      <Section title={copy.overview.linksHeading} lede={copy.overview.linksLede}>
        <ul className="space-y-1.5 text-sm">
          <li>
            <a href={OPENAPI_PATH} className={linkClass}>
              {copy.nav.openapi}
            </a>{' '}
            <code className="font-mono text-xs text-muted-foreground">{OPENAPI_PATH}</code>
          </li>
          <li>
            <a href={HEALTH_PATH} className={linkClass}>
              {copy.nav.health}
            </a>{' '}
            <code className="font-mono text-xs text-muted-foreground">{HEALTH_PATH}</code>
          </li>
          <li>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={linkClass}>
              {copy.nav.github}
            </a>
          </li>
          <li>
            <a href={DEPLOYEDWORK_URL} target="_blank" rel="noreferrer" className={linkClass}>
              DeployedWork
            </a>
          </li>
        </ul>
      </Section>
    </article>
  )
}
