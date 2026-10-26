import { PageHeader } from '@/components/doc'
import { Link } from '@/components/link'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'

export function NotFoundPage() {
  return (
    <article className="space-y-6">
      <PageHeader title={copy.notFound.title} lede={copy.notFound.lede} />
      <Button asChild variant="outline">
        <Link to="/">{copy.actions.backHome}</Link>
      </Button>
    </article>
  )
}
