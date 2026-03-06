import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import assert from 'node:assert/strict'

process.env.HOME = fs.mkdtempSync(path.join(os.tmpdir(), 'ocbridge-home-'))

const pluginModule = await import('../plugin/ocbridge/index.js')
const plugin = pluginModule.default

const setupOut = await plugin.commands['oc-setup']({ args: [] })
assert.match(setupOut, /config skeleton created|config exists/)
assert.match(setupOut, /\.config\/ocbridge\/env/)

const envPath = path.join(process.env.HOME, '.config', 'ocbridge', 'env')
assert.ok(fs.existsSync(envPath), 'env file should be created')

const showOut = await plugin.commands['oc-reconfigure']({ args: ['--show'] })
assert.match(showOut, /current config \(sanitized\)/)

const updateOut = await plugin.commands['oc-reconfigure']({ args: ['OC_NODE_ID=node-test-1', 'RUN_TIMEOUT=1234'] })
assert.match(updateOut, /updated: OC_NODE_ID, RUN_TIMEOUT/)

const reloaded = fs.readFileSync(envPath, 'utf8')
assert.match(reloaded, /export OC_NODE_ID='node-test-1'/)
assert.match(reloaded, /export RUN_TIMEOUT='1234'/)

console.log('plugin ux command smoke passed')
