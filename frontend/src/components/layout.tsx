import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { MenuIcon, XIcon } from 'lucide-react'
import { Link } from '@/components/link'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'
import { DEPLOYEDWORK_URL, GITHUB_URL, HEALTH_PATH, OPENAPI_PATH } from '@/lib/api'
import { useLocation } from '@/lib/router'
import { cn } from '@/lib/utils'

export type PageKey = 'home' | 'overview' | 'resources' | 'resourceDetail' | 'categories' | 'status' | 'notFound'

type ReferenceKey = Exclude<PageKey, 'home' | 'notFound'>

// Endpoint rail entries pair the existing section labels with the literal route they document.
const REFERENCE_SECTIONS: { key: ReferenceKey; to: string; path?: string }[] = [
  { key: 'overview', to: '/reference' },
  { key: 'resources', to: '/resources', path: '/v1/resources' },
  { key: 'resourceDetail', to: '/resource', path: '/v1/resources/{id}' },
  { key: 'categories', to: '/categories', path: '/v1/categories' },
  { key: 'status', to: '/status', path: '/v1/status' },
]

const PRIMARY: { key: 'courses' | 'reference'; to: string; pages: PageKey[] }[] = [
  { key: 'courses', to: '/', pages: ['home'] },
  { key: 'reference', to: '/reference', pages: ['overview', 'resources', 'resourceDetail', 'categories', 'status'] },
]

const primaryLinkClass =
  'relative block rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground'
const primaryBarClass =
  'md:after:absolute md:after:inset-x-2.5 md:after:-bottom-[13px] md:after:h-0.5 md:after:rounded-full md:after:bg-signal md:after:opacity-0 md:aria-[current=page]:after:opacity-100'
const externalLinkClass = 'rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground'

function PrimaryLinks({ active, inHeader }: { active: PageKey; inHeader: boolean }) {
  return (
    <ul className={cn('flex', inHeader ? 'items-center gap-1' : 'flex-col gap-0.5')}>
      {PRIMARY.map((item) => (
        <li key={item.key}>
          <Link
            to={item.to}
            aria-current={item.pages.includes(active) ? 'page' : undefined}
            className={cn(primaryLinkClass, inHeader && primaryBarClass)}
          >
            {copy.nav[item.key]}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function RailLinks({ active }: { active: PageKey }) {
  return (
    <ul className="flex flex-col">
      {REFERENCE_SECTIONS.map((item) => (
        <li key={item.key}>
          <Link to={item.to} aria-current={active === item.key ? 'page' : undefined} className="rail-link rounded-r-md text-sm">
            <span className="block font-medium">{copy.nav[item.key]}</span>
            {item.path ? <span className="rail-path">GET {item.path}</span> : null}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function ExternalLinks({ className }: { className?: string }) {
  return (
    <ul className={className}>
      <li>
        <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={externalLinkClass}>
          {copy.nav.github}
        </a>
      </li>
      <li>
        <a href={OPENAPI_PATH} className={externalLinkClass}>
          {copy.nav.openapi}
        </a>
      </li>
    </ul>
  )
}

export function Shell({ active, children }: { active: PageKey; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const navId = useId()
  const toggleRef = useRef<HTMLButtonElement>(null)
  const [openedAt, setOpenedAt] = useState(pathname)
  const reference = active !== 'home' && active !== 'notFound'

  // Close the disclosure when the route changes (state adjusted during render, no effect needed).
  if (openedAt !== pathname) {
    setOpenedAt(pathname)
    setOpen(false)
  }

  function closeOnEscape(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      toggleRef.current?.focus()
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:border focus:bg-background focus:px-3 focus:py-2 focus:text-sm"
      >
        {copy.nav.skipToContent}
      </a>
      <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-13 w-full max-w-[90rem] items-center gap-2 px-4 sm:px-6">
          <Link to="/" className="flex min-w-0 items-center gap-2 text-sm font-semibold tracking-tight">
            <span className="truncate">{copy.app.name}</span>
          </Link>
          <nav aria-label={copy.nav.primaryLabel} className="ml-4 hidden md:block">
            <PrimaryLinks active={active} inHeader />
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <nav aria-label={copy.nav.externalLabel} className="hidden sm:block">
              <ExternalLinks className="flex items-center gap-1" />
            </nav>
            <ThemeToggle />
            <Button
              ref={toggleRef}
              type="button"
              variant="outline"
              size="sm"
              className="lg:hidden"
              aria-expanded={open}
              aria-controls={navId}
              onClick={() => setOpen((value) => !value)}
              onKeyDown={closeOnEscape}
            >
              {open ? <XIcon data-icon="inline-start" aria-hidden="true" /> : <MenuIcon data-icon="inline-start" aria-hidden="true" />}
              {open ? copy.nav.closeMenu : copy.nav.menu}
            </Button>
          </div>
        </div>
        {/* Inline disclosure: it pushes the page down instead of covering it, and never traps focus. */}
        <div id={navId} hidden={!open} onKeyDown={closeOnEscape} className="border-t px-4 py-3 sm:px-6 lg:hidden">
          <nav aria-label={copy.nav.primaryLabel} className="md:hidden">
            <PrimaryLinks active={active} inHeader={false} />
          </nav>
          <nav aria-label={copy.nav.sectionsLabel} className="mt-2 border-t pt-2 md:mt-0 md:border-t-0 md:pt-0">
            <RailLinks active={active} />
          </nav>
          <ExternalLinks className="mt-2 flex gap-1 border-t pt-2 sm:hidden" />
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-[90rem] flex-1 px-4 sm:px-6">
        {reference ? (
          <aside className="sticky top-13 hidden h-[calc(100dvh-3.25rem)] w-56 shrink-0 overflow-y-auto border-r py-6 pr-5 lg:block">
            <nav aria-label={copy.nav.sectionsLabel}>
              <RailLinks active={active} />
            </nav>
            <ul className="mt-5 border-t pt-4">
              <li>
                <a href={HEALTH_PATH} className="rail-link rounded-r-md text-sm">
                  <span className="block font-medium">{copy.nav.health}</span>
                  <span className="rail-path">GET {HEALTH_PATH}</span>
                </a>
              </li>
              <li>
                <a href={OPENAPI_PATH} className="rail-link rounded-r-md text-sm">
                  <span className="block font-medium">{copy.nav.openapi}</span>
                  <span className="rail-path">GET {OPENAPI_PATH}</span>
                </a>
              </li>
            </ul>
          </aside>
        ) : null}
        <main id="main" tabIndex={-1} className={cn('min-w-0 flex-1 py-8 outline-none', reference && 'lg:pl-10')}>
          <div className={cn('min-w-0', reference ? 'max-w-6xl' : 'max-w-[76rem]')}>{children}</div>
        </main>
      </div>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-[90rem] flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="max-w-prose">{copy.footer.independence}</p>
          <p className="flex shrink-0 items-center gap-3">
            <span>
              {copy.footer.madeBy}{' '}
              <a href={DEPLOYEDWORK_URL} target="_blank" rel="noreferrer" className="font-medium text-foreground underline-offset-4 hover:underline">
                DeployedWork
              </a>
            </span>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">
              {copy.nav.github}
            </a>
          </p>
        </div>
      </footer>
    </div>
  )
}
