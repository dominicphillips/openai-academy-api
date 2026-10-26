import { useId, useState } from 'react'
import { ArrowUpRightIcon } from 'lucide-react'
import { Artwork } from '@/components/artwork'
import { Link } from '@/components/link'
import { copy } from '@/copy'
import type { Resource } from '@/lib/api'
import { primaryDuration } from '@/lib/duration'
import { safeHttpUrl } from '@/lib/format'
import { resourceRoute } from '@/lib/routes'

// A card opens the official resource in a new tab; the whole surface is the link, the inspect
// action stays a separate control above it. Validated official artwork shows when it loads; a
// missing, blocked or broken image falls back to the generated artwork.
export function CourseCard({ resource }: { resource: Resource }) {
  const titleId = useId()
  const [imageFailed, setImageFailed] = useState(false)
  const href = safeHttpUrl(resource.url)
  // A single duration keeps cards unambiguous; it is labelled whenever it measures another scope.
  const duration = primaryDuration(resource.kind, resource.duration)
  const artwork = imageFailed ? null : resource.artwork

  return (
    <article className="course-card group relative flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card transition-colors hover:border-foreground/30 focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/50">
      <div className="aspect-[5/3] overflow-hidden border-b bg-panel">
        {artwork ? (
          <img
            src={artwork.url}
            alt={artwork.alt ?? ''}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className="h-full w-full object-cover"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <Artwork seed={resource.id} kind={resource.kind} title={resource.title} />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 id={titleId} className="text-[1.0625rem] leading-snug font-semibold tracking-tight">
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer" className="outline-none after:absolute after:inset-0">
              {resource.title}
              <ArrowUpRightIcon className="ml-1 inline size-3.5 align-[-1px] text-muted-foreground" aria-hidden="true" />
            </a>
          ) : (
            resource.title
          )}
        </h3>
        {resource.summary ? <p className="line-clamp-3 text-sm leading-6 text-muted-foreground">{resource.summary}</p> : null}
        <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 text-xs text-muted-foreground">
          {resource.level ? <span className="capitalize">{resource.level}</span> : null}
          {duration ? (
            <span>
              <span className={duration.matchesKind ? 'sr-only' : undefined}>{duration.entry.label} </span>
              {duration.entry.value}
            </span>
          ) : null}
          <Link
            to={resourceRoute(resource.id)}
            aria-describedby={titleId}
            className="relative z-10 ml-auto rounded-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 outline-none"
          >
            {copy.home.inspect}
          </Link>
        </div>
      </div>
    </article>
  )
}
