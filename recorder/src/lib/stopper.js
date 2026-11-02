'use strict';
// `clipagent-recorder --stop <DIR>`: create take/stop (the running recorder polls for it),
// then by default wait for state.json to reach done/error. Plain Node, no Electron needed.

const fs = require('fs');
const { takePaths } = require('./take');

function readState(file) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; }
}

/** Returns {code, message, state}. */
async function requestStop(sessionDir, { wait = true, timeout = 60, poll = 250 } = {}) {
  const p = takePaths(sessionDir);
  if (!fs.existsSync(p.dir)) return { code: 1, message: `no take directory at ${p.dir}`, state: null };
  const before = readState(p.state);
  if (before && (before.status === 'done' || before.status === 'error')) {
    return { code: before.status === 'done' ? 0 : 1, message: `recorder already finished (status ${before.status})`, state: before };
  }
  fs.writeFileSync(p.stop, String(Date.now() / 1000));
  if (!wait) return { code: 0, message: `stop requested: ${p.stop}`, state: before };
  const deadline = Date.now() + timeout * 1000;
  while (Date.now() < deadline) {
    const st = readState(p.state);
    if (st && st.status === 'done') return { code: 0, message: `take finished (${st.elapsed}s recorded)`, state: st };
    if (st && st.status === 'error') return { code: 1, message: `recorder error: ${st.error}`, state: st };
    await new Promise((r) => setTimeout(r, poll));
  }
  return { code: 2, message: `stop requested but recorder did not finish within ${timeout}s`, state: readState(p.state) };
}

module.exports = { requestStop, readState };
