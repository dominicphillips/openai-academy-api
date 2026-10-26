// Native fallback artwork for catalog cards without permitted media: a tone-on-tone initial from the
// title, a line composition keyed by resource kind, and a hue family chosen by the stable resource ID.
// Everything is drawn from real metadata; nothing imitates provider artwork.
import { enumLabel } from '@/lib/format'

const HUE_FAMILIES = 6

function fnv1a(input: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash >>> 0
}

function initial(title: string): string {
  const match = title.match(/[\p{L}\p{N}]/u)
  return match ? match[0].toUpperCase() : '·'
}

function quarterArc(radius: number): string {
  // Quarter circle centred on the bottom-right corner of the 320x192 canvas.
  return `M 320 ${192 - radius} A ${radius} ${radius} 0 0 0 ${320 - radius} 192`
}

function KindShapes({ kind, variant }: { kind: string; variant: number }) {
  const scale = [0.88, 1, 1.12][variant]
  switch (kind) {
    case 'course':
      return (
        <g>
          {[52, 86, 120].map((radius) => (
            <path key={radius} className="art-line" d={quarterArc(radius * scale)} />
          ))}
        </g>
      )
    case 'learning-path': {
      const lift = (variant - 1) * 14
      const points = [
        [194, 142 + lift],
        [232, 84 - lift],
        [268, 116 + lift],
        [306, 54 - lift],
      ]
      return (
        <g>
          <polyline className="art-line" points={points.map((point) => point.join(',')).join(' ')} />
          {points.map(([x, y]) => (
            <circle key={`${x}-${y}`} className="art-fill" cx={x} cy={y} r="5" />
          ))}
        </g>
      )
    }
    case 'video':
      return (
        <g>
          <circle className="art-line" cx="252" cy="92" r={44 * scale} />
          <line className="art-line" x1="186" y1="92" x2="318" y2="92" />
        </g>
      )
    case 'article':
      return (
        <g>
          {[104, 84, 104, 68, 56].map((width, index) => (
            <line key={index} className="art-line" x1={304 - width} y1={56 + index * 20} x2="304" y2={56 + index * 20} />
          ))}
        </g>
      )
    case 'event':
      return (
        <g>
          <polygon className="art-line" points="214,160 298,40 316,52 232,172" />
          <circle className="art-line" cx={292 - variant * 6} cy="124" r="12" />
        </g>
      )
    case 'collection':
      return (
        <g>
          {[0, 1, 2].flatMap((row) =>
            [0, 1, 2].map((column) => {
              const filled = row * 3 + column === [4, 0, 8][variant]
              return (
                <rect
                  key={`${row}-${column}`}
                  className={filled ? 'art-fill' : 'art-line'}
                  x={210 + column * 32}
                  y={46 + row * 32}
                  width="20"
                  height="20"
                  rx="3"
                />
              )
            }),
          )}
        </g>
      )
    case 'external':
      return (
        <g>
          <line className="art-line" x1="212" y1="140" x2="300" y2="52" />
          <polyline className="art-line" points="250,52 300,52 300,102" />
        </g>
      )
    default:
      return (
        <g>
          {[0, 1, 2].flatMap((row) =>
            [0, 1, 2, 3].map((column) => (
              <circle key={`${row}-${column}`} className="art-fill" cx={212 + column * 28} cy={64 + row * 28} r="3" />
            )),
          )}
        </g>
      )
  }
}

export function Artwork({ seed, kind, title }: { seed: string; kind: string; title: string }) {
  const hash = fnv1a(seed)
  const hue = hash % HUE_FAMILIES
  const variant = (hash >>> 4) % 3
  const label = kind ? enumLabel(kind) : ''
  const labelled = label !== ''
  return (
    <svg
      viewBox="0 0 320 192"
      preserveAspectRatio="xMidYMid slice"
      role={labelled ? 'img' : undefined}
      aria-label={labelled ? label : undefined}
      aria-hidden={labelled ? undefined : true}
      className="art"
      data-hue={hue}
    >
      <rect className="art-field" width="320" height="192" />
      <text className="art-glyph" x="-6" y="212" fontSize="236">
        {initial(title)}
      </text>
      <KindShapes kind={kind} variant={variant} />
      {labelled ? (
        <text className="art-kind" x="16" y="26">
          {label}
        </text>
      ) : null}
    </svg>
  )
}
