// ocbridge OpenCode command plugin (MVP)
// Provides commands that interact with local ocbridge daemon HTTP API.
// This is a lightweight shim; the daemon owns NATS connection + store.

import http from 'node:http'
import { URL } from 'node:url'

const DEFAULT_BASE = process.env.OCBRIDGE_API || 'http://127.0.0.1:7341'

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
    'oc-inbox': async ({ args }) => {
      const limit = Number(args?.[0] || 20)
      const rows = await requestJson(`/inbox?limit=${encodeURIComponent(limit)}`)
      return JSON.stringify(rows, null, 2)
    },
    'oc-reply': async ({ args }) => {
      const taskId = args?.[0]
      const text = args?.slice(1).join(' ')
      if (!taskId || !text) throw new Error('usage: /oc-reply <task_id> <text>')
      const out = await requestJson('/publish', {
        method: 'POST',
        body: { kind: 'chat', task_id: taskId, text },
      })
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
