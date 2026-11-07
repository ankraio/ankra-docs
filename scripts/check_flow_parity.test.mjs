import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { findProblems, parseCliReference, parseMcpTools, renderTable, withTable } from './check_flow_parity.mjs'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const matrix = JSON.parse(readFileSync(join(root, 'scripts/flow_parity.json'), 'utf8'))
const cliDirectory = join(root, 'reference/cli')
const cli = parseCliReference(
  readdirSync(cliDirectory)
    .filter((file) => file.endsWith('.mdx'))
    .map((file) => readFileSync(join(cliDirectory, file), 'utf8')),
)
const tools = parseMcpTools(readFileSync(join(root, 'platform/mcp-tools.mdx'), 'utf8'))
const row = (cell) => ({ steps: [{ step: 'Step', ui: { page: '/a', action: 'b' }, cli: { gap: 'why' }, mcp: { gap: 'why' }, ...cell }] })

test('the matrix holds against the references in this repository', () => {
  assert.deepEqual(findProblems(matrix, cli, tools), [])
})

test('the eighteen steps the epic names stay on the matrix', () => {
  assert.equal(matrix.steps.length, 18)
})

test('a command the CLI no longer has fails', () => {
  const problems = findProblems(row({ cli: { commands: ['ankra application teleport'] } }), cli, tools)
  assert.deepEqual(problems, ['Step (CLI): "ankra application teleport" is not in reference/cli'])
})

test('a flag the command does not take fails', () => {
  const flags = { 'ankra application deploy': ['--teleport'] }
  const problems = findProblems(row({ cli: { commands: ['ankra application deploy'], flags } }), cli, tools)
  assert.deepEqual(problems, ['Step (CLI): "ankra application deploy" has no --teleport'])
})

test('a flag that is only the prefix of a documented flag fails', () => {
  const sections = new Map([...cli, ['ankra application ship', '## ankra application ship\n\n--set-up-database']])
  const flags = { 'ankra application ship': ['--set'] }
  const problems = findProblems(row({ cli: { commands: ['ankra application ship'], flags } }), sections, tools)
  assert.deepEqual(problems, ['Step (CLI): "ankra application ship" has no --set'])
})

test('a tool the MCP reference does not list fails', () => {
  const problems = findProblems(row({ mcp: { tools: ['teleport_application'] } }), cli, tools)
  assert.deepEqual(problems, ['Step (MCP): "teleport_application" is not on platform/mcp-tools.mdx'])
})

test('a gap with no reason fails, and so does a missing cell', () => {
  assert.deepEqual(findProblems(row({ cli: { gap: ' ' } }), cli, tools), ['Step (CLI): a gap needs its reason'])
  assert.deepEqual(findProblems(row({ mcp: undefined }), cli, tools), ['Step (MCP): no MCP cell'])
})

test('the page carries the table the matrix generates', () => {
  const page = readFileSync(join(root, 'reference/flow-parity.mdx'), 'utf8')
  assert.equal(withTable(page, renderTable(matrix)), page)
})

test('tracker ids stay out of the published table', () => {
  assert.doesNotMatch(renderTable(matrix), /ankra-[a-z0-9]+/)
})
