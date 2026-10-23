// Starts Electron with ELECTRON_RUN_AS_NODE cleared: VS Code terminals set it, which makes electron.exe act as plain Node.
const { spawn } = require('node:child_process')
const path = require('node:path')
const electron = require('electron')

const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE
const child = spawn(electron, [path.resolve(__dirname, '..'), ...process.argv.slice(2)], { stdio: 'inherit', env })
child.on('exit', (code) => process.exit(code ?? 0))
