// ocbridge OpenCode command plugin (MVP)
// Provides commands that interact with local ocbridge daemon HTTP API.
// This is a lightweight shim; the daemon owns NATS connection + store.

import http from 'node:http'
import { URL } from 'node:url'
import os from 'node:os'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'

const DEFAULT_BASE = process.env.OCBRIDGE_API || 'http://127.0.0.1:7341'

function ensureSessionId() {
  // Persist per-user session id so multiple TUIs can be distinguished.
  const dir = path.join(os.homedir(), '.local', 'share', 'ocbridge')
  const file = path.join(dir, 'session_id')
  try {
    fs.mkdirSync(dir, { recursive: true })
    if (fs.existsSync(file)) {
      const v = fs.readFileSync(file, 'utf8').trim()
      if (v) return v
    }
    const sid = crypto.randomUUID()
    fs.writeFileSync(file, sid + '\n', 'utf8')
    return sid
  } catch {
    // fallback: still return a stable id for this process
    return crypto.randomUUID()
  }
}

const SESSION_ID = process.env.OCBRIDGE_SESSION_ID || ensureSessionId()

function requestJson(path, { method = 'GET', body = null } = {}) {
  const url = new URL(path, DEFAULT_BASE)
  return new Promise((resolve, reject) => {
    const payload = body ? Buffer.from(JSON.stringify(body)) : null
    const req = http.request(
      {
        method,
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        headers: {
          'content-type': 'application/json',
          'x-session-id': SESSION_ID,
          ...(payload ? { 'content-length': payload.length } : {}),
        },
      },
      (res) => {
        const chunks = []
        res.on('data', (d) => chunks.push(d))
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8')
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}: ${text}`))
            return
          }
          try {
            resolve(text ? JSON.parse(text) : {})
          } catch (e) {
            reject(new Error(`Invalid JSON: ${text.slice(0, 200)}`))
          }
        })
      }
    )
    req.on('error', reject)
    if (payload) req.write(payload)
    req.end()
  })
}

export default {
  name: 'ocbridge',
  description: 'ocbridge commands (inbox/status/reply/mode) via local daemon',
  commands: {
    'oc-status': async () => {
      const st = await requestJson('/status')
      return JSON.stringify(st, null, 2)
    },
    'oc-doctor': async () => {
      const out = await requestJson('/doctor')
      return JSON.stringify(out, null, 2)
    },
    'oc-logs': async ({ args }) => {
      const lines = Number(args?.[0] || 50)
      const out = await requestJson(`/logs?lines=${encodeURIComponent(lines)}`)
      return JSON.stringify(out, null, 2)
    },
    'oc-inbox': async ({ args }) => {
      const limit = Number(args?.[0] || 20)
      const rows = await requestJson(`/inbox?limit=${encodeURIComponent(limit)}`)
      return JSON.stringify(rows, null, 2)
    },
    'oc-pending': async ({ args }) => {
      const limit = Number(args?.[0] || 20)
      const rows = await requestJson(`/pending?limit=${encodeURIComponent(limit)}`)
      return JSON.stringify(rows, null, 2)
    },
    'oc-claim': async ({ args }) => {
      const taskId = args?.[0]
      if (!taskId) throw new Error('usage: /oc-claim <task_id>')
      const out = await requestJson('/claim', {
        method: 'POST',
        body: { task_id: taskId, session_id: SESSION_ID },
      })
      return JSON.stringify(out, null, 2)
    },
    'oc-run': async ({ args }) => {
      const taskId = args?.[0]
      if (!taskId) throw new Error('usage: /oc-run <task_id>')
      const out = await requestJson('/run', {
        method: 'POST',
        body: { task_id: taskId, session_id: SESSION_ID },
      })
      return JSON.stringify(out, null, 2)
    },
    'oc-reply': async ({ args }) => {
      const taskId = args?.[0]
      const text = args?.slice(1).join(' ')
      if (!taskId || !text) throw new Error('usage: /oc-reply <task_id> <text>')
      const out = await requestJson('/publish', {
        method: 'POST',
        body: { kind: 'chat', task_id: taskId, text, session_id: SESSION_ID },
      })
      return JSON.stringify(out, null, 2)
    },
    'oc-session': async () => {
      return JSON.stringify({ session_id: SESSION_ID }, null, 2)
    },
    'oc-whoami': async () => {
      const out = await requestJson('/whoami')
      return JSON.stringify(out, null, 2)
    },
    'oc-mode': async ({ args }) => {
      const mode = (args?.[0] || '').toLowerCase()
      if (!mode || (mode !== 'auto' && mode !== 'manual')) throw new Error('usage: /oc-mode auto|manual')
      const out = await requestJson('/mode', {
        method: 'POST',
        body: { mode },
      })
      return JSON.stringify(out, null, 2)
    },
  },
}
