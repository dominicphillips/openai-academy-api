// Writes or merges the values file from the key schema with every new leaf set to its own key path.
// Usage: node copy-placeholder.mjs [--merge] [--force] [--keys src/copy/keys.json] [--values src/copy/en.json]
// Mechanical placeholder only: real values are written by the copy author.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

const arg = (name, fallback) => { const i = process.argv.indexOf(name); return i > -1 ? process.argv[i + 1] : fallback }
const keysPath = resolve(arg('--keys', 'src/copy/keys.json'))
const valuesPath = resolve(arg('--values', 'src/copy/en.json'))
const force = process.argv.includes('--force')
const merge = process.argv.includes('--merge')
const keys = JSON.parse(readFileSync(keysPath, 'utf8'))

const fill = (o, p = []) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v && typeof v === 'object' ? fill(v, [...p, k]) : [...p, k].join('.')]))

if (existsSync(valuesPath) && merge) {
  const en = JSON.parse(readFileSync(valuesPath, 'utf8'))
  let added = 0
  const walk = (k, e, p = []) =>
    Object.fromEntries(
      Object.entries(k).map(([name, v]) => {
        const path = [...p, name]
        if (v && typeof v === 'object') return [name, walk(v, e && typeof e[name] === 'object' ? e[name] : {}, path)]
        if (e && typeof e[name] === 'string' && e[name] !== '') return [name, e[name]]
        added++
        return [name, path.join('.')]
      }),
    )
  writeFileSync(valuesPath, JSON.stringify(walk(keys, en), null, 2) + '\n')
  console.log(`merged ${valuesPath}: ${added} placeholder(s) added`)
  process.exit(0)
}
if (existsSync(valuesPath) && !force) {
  console.log('values file exists; pass --force to regenerate placeholders, or --merge to add new keys only')
  process.exit(0)
}
writeFileSync(valuesPath, JSON.stringify(fill(keys), null, 2) + '\n')
console.log('wrote', valuesPath)
