import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { MenuIcon, XIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'
import { DEPLOYEDWORK_URL, GITHUB_URL, OPENAPI_PATH } from '@/lib/api'
import { Link } from '@/components/link'
import { useLocation } from '@/lib/router'

export type PageKey = 'overview' | 'resources' | 'resourceDetail' | 'categories' | 'status' | 'notFound'

const SECTIONS: { key: Exclude<PageKey, 'notFound'>; to: string }[] = [
  { key: 'overview', to: '/' },
  { key: 'resources', to: '/resources' },
  { key: 'resourceDetail', to: '/resource' },
  { key: 'categories', to: '/categories' },
  { key: 'status', to: '/status' },
]

const navLinkClass =
  'block rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground aria-[current=page]:bg-muted aria-[current=page]:font-medium aria-[current=page]:text-foreground'
const externalLinkClass = 'rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground'

function SectionLinks({ active }: { active: PageKey }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {SECTIONS.map((item) => (
        <li key={item.key}>
          <Link to={item.to} aria-current={active === item.key ? 'page' : undefined} className={navLinkClass}>
            {copy.nav[item.key]}
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
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Link to="/" className="truncate text-sm font-semibold tracking-tight">
            {copy.app.name}
          </Link>
          <nav aria-label={copy.nav.externalLabel} className="ml-auto hidden sm:block">
            <ExternalLinks className="flex items-center gap-1" />
          </nav>
          <Button
            ref={toggleRef}
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto sm:ml-0 lg:hidden"
            aria-expanded={open}
            aria-controls={navId}
            onClick={() => setOpen((value) => !value)}
            onKeyDown={closeOnEscape}
          >
            {open ? <XIcon data-icon="inline-start" aria-hidden="true" /> : <MenuIcon data-icon="inline-start" aria-hidden="true" />}
            {open ? copy.nav.closeMenu : copy.nav.menu}
          </Button>
        </div>
        {/* Inline disclosure: it pushes the page down instead of covering it, and never traps focus. */}
        <nav
          id={navId}
          aria-label={copy.nav.sectionsLabel}
          hidden={!open}
          onKeyDown={closeOnEscape}
          className="border-t px-4 py-3 sm:px-6 lg:hidden"
        >
          <SectionLinks active={active} />
          <ExternalLinks className="mt-2 flex gap-1 border-t pt-2 sm:hidden" />
        </nav>
      </header>
      <div className="mx-auto flex w-full max-w-7xl flex-1 px-4 sm:px-6">
        <aside className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-52 shrink-0 overflow-y-auto border-r py-8 pr-4 lg:block">
          <nav aria-label={copy.nav.sectionsLabel}>
            <SectionLinks active={active} />
          </nav>
        </aside>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 py-8 outline-none lg:pl-10">
          <div className="min-w-0 max-w-3xl">{children}</div>
        </main>
      </div>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
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
