import type { ComponentProps, MouseEvent } from 'react'
import { navigate } from '@/lib/router'

type LinkProps = Omit<ComponentProps<'a'>, 'href'> & { to: string }

export function Link({ to, onClick, target, ...props }: LinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event)
    if (event.defaultPrevented) return
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (target && target !== '_self') return
    event.preventDefault()
    navigate(to)
  }
  return <a href={to} target={target} onClick={handleClick} {...props} />
}
