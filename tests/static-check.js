const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const projectRoot = path.resolve(__dirname, '..')
const ignored = new Set(['node_modules', 'jinriheshi_starter'])
const files = []

function walk(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) walk(target)
    else files.push(target)
  }
}

walk(projectRoot)

for (const file of files.filter(item => item.endsWith('.json'))) {
  JSON.parse(fs.readFileSync(file, 'utf8'))
}

for (const file of files.filter(item => item.endsWith('.wxml'))) {
  const source = fs.readFileSync(file, 'utf8').replace(/<!--[\s\S]*?-->/g, '')
  const stack = []
  for (const match of source.matchAll(/<(\/)?([a-zA-Z][\w-]*)\b[^>]*?(\/?)>/g)) {
    const [, closing, tag, selfClosing] = match
    if (selfClosing) continue
    if (!closing) stack.push(tag)
    else assert.equal(stack.pop(), tag, `${path.relative(projectRoot, file)} has a mismatched </${tag}>`)
  }
  assert.deepEqual(stack, [], `${path.relative(projectRoot, file)} has unclosed tags`)
}

console.log(`static-check: ${files.filter(item => item.endsWith('.json')).length} JSON and ${files.filter(item => item.endsWith('.wxml')).length} WXML files passed`)
