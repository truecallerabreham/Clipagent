'use strict';
// Global input capture. Picks a source and feeds raw input (see src/lib/events.js) to onRaw:
//   uiohook  - uiohook-napi global hooks (macOS, Windows, Linux X11)
//   evdev    - /dev/input/event* read in a child process (Linux Wayland, or X11 without uiohook)
//   none     - nothing available; `warning` says why and how to fix it
// Override with CLIPAGENT_INPUT=uiohook|evdev|none.

const path = require('path');
const { fork } = require('child_process');
const { performance } = require('perf_hooks');
const { invertUiohookKeys } = require('../lib/keys');
const { EvdevTranslator } = require('../lib/evdev');

const now = () => performance.timeOrigin + performance.now();

const INPUT_GROUP_HELP = 'add yourself to the "input" group to record clicks and shortcuts: `sudo usermod -aG input $USER`, then log out and back in';

function isWayland() {
  return process.platform === 'linux' && (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
}

function startUiohook(onRaw) {
  let mod;
  try {
    mod = require('uiohook-napi');
  } catch (e) {
    return { error: `uiohook-napi could not be loaded (${e.message.split('\n')[0]})` };
  }
  const { uIOhook, UiohookKey } = mod;
  const names = invertUiohookKeys(UiohookKey);
  const held = new Set();
  const buttons = { 1: 'left', 2: 'right', 3: 'middle', 4: 'back', 5: 'forward' };
  const mods = (e) => ({ ctrl: !!e.ctrlKey, alt: !!e.altKey, shift: !!e.shiftKey, meta: !!e.metaKey });
  uIOhook.on('keydown', (e) => {
    if (held.has(e.keycode)) return; // autorepeat
    held.add(e.keycode);
    onRaw({ kind: 'key', name: names[e.keycode] || null, mods: mods(e), ts: now() });
  });
  uIOhook.on('keyup', (e) => held.delete(e.keycode));
  uIOhook.on('mousedown', (e) => onRaw({ kind: 'down', button: buttons[e.button] || 'left', x: e.x, y: e.y, ts: now() }));
  const move = (e) => onRaw({ kind: 'move', x: e.x, y: e.y, ts: now() });
  uIOhook.on('mousemove', move);
  uIOhook.on('mousedrag', move);
  uIOhook.on('wheel', (e) => {
    if (e.direction !== 3) return; // vertical only
    onRaw({ kind: 'wheel', dy: e.rotation, x: e.x, y: e.y, ts: now() });
  });
  try {
    uIOhook.start();
  } catch (e) {
    return { error: `uiohook failed to start (${e.message})` };
  }
  return { source: 'uiohook', warning: null, stop: () => { try { uIOhook.stop(); } catch { /* ignore */ } } };
}

/** Starts the evdev worker; resolves once it reports which devices it could open. */
function startEvdev(onRaw, log) {
  return new Promise((resolve) => {
    const translator = new EvdevTranslator();
    let child;
    try {
      child = fork(path.join(__dirname, 'evdev-worker.js'), [], {
        env: { ...process.env, ELECTRON_RUN_AS_NODE: '1', UV_THREADPOOL_SIZE: '64' },
        stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
      });
    } catch (e) {
      resolve({ error: `evdev worker failed to start (${e.message})` });
      return;
    }
    let settled = false;
    const done = (r) => { if (!settled) { settled = true; clearTimeout(timer); resolve(r); } };
    const timer = setTimeout(() => { child.kill(); done({ error: 'evdev worker did not respond' }); }, 5000);
    child.on('message', (m) => {
      if (m.type === 'ready') {
        log(`evdev: reading ${m.devices.map((d) => `${d.path} (${d.kind}: ${d.name})`).join(', ')}`);
        done({ source: 'evdev', warning: m.warning || null, stop: () => child.kill() });
      } else if (m.type === 'unavailable') {
        done({ error: m.reason, permission: !!m.permission });
      } else if (m.type === 'events') {
        for (const [ts, type, code, value] of m.events) {
          const raw = translator.feed({ ts, type, code, value });
          if (raw) onRaw(raw);
        }
      } else if (m.type === 'log') {
        log(`evdev: ${m.message}`);
      }
    });
    child.on('error', (e) => done({ error: `evdev worker error (${e.message})` }));
    child.on('exit', (code) => done({ error: `evdev worker exited (${code})` }));
  });
}

/**
 * @returns {Promise<{source:'uiohook'|'evdev'|'none', warning:string|null, stop:()=>void}>}
 */
async function startInput({ onRaw, log = () => {}, systemPreferences = null }) {
  const forced = process.env.CLIPAGENT_INPUT;
  const none = (warning) => ({ source: 'none', warning, stop: () => {} });
  if (forced === 'none') return none('input capture disabled (CLIPAGENT_INPUT=none)');

  const problems = [];
  const tryEvdev = async () => {
    const r = await startEvdev(onRaw, log);
    if (!r.error) return r;
    problems.push(r.error);
    if (r.permission) return none(`cannot read /dev/input (${r.error}); ${INPUT_GROUP_HELP}. Clicks and shortcuts were not recorded.`);
    return null;
  };

  if (forced === 'evdev' || (forced !== 'uiohook' && isWayland())) {
    if (process.platform !== 'linux') return none('evdev input is only available on Linux');
    const r = await tryEvdev();
    if (r) return r;
    return none(`no global input source on Wayland (${problems.join('; ')}). Clicks and shortcuts were not recorded.`);
  }

  if (process.platform === 'darwin' && systemPreferences && !systemPreferences.isTrustedAccessibilityClient(false)) {
    return none('macOS Accessibility permission missing: enable ClipAgent Recorder (or your terminal in dev) in System Settings > Privacy & Security > Accessibility and Input Monitoring, then restart the recorder. Clicks and shortcuts were not recorded.');
  }

  const u = startUiohook(onRaw);
  if (!u.error) return u;
  problems.push(u.error);
  if (process.platform === 'linux') {
    const r = await tryEvdev();
    if (r) return r;
  }
  return none(`no global input source (${problems.join('; ')}). Clicks and shortcuts were not recorded.`);
}

module.exports = { startInput, isWayland, INPUT_GROUP_HELP };
