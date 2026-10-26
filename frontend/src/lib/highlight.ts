// Local, dependency-free tokenizers for the code viewer. Output is plain data (kind + exact text);
// the viewer renders it as escaped React text, so untrusted response bodies never become markup.

export type Language = 'json' | 'bash' | 'text'

export type TokenKind = 'key' | 'string' | 'number' | 'literal' | 'punct' | 'command' | 'flag' | 'plain'

export interface Token {
  kind: TokenKind
  text: string
}

const JSON_NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y
const JSON_LITERAL = /true|false|null/y
const JSON_SIGNIFICANT = new Set('"{}[],:-0123456789tfn')

function tokenizeJson(source: string): Token[] {
  const out: Token[] = []
  const length = source.length
  let i = 0
  while (i < length) {
    const ch = source[i]
    if (ch === '"') {
      let j = i + 1
      while (j < length) {
        if (source[j] === '\\') {
          j += 2
          continue
        }
        if (source[j] === '"') {
          j += 1
          break
        }
        j += 1
      }
      const end = Math.min(j, length)
      let k = end
      while (k < length && (source[k] === ' ' || source[k] === '\t')) k += 1
      out.push({ kind: source[k] === ':' ? 'key' : 'string', text: source.slice(i, end) })
      i = end
      continue
    }
    if (ch === '{' || ch === '}' || ch === '[' || ch === ']' || ch === ',' || ch === ':') {
      out.push({ kind: 'punct', text: ch })
      i += 1
      continue
    }
    if (ch === '-' || (ch >= '0' && ch <= '9')) {
      JSON_NUMBER.lastIndex = i
      const match = JSON_NUMBER.exec(source)
      if (match && match[0].length > 0) {
        out.push({ kind: 'number', text: match[0] })
        i += match[0].length
        continue
      }
    }
    if (ch === 't' || ch === 'f' || ch === 'n') {
      JSON_LITERAL.lastIndex = i
      const match = JSON_LITERAL.exec(source)
      if (match) {
        out.push({ kind: 'literal', text: match[0] })
        i += match[0].length
        continue
      }
    }
    let j = i + 1
    while (j < length && !JSON_SIGNIFICANT.has(source[j])) j += 1
    out.push({ kind: 'plain', text: source.slice(i, j) })
    i = j
  }
  return out
}

const BASH_SEPARATORS = new Set(['|', '||', '&&', ';'])

function tokenizeBashLine(line: string, out: Token[]) {
  const length = line.length
  let i = 0
  let expectCommand = true
  while (i < length) {
    const ch = line[i]
    if (ch === ' ' || ch === '\t') {
      let j = i
      while (j < length && (line[j] === ' ' || line[j] === '\t')) j += 1
      out.push({ kind: 'plain', text: line.slice(i, j) })
      i = j
      continue
    }
    if (ch === '"' || ch === "'") {
      let j = i + 1
      while (j < length && line[j] !== ch) {
        if (ch === '"' && line[j] === '\\') j += 1
        j += 1
      }
      const end = Math.min(j + 1, length)
      out.push({ kind: 'string', text: line.slice(i, end) })
      i = end
      expectCommand = false
      continue
    }
    let j = i
    while (j < length && line[j] !== ' ' && line[j] !== '\t') j += 1
    const word = line.slice(i, j)
    if (BASH_SEPARATORS.has(word)) {
      out.push({ kind: 'punct', text: word })
      expectCommand = true
    } else if (expectCommand) {
      out.push({ kind: 'command', text: word })
      expectCommand = false
    } else {
      out.push({ kind: word.startsWith('-') ? 'flag' : 'plain', text: word })
    }
    i = j
  }
}

function tokenizeBash(source: string): Token[] {
  const out: Token[] = []
  source.split('\n').forEach((line, index) => {
    if (index > 0) out.push({ kind: 'plain', text: '\n' })
    tokenizeBashLine(line, out)
  })
  return out
}

function tokenize(source: string, language: Language): Token[] {
  if (language === 'json') return tokenizeJson(source)
  if (language === 'bash') return tokenizeBash(source)
  return [{ kind: 'plain', text: source }]
}

// Tokens grouped per line, so the viewer can number lines and wrap them independently.
export function tokenizeLines(source: string, language: Language): Token[][] {
  const lines: Token[][] = [[]]
  for (const token of tokenize(source, language)) {
    const parts = token.text.split('\n')
    parts.forEach((part, index) => {
      if (index > 0) lines.push([])
      if (part) lines[lines.length - 1].push({ kind: token.kind, text: part })
    })
  }
  return lines
}
