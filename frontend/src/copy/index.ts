// Copy module. Keys are defined in keys.json (the designer), values in en.json (the copy author only).
import en from './en.json'

export type Copy = typeof en
export const copy: Copy = en

/** Plain-text substitution. Emphasis markers (`**...**`, see lib/rich.tsx) are dropped here. */
export function fmt(template: string, values: Record<string, string | number>): string {
  return template.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\{(\w+)\}/g, (_, k: string) => (k in values ? String(values[k]) : `{${k}}`))
}
