import { useEffect } from 'react'
import { Shell, type PageKey } from '@/components/layout'
import { copy, fmt } from '@/copy'
import { useLocation } from '@/lib/router'
import { CategoriesPage } from '@/pages/categories'
import { HomePage } from '@/pages/home'
import { NotFoundPage } from '@/pages/not-found'
import { OverviewPage } from '@/pages/overview'
import { ResourceDetailPage } from '@/pages/resource-detail'
import { ResourcesPage } from '@/pages/resources'
import { StatusPage } from '@/pages/status'

interface Route {
  page: PageKey
  id?: string
}

// The course overview owns "/"; the API reference overview lives at /reference (the server keeps /docs).
function resolve(pathname: string): Route {
  if (pathname === '/') return { page: 'home' }
  if (pathname === '/reference') return { page: 'overview' }
  if (pathname === '/resources') return { page: 'resources' }
  if (pathname === '/resource') return { page: 'resourceDetail' }
  const detail = pathname.match(/^\/resources\/([^/]+)$/)
  if (detail) return { page: 'resourceDetail', id: decodeURIComponent(detail[1]) }
  if (pathname === '/categories') return { page: 'categories' }
  if (pathname === '/status') return { page: 'status' }
  return { page: 'notFound' }
}

const TITLES: Record<PageKey, () => string> = {
  home: () => copy.home.catalogHeading,
  overview: () => copy.overview.title,
  resources: () => copy.resources.title,
  resourceDetail: () => copy.resource.title,
  categories: () => copy.categories.title,
  status: () => copy.status.title,
  notFound: () => copy.notFound.title,
}

export default function App() {
  const { pathname, search } = useLocation()
  const route = resolve(pathname)
  const title = TITLES[route.page]()

  useEffect(() => {
    document.title = fmt(copy.app.documentTitle, { page: title, site: copy.app.name })
  }, [title])

  let page
  switch (route.page) {
    case 'home':
      page = <HomePage search={search} />
      break
    case 'overview':
      page = <OverviewPage />
      break
    case 'resources':
      page = <ResourcesPage search={search} />
      break
    case 'resourceDetail':
      page = <ResourceDetailPage id={route.id} />
      break
    case 'categories':
      page = <CategoriesPage />
      break
    case 'status':
      page = <StatusPage />
      break
    default:
      page = <NotFoundPage />
  }

  return <Shell active={route.page}>{page}</Shell>
}
