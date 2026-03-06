import http from 'node:http'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import assert from 'node:assert/strict'

const events = [
  { ts: 1000.0, payload: { task_id: 'TASK-A', phase: 'queued', node_id: 'node-a', message: 'accepted' } },
  { ts: 1001.0, payload: { task_id: 'TASK-A', phase: 'running', node_id: 'node-a', message: 'model=gpt' } },
  { ts: 1002.0, payload: { task_id: 'TASK-A', phase: 'finished', node_id: 'node-a', message: 'exit=0' } },
]

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1')
  if (u.pathname === '/events') {
    const since = Number(u.searchParams.get('since_ts') || '0')
    const rows = events.filter((e) => Number(e.ts) >= since)
    const body = JSON.stringify({ ok: true, events: rows })
    res.writeHead(200, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(body) })
    res.end(body)
    return
  }
  res.writeHead(404)
  res.end('not found')
})

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port

process.env.HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'ocbridge-home-'))
process.env.OCBRIDGE_API = `http://127.0.0.1:${port}`

const pluginModule = await import('../plugin/ocbridge/index.js')
const plugin = pluginModule.default

const onceOut = await plugin.commands['oc-events']({ args: ['--limit=10'] })
assert.match(onceOut, /task=TASK-A phase=queued node=node-a/)
assert.match(onceOut, /task=TASK-A phase=finished node=node-a/)

const followOut = await plugin.commands['oc-follow']({ args: ['--seconds=1', '--timeout-ms=100', '--limit=10'] })
assert.match(followOut, /following \/events for 1s/)
assert.match(followOut, /task=TASK-A phase=running node=node-a/)

server.close()
console.log('plugin events follow smoke passed')
