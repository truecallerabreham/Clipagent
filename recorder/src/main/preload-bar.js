'use strict';
// Bridge for the floating control bar (src/renderer/bar.js).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('bar', {
  onState: (fn) => ipcRenderer.on('bar:state', (_e, s) => fn(s)),
  onLevel: (fn) => ipcRenderer.on('bar:level', (_e, v) => fn(v)),
  onFlash: (fn) => ipcRenderer.on('bar:flash', (_e, kind) => fn(kind)),
  pause: () => ipcRenderer.send('bar:pause'),
  stop: () => ipcRenderer.send('bar:stop'),
  marker: () => ipcRenderer.send('bar:marker'),
});
