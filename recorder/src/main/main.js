'use strict';
// ClipAgent recorder: Electron main process.
// Writes a Take into <SESSION>/take/ following Contract 1 in docs/design.md.

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { performance } = require('perf_hooks');
const {
  app, BrowserWindow, ipcMain, session, desktopCapturer, screen, globalShortcut, systemPreferences,
} = require('electron');

const { parseArgs, userArgv, UsageError, USAGE } = require('../lib/cli');
const { requestStop } = require('../lib/stopper');
const { RecordingClock } = require('../lib/clock');
const { EventNormalizer } = require('../lib/events');
const { matchHotkey, ACCELERATORS } = require('../lib/keys');
const { matchDisplay, overlayRect, inputRect, barPosition, physicalSize } = require('../lib/geometry');
const {
  takePaths, writeState, writeTake, EventsWriter, assertFreshTake, APP_VERSION,
} = require('../lib/take');
const { startInput, isWayland } = require('./input');

const now = () => performance.timeOrigin + performance.now();
const log = (...a) => console.log(`[recorder ${new Date().toISOString()}]`, ...a);
const RENDERER = path.join(__dirname, '..', 'renderer');
const START_TIMEOUT = Number(process.env.CLIPAGENT_START_TIMEOUT || 180) * 1000; // portal dialog may wait on the user

// Exit codes: 0 ok, 1 runtime error, 2 usage error, 3 permission / device error.
const EXIT = { OK: 0, ERROR: 1, USAGE: 2, DEVICE: 3 };

// ------------------------------------------------------------------ argv

let opts;
try {
  opts = parseArgs(userArgv(process.argv, app.isPackaged));
  for (const w of opts.warnings) console.error(`clipagent-recorder: ${w}`);
} catch (e) {
  if (!(e instanceof UsageError)) throw e;
  console.error(`clipagent-recorder: ${e.message}\n\n${USAGE}`);
  process.exit(EXIT.USAGE);
}

// ------------------------------------------------------------------ RPC with the capture window

class CaptureRpc {
  constructor() {
    this.win = null;
    this.seq = 0;
    this.pending = new Map();
    ipcMain.on('rpc-reply', (_e, m) => {
      const p = this.pending.get(m.id);
      if (!p) return;
      this.pending.delete(m.id);
      clearTimeout(p.timer);
      if (m.ok) p.resolve(m.result);
      else p.reject(Object.assign(new Error(m.error.message), { kind: m.error.kind, errName: m.error.name }));
    });
  }

  async open() {
    this.win = new BrowserWindow({
      show: false,
      width: 320,
      height: 240,
      webPreferences: {
        preload: path.join(__dirname, 'preload-capture.js'),
        contextIsolation: true,
        backgroundThrottling: false,
      },
    });
    await this.win.loadFile(path.join(RENDERER, 'capture.html')); // capture.js has registered its RPC handler
    return this.win;
  }

  call(method, args = {}, timeout = 15000) {
    return new Promise((resolve, reject) => {
      if (!this.win || this.win.isDestroyed()) { reject(new Error('capture window is gone')); return; }
      const id = ++this.seq;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`capture ${method} timed out after ${Math.round(timeout / 1000)} s`));
      }, timeout);
      this.pending.set(id, { resolve, reject, timer });
      this.win.webContents.send('rpc', { id, method, args });
    });
  }

  rejectAll(err) {
    for (const [id, p] of this.pending) { clearTimeout(p.timer); p.reject(err); this.pending.delete(id); }
  }
}

function setupPermissions() {
  const ses = session.defaultSession;
  const allowed = new Set(['media', 'display-capture', 'mediaKeySystem']);
  ses.setPermissionRequestHandler((_wc, permission, cb) => cb(allowed.has(permission)));
  ses.setPermissionCheckHandler((_wc, permission) => allowed.has(permission));
}

function displaysInfo() {
  const primary = screen.getPrimaryDisplay();
  return screen.getAllDisplays().map((d) => ({
    id: String(d.id),
    label: d.label || '',
    primary: d.id === primary.id,
    width: physicalSize(d).width,
    height: physicalSize(d).height,
    scale: d.scaleFactor,
    bounds: d.bounds,
  }));
}

// ------------------------------------------------------------------ --list-devices

async function listDevices() {
  setupPermissions();
  const rpc = new CaptureRpc();
  let devices = { cameras: [], mics: [] };
  let error = null;
  try {
    await rpc.open();
    devices = await rpc.call('enumerate', {}, 20000);
  } catch (e) {
    error = e.message;
  }
  const out = { displays: displaysInfo(), cameras: devices.cameras, mics: devices.mics };
  if (isWayland()) out.note = 'Wayland: the screen-share portal dialog chooses the display; --display is ignored';
  if (error) out.error = error;
  process.stdout.write(JSON.stringify(out, null, 2) + '\n');
  app.exit(error ? EXIT.ERROR : EXIT.OK);
}

// ------------------------------------------------------------------ recording

class Recorder {
  constructor(o) {
    this.opts = o;
    this.paths = takePaths(o.session);
    this.status = 'starting';
    this.clock = new RecordingClock();
    this.rpc = new CaptureRpc();
    this.files = {};
    this.events = null;
    this.normalizer = null;
    this.input = { source: 'none', warning: null, stop: () => {} };
    this.bar = null;
    this.display = null;
    this.overlay = null;
    this.started = null;
    this.timers = [];
    this.lastAction = {};
    this.busy = false;
    this.ownsState = false;
    this.micLabel = null;
  }

  setState(status, extra = {}) {
    this.status = status;
    if (!this.ownsState) return;
    const elapsed = extra.elapsed !== undefined ? extra.elapsed : (this.clock.started ? this.clock.elapsed(now()) : 0);
    try { writeState(this.paths, status, { error: extra.error || null, elapsed }); } catch (e) { log('state write failed:', e.message); }
    this.pushBar();
  }

  async fail(message, code = EXIT.ERROR) {
    console.error(`clipagent-recorder: error: ${message}`);
    this.setState('error', { error: message });
    this.cleanup();
    app.exit(code);
  }

  cleanup() {
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
    try { globalShortcut.unregisterAll(); } catch { /* ignore */ }
    try { this.input.stop(); } catch { /* ignore */ }
    for (const fd of Object.values(this.files)) { try { fs.closeSync(fd); } catch { /* ignore */ } }
    this.files = {};
    if (this.events) this.events.close();
  }

  writeChunk(stream, data) {
    if (!['screen', 'camera', 'mic'].includes(stream)) throw new Error(`unknown stream ${stream}`);
    if (!(stream in this.files)) this.files[stream] = fs.openSync(this.paths[stream], 'w');
    const buf = Buffer.from(data.buffer, data.byteOffset, data.byteLength);
    fs.writeSync(this.files[stream], buf);
  }

  pushBar() {
    if (!this.bar || this.bar.isDestroyed()) return;
    this.bar.webContents.send('bar:state', {
      status: this.status,
      elapsed: this.clock.started ? this.clock.elapsed(now()) : 0,
      mic: !!this.opts.mic,
    });
  }

  // ---- startup

  async start() {
    const p = this.paths;
    try {
      fs.mkdirSync(p.dir, { recursive: true });
      assertFreshTake(p);
    } catch (e) {
      // Never touch an existing Take (not even its state.json).
      console.error(`clipagent-recorder: error: ${e.message}`);
      app.exit(EXIT.USAGE);
      return;
    }
    this.ownsState = true;
    try { fs.unlinkSync(p.stop); } catch { /* no stale stop file */ }
    this.setState('starting');
    log(`clipagent-recorder ${APP_VERSION} on ${process.platform} (${isWayland() ? 'wayland' : 'native'}); take: ${p.dir}`);

    // Stop requested while still starting = cancel.
    this.timers.push(setInterval(() => this.pollStop(), 250));
    for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => { log(`${sig} received`); this.requestStop(sig); });
    if (process.platform !== 'win32') {
      process.on('SIGUSR1', () => this.action('pause')); // scriptable pause/resume
      process.on('SIGUSR2', () => this.action('marker')); // scriptable Scratch Marker
    }
    // A quit from outside (Electron maps SIGTERM to app.quit, logout, ...) finalizes the Take first.
    app.on('will-quit', (e) => {
      if (['done', 'error'].includes(this.status)) return;
      e.preventDefault();
      this.requestStop('quit');
    });
    if (process.env.CLIPAGENT_RESPAWNED && process.platform !== 'win32') {
      // Launched by our own re-exec: stop if that parent disappears (e.g. it was SIGKILLed).
      const parent = process.ppid;
      const dog = setInterval(() => {
        try { process.kill(parent, 0); } catch { clearInterval(dog); this.requestStop('parent process exited'); }
      }, 1000);
    }

    if (process.platform === 'darwin') {
      const st = systemPreferences.getMediaAccessStatus('screen');
      if (st === 'denied' || st === 'restricted') {
        return this.fail('macOS Screen Recording permission denied: enable ClipAgent Recorder (or your terminal in dev) in System Settings > Privacy & Security > Screen Recording, then restart it', EXIT.DEVICE);
      }
      if (this.opts.camera !== 'none' && !(await systemPreferences.askForMediaAccess('camera'))) {
        if (this.opts.camera !== null) return this.fail('macOS Camera permission denied: enable it in System Settings > Privacy & Security > Camera, or pass --camera none', EXIT.DEVICE);
        this.opts.camera = 'none';
      }
      if (this.opts.mic && !(await systemPreferences.askForMediaAccess('microphone'))) {
        return this.fail('macOS Microphone permission denied: enable it in System Settings > Privacy & Security > Microphone, or pass --no-mic', EXIT.DEVICE);
      }
    }

    const displays = screen.getAllDisplays();
    const primary = screen.getPrimaryDisplay();
    let target = primary;
    if (this.opts.display !== null) {
      target = displays.find((d) => String(d.id) === String(this.opts.display));
      if (!target) {
        return this.fail(`display ${this.opts.display} not found; available: ${displays.map((d) => d.id).join(', ')} (see --list-devices)`, EXIT.USAGE);
      }
      if (isWayland()) log('Wayland: the portal dialog chooses the display; --display only sets the expected size');
    }
    const useSystemPicker = process.platform === 'darwin' && this.opts.display === null;

    setupPermissions();
    session.defaultSession.setDisplayMediaRequestHandler((_req, cb) => {
      desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } })
        .then((sources) => {
          if (!sources.length) { log('no screen source granted'); cb(null); return; }
          const src = sources.find((s) => s.display_id === String(target.id)) || sources[0];
          log(`capturing source "${src.name}" (display_id ${src.display_id || '?'})`);
          cb({ video: src });
        })
        .catch((e) => { log('getSources failed:', e.message); cb(null); });
    }, { useSystemPicker });

    ipcMain.handle('chunk', (_e, stream, data) => this.writeChunk(stream, data));
    ipcMain.on('level', (_e, v) => { if (this.bar && !this.bar.isDestroyed()) this.bar.webContents.send('bar:level', v); });
    ipcMain.on('capture-event', (_e, type, info) => this.onCaptureEvent(type, info));
    ipcMain.on('bar:pause', () => this.action('pause'));
    ipcMain.on('bar:stop', () => this.action('stop'));
    ipcMain.on('bar:marker', () => this.action('marker'));

    let started;
    try {
      const win = await this.rpc.open();
      win.webContents.on('render-process-gone', (_e, d) => this.onCaptureGone(d.reason));
      const size = physicalSize(target);
      started = await this.rpc.call('start', {
        camera: this.opts.camera,
        mic: this.opts.mic,
        width: size.width,
        height: size.height,
        fakeScreen: !!process.env.CLIPAGENT_FAKE_SCREEN,
        screenCodec: process.env.CLIPAGENT_SCREEN_CODEC || 'vp9',
        screenBitrate: Number(process.env.CLIPAGENT_SCREEN_BITRATE) || undefined,
      }, START_TIMEOUT);
    } catch (e) {
      const code = (e.kind || /permission|not found|busy|cancel/i.test(e.message)) ? EXIT.DEVICE : EXIT.ERROR;
      return this.fail(e.message, code);
    }
    if (this.status !== 'starting') return; // cancelled meanwhile

    this.started = started;
    this.clock.start(started.t0);
    this.events = new EventsWriter(p.events);
    for (const n of started.notes || []) log(n);
    log(`recording: screen ${started.screen.width}x${started.screen.height} (${started.screen.mimeType})`
      + `${started.camera ? `, camera "${started.camera.label}"` : ''}${started.mic ? `, mic "${started.mic.label}"` : ''}`);

    // Which display did we get? (portal / system picker may choose any)
    const pickerChose = useSystemPicker || isWayland();
    this.display = matchDisplay(displays, {
      id: pickerChose ? null : target.id,
      width: started.screen.width,
      height: started.screen.height,
      primaryId: primary.id,
    });

    this.normalizer = new EventNormalizer({
      clock: this.clock,
      sink: (ev) => this.events.write(ev),
      rect: this.display ? inputRect(this.display, process.platform, (r) => screen.dipToScreenRect(null, r)) : null,
      platform: process.platform,
    });

    this.createBar();
    this.registerHotkeys();
    this.setState('recording');
    this.timers.push(setInterval(() => this.pushBar(), 250));
    this.timers.push(setInterval(() => { if (this.status === 'recording') this.setState('recording'); }, 1000));

    this.input = await startInput({
      onRaw: (raw) => this.onRaw(raw),
      log,
      systemPreferences: process.platform === 'darwin' ? systemPreferences : null,
    });
    log(`input source: ${this.input.source}${this.input.warning ? ` (warning: ${this.input.warning})` : ''}`);
    if (this.status === 'stopping' || this.status === 'done') this.input.stop();
  }

  createBar() {
    const d = this.display || screen.getPrimaryDisplay();
    const rect = barPosition(d.workArea, { width: 236, height: 48 });
    const linux = process.platform === 'linux';
    const bar = new BrowserWindow({
      ...rect,
      frame: false,
      transparent: true,
      resizable: false,
      movable: !linux, // on Linux the bar is visible in the capture: keep it where overlay_rect says
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      hasShadow: false,
      show: false,
      title: 'ClipAgent Recorder',
      webPreferences: { preload: path.join(__dirname, 'preload-bar.js'), contextIsolation: true },
    });
    bar.setAlwaysOnTop(true, 'screen-saver');
    try { bar.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true }); } catch { /* unsupported */ }
    bar.setContentProtection(true); // excluded from capture on macOS / Windows
    bar.loadFile(path.join(RENDERER, 'bar.html'));
    bar.once('ready-to-show', () => {
      bar.showInactive();
      bar.setBounds(rect);
      this.pushBar();
      this.updateOverlay();
    });
    bar.on('moved', () => this.updateOverlay());
    this.bar = bar;
  }

  updateOverlay() {
    // setContentProtection has no effect on Linux: record where the bar sits so the engine can hide it.
    if (process.platform !== 'linux' || !this.bar || this.bar.isDestroyed() || !this.display) return;
    const b = this.bar.getBounds();
    const inset = { x: b.x + 2, y: b.y + 2, width: b.width - 4, height: b.height - 4 }; // drop transparent margin
    this.overlay = overlayRect(inset, this.display.bounds);
  }

  registerHotkeys() {
    for (const [action, acc] of Object.entries(ACCELERATORS)) {
      let ok = false;
      try { ok = globalShortcut.register(acc, () => this.action(action)); } catch (e) { log(`hotkey ${acc}: ${e.message}`); }
      if (!ok) log(`hotkey ${acc} (${action}) could not be registered globally${isWayland() ? ' (Wayland: detected through evdev when /dev/input is readable)' : ''}`);
    }
  }

  onRaw(raw) {
    if (!this.normalizer) return;
    if (raw.kind === 'key') {
      const hk = matchHotkey(raw.name, raw.mods || {}, process.platform);
      if (hk) { this.action(hk); return; } // recorder hotkeys are not recorded as shortcuts
    }
    this.normalizer.input(raw);
  }

  /** stop | pause | marker, debounced (globalShortcut and the input hook may both fire). */
  action(name) {
    const t = Date.now();
    if (this.lastAction[name] && t - this.lastAction[name] < 400) return;
    this.lastAction[name] = t;
    if (name === 'stop') this.requestStop('stop');
    else if (name === 'pause') this.togglePause();
    else if (name === 'marker') this.marker();
  }

  marker() {
    if (!this.normalizer || !['recording', 'paused'].includes(this.status)) return;
    const ev = this.normalizer.marker(now(), 'scratch');
    log(`scratch marker at ${ev && ev.t}s`);
    if (this.bar && !this.bar.isDestroyed()) this.bar.webContents.send('bar:flash', 'scratch');
  }

  async togglePause() {
    if (this.busy || !['recording', 'paused'].includes(this.status)) return;
    this.busy = true;
    try {
      if (this.status === 'recording') {
        const { at } = await this.rpc.call('pause');
        const t = this.clock.pause(at);
        if (t !== null) this.normalizer.control('pause', t);
        this.setState('paused');
        log(`paused at ${t === null ? "?" : t.toFixed(3)}s`);
      } else {
        const { at } = await this.rpc.call('resume');
        const t = this.clock.resume(at);
        if (t !== null) this.normalizer.control('resume', t);
        this.setState('recording');
        log(`resumed at ${t === null ? "?" : t.toFixed(3)}s`);
      }
    } catch (e) {
      log('pause/resume failed:', e.message);
    } finally {
      this.busy = false;
    }
  }

  pollStop() {
    if (fs.existsSync(this.paths.stop)) this.requestStop('stop file');
  }

  onCaptureEvent(type, info) {
    if (type === 'ended') { log(`${info.stream} capture ended by the system (share stopped)`); this.requestStop('share ended'); return; }
    if (type === 'error') log('capture error:', info.message);
  }

  onCaptureGone(reason) {
    if (['done', 'error'].includes(this.status)) return;
    log(`capture process gone (${reason})`);
    this.rpc.rejectAll(new Error(`capture process gone (${reason})`));
    if (this.status === 'stopping') return; // finish() is running and will report the failed stop
    if (this.status === 'starting') { this.fail(`capture process crashed (${reason})`); return; }
    this.finish({ error: `capture process crashed (${reason}); the Take holds what was written up to the last second` });
  }

  requestStop(reason) {
    if (this.status === 'starting') {
      log(`stop requested before recording started (${reason}): cancelling`);
      this.fail(`cancelled before recording started (${reason})`);
      return;
    }
    if (!['recording', 'paused'].includes(this.status)) return;
    log(`stopping (${reason})`);
    this.finish({});
  }

  async finish({ error = null }) {
    if (['stopping', 'done', 'error'].includes(this.status) && !error) return;
    const wasPaused = this.clock.paused;
    this.setState('stopping');
    for (const t of this.timers) clearInterval(t);
    this.timers = [];
    try { globalShortcut.unregisterAll(); } catch { /* ignore */ }
    try { this.input.stop(); } catch { /* ignore */ }

    let stopAt = now();
    if (!error) {
      try {
        stopAt = (await this.rpc.call('stop', {}, 30000)).at;
      } catch (e) {
        error = `finalizing recorders failed: ${e.message}`;
      }
    }
    for (const [k, fd] of Object.entries(this.files)) { try { fs.closeSync(fd); } catch { /* ignore */ } delete this.files[k]; }

    const duration = wasPaused ? this.clock.pauses[this.clock.pauses.length - 1] : this.clock.elapsed(stopAt);
    const st = this.started;
    const streams = { screen: { start_offset: st.offsets.screen || 0 } };
    if (st.camera && fs.existsSync(this.paths.camera)) streams.camera = { start_offset: st.offsets.camera || 0, label: st.camera.label };
    if (st.mic && fs.existsSync(this.paths.mic)) streams.mic = { start_offset: st.offsets.mic || 0, label: st.mic.label };
    const d = this.display;
    const scale = d && Math.abs(st.screen.width / st.screen.height - d.bounds.width / d.bounds.height) < 0.02
      ? Math.round((st.screen.width / d.bounds.width) * 1000) / 1000
      : (d ? d.scaleFactor : 1);
    try {
      const manifest = writeTake(this.paths, {
        startedAt: st.t0,
        duration,
        display: { width: st.screen.width, height: st.screen.height, scale },
        streams,
        input: { source: this.input.source, warning: this.input.warning },
        overlayRect: process.platform === 'linux' ? this.overlay : null,
        pauses: this.clock.pauses,
      });
      log(`take.json written: ${manifest.duration}s, ${this.events ? this.events.count : 0} events`);
    } catch (e) {
      error = error || `writing take.json failed: ${e.message}`;
    }
    if (this.events) this.events.close();
    try { fs.unlinkSync(this.paths.stop); } catch { /* not stopped by file */ }
    if (this.bar && !this.bar.isDestroyed()) this.bar.destroy();
    if (error) {
      console.error(`clipagent-recorder: error: ${error}`);
      this.setState('error', { error, elapsed: duration });
      app.exit(EXIT.ERROR);
      return;
    }
    this.setState('done', { elapsed: duration });
    log('done');
    app.exit(EXIT.OK);
  }
}

// ------------------------------------------------------------------ Linux Wayland: run under XWayland

/**
 * On Wayland we run the windows under XWayland (--ozone-platform=x11): native Wayland lets neither
 * always-on-top nor window placement work, and the bar's position must be known for overlay_rect.
 * Screen capture still goes through the PipeWire portal. The switch must be on the real command line,
 * so a packaged binary re-executes itself once. bin/clipagent-recorder passes it directly.
 */
function needsX11Respawn() {
  return process.platform === 'linux' && isWayland()
    && !process.argv.some((a) => a.startsWith('--ozone-platform=')) // Electron itself sets the switch to "wayland"
    && !process.env.CLIPAGENT_NATIVE_WAYLAND && !process.env.CLIPAGENT_RESPAWNED;
}

function respawn() {
  const args = [...process.argv.slice(1)];
  const at = args.indexOf('--');
  const flag = '--ozone-platform=x11';
  if (at >= 0) args.splice(at, 0, flag); else args.unshift(flag);
  const child = spawn(process.execPath, args, {
    stdio: 'inherit',
    env: { ...process.env, CLIPAGENT_RESPAWNED: '1' },
  });
  let exited = false;
  const forward = ['SIGINT', 'SIGTERM', 'SIGHUP', 'SIGUSR1', 'SIGUSR2'];
  for (const sig of forward) process.on(sig, () => { if (!exited) child.kill(sig); });
  // Electron turns SIGTERM/SIGINT into app.quit(): hold the quit until the child has finalized the Take.
  app.on('will-quit', (e) => { if (!exited) { e.preventDefault(); child.kill('SIGTERM'); } });
  child.on('exit', (code, signal) => {
    exited = true;
    app.exit(code === null ? (signal ? EXIT.ERROR : EXIT.OK) : code);
  });
}

// ------------------------------------------------------------------ entry

function main() {
  if (opts.mode === 'help') { console.log(USAGE); process.exit(EXIT.OK); }
  if (opts.mode === 'version') { console.log(`clipagent-recorder ${APP_VERSION}`); process.exit(EXIT.OK); }
  if (opts.mode === 'stop') {
    requestStop(opts.session, { wait: opts.wait, timeout: opts.timeout }).then((r) => {
      (r.code ? console.error : console.log)(`clipagent-recorder: ${r.message}`);
      process.exit(r.code);
    });
    return;
  }
  if (needsX11Respawn()) { respawn(); return; }

  if (process.platform === 'linux') app.commandLine.appendSwitch('enable-features', 'WebRTCPipeWireCapturer');
  app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
  if (process.platform === 'darwin' && app.dock) app.dock.hide();
  app.on('window-all-closed', () => { /* keep running: the capture window is hidden, the bar may close */ });

  app.whenReady().then(() => {
    if (opts.mode === 'list-devices') return listDevices();
    const rec = new Recorder({ ...opts });
    return rec.start().catch((e) => rec.fail(e.stack || e.message));
  }).catch((e) => {
    console.error(`clipagent-recorder: error: ${e.stack || e.message}`);
    app.exit(EXIT.ERROR);
  });
}

main();
