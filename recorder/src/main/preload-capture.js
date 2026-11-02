'use strict';
// Bridge for the hidden capture window (src/renderer/capture.js).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('recorder', {
  /** Register the RPC handler: fn(method, args) -> Promise<result>. */
  onRpc(fn) {
    ipcRenderer.on('rpc', async (_e, msg) => {
      try {
        const result = await fn(msg.method, msg.args);
        ipcRenderer.send('rpc-reply', { id: msg.id, ok: true, result });
      } catch (err) {
        ipcRenderer.send('rpc-reply', {
          id: msg.id,
          ok: false,
          error: { name: (err && err.name) || 'Error', kind: (err && err.kind) || null, message: String((err && err.message) || err) },
        });
      }
    });
  },
  /** Append a chunk to <stream>.webm; resolves once it is on disk. */
  chunk: (stream, data) => ipcRenderer.invoke('chunk', stream, data),
  level: (v) => ipcRenderer.send('level', v),
  notify: (type, info) => ipcRenderer.send('capture-event', type, info || {}),
});
