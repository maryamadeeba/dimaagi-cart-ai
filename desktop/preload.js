// Gives the page only what it needs: the backend port and token, a folder picker and the data-folder setting.
const { contextBridge, ipcRenderer } = require('electron')

const { port, token } = ipcRenderer.sendSync('dimaagi:config')

contextBridge.exposeInMainWorld('dimaagi', {
  port,
  token,
  pickFolder: () => ipcRenderer.invoke('dimaagi:pick-folder'),
  dataFolder: {
    get: () => ipcRenderer.invoke('dimaagi:data-folder'),
    check: (dir) => ipcRenderer.invoke('dimaagi:check-folder', dir),
    set: (dir, opts) => ipcRenderer.invoke('dimaagi:set-data-folder', dir, opts),   // null = back to the default
  },
})
