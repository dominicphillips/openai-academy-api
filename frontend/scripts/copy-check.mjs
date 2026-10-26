// Checks the values file against the key schema: same key tree, no empty values, and reports leaves
// still holding the mechanical placeholder (value === key path). --strict fails on any placeholder.
// Usage: node copy-check.mjs [--strict] [--keys src/copy/keys.json] [--values src/copy/en.json]
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i > -1 ? process.argv[i + 1] : fallback }
const keys = JSON.parse(readFileSync(resolve(arg('--keys', 'src/copy/keys.json')), 'utf8'))
const en = JSON.parse(readFileSync(resolve(arg('--values', 'src/copy/en.json')), 'utf8'))

const missing = [], extra = [], empty = [], placeholder = []
const walk = (k, e, p = []) => {
  for (const name of Object.keys(k)) {
    const path = [...p, name].join('.')
    if (!(name in e)) { missing.push(path); continue }
    if (k[name] && typeof k[name] === 'object') {
      if (!e[name] || typeof e[name] !== 'object') { missing.push(path); continue }
      walk(k[name], e[name], [...p, name])
    } else {
      if (typeof e[name] !== 'string' || e[name].trim() === '') empty.push(path)
      else if (e[name] === path) placeholder.push(path)
    }
  }
  for (const name of Object.keys(e)) if (!(name in k)) extra.push([...p, name].join('.'))
}
walk(keys, en)
const report = (label, list) => list.length && console.log(`${label} (${list.length}):\n  ${list.join('\n  ')}`)
report('MISSING', missing); report('EXTRA', extra); report('EMPTY', empty); report('PLACEHOLDER', placeholder)
const strict = process.argv.includes('--strict')
const fail = missing.length || extra.length || empty.length || (strict && placeholder.length)
console.log(fail ? 'copy-check: FAIL' : `copy-check: OK (${placeholder.length} placeholder values${strict ? '' : ' allowed'})`)
process.exit(fail ? 1 : 0)
