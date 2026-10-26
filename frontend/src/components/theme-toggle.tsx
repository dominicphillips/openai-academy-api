import { MoonIcon, SunIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'
import { setTheme, useTheme } from '@/lib/theme'

// The label names the theme the button switches to, not the icon it shows.
export function ThemeToggle({ className }: { className?: string }) {
  const theme = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  const label = next === 'light' ? copy.theme.toggleToLight : copy.theme.toggleToDark
  const Icon = next === 'light' ? SunIcon : MoonIcon
  return (
    <Button type="button" variant="ghost" size="icon-sm" aria-label={label} title={label} onClick={() => setTheme(next)} className={className}>
      <Icon aria-hidden="true" />
    </Button>
  )
}
