'use strict';
// Hidden capture window: acquires screen / camera / mic, runs one MediaRecorder per stream and
// streams 1-second chunks to the main process (which appends them to screen.webm, camera.webm, mic.webm).
// Driven by RPC from the main process: enumerate, start, pause, resume, stop.

/* global MediaRecorder */
const R = window.recorder;
const nowEpoch = () => performance.timeOrigin + performance.now();

const S = { streams: {}, recs: {}, queues: {}, audio: null, levelTimer: null };

class CaptureError extends Error {
  constructor(kind, message) { super(message); this.name = 'CaptureError'; this.kind = kind; }
}

function describe(err, what) {
  const name = err && err.name;
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return `${what}: permission denied${what === 'screen capture' ? ' or the screen-share dialog was cancelled' : ''}`;
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return `${what}: device not found`;
  if (name === 'NotReadableError' || name === 'AbortError') return `${what}: device is busy or could not be started (${err.message})`;
  return `${what}: ${name || 'Error'}: ${(err && err.message) || err}`;
}

function pickMime(candidates) {
  return candidates.find((m) => MediaRecorder.isTypeSupported(m)) || '';
}

async function enumerate() {
  const devs = await navigator.mediaDevices.enumerateDevices();
  const pick = (kind) => devs.filter((d) => d.kind === kind && d.deviceId)
    .map((d) => ({ deviceId: d.deviceId, label: d.label, groupId: d.groupId }));
  return { cameras: pick('videoinput'), mics: pick('audioinput') };
}

async function enumerateWithLabels() {
  let d = await enumerate();
  const unlabeled = [...d.cameras, ...d.mics].some((x) => !x.label);
  if (unlabeled && (d.cameras.length || d.mics.length)) {
    // Labels are only exposed after a capture permission grant: open devices briefly, then re-enumerate.
    for (const c of [{ video: true }, { audio: true }]) {
      if ((c.video && !d.cameras.length) || (c.audio && !d.mics.length)) continue;
      try { (await navigator.mediaDevices.getUserMedia(c)).getTracks().forEach((t) => t.stop()); } catch { /* keep ids */ }
    }
    d = await enumerate();
  }
  return d;
}

function stopTracks() {
  for (const s of Object.values(S.streams)) s.getTracks().forEach((t) => t.stop());
}

/** Test pattern instead of the real screen (CLIPAGENT_FAKE_SCREEN=1): exercises the pipeline without a portal. */
function fakeScreen(cfg) {
  const c = document.createElement('canvas');
  c.width = Math.min(cfg.width || 1280, 1920);
  c.height = Math.round(c.width * ((cfg.height || 720) / (cfg.width || 1280)));
  const g = c.getContext('2d');
  const t0 = performance.now();
  setInterval(() => {
    const t = (performance.now() - t0) / 1000;
    g.fillStyle = '#111827';
    g.fillRect(0, 0, c.width, c.height);
    g.fillStyle = '#38bdf8';
    g.fillRect((t * 200) % c.width, c.height / 2 - 40, 80, 80);
    g.fillStyle = '#fff';
    g.font = '48px sans-serif';
    g.fillText(`fake screen ${t.toFixed(2)}s`, 40, 80);
  }, 33);
  return c.captureStream(30);
}

async function acquire(cfg) {
  const notes = [];
  try {
    S.streams.screen = cfg.fakeScreen ? fakeScreen(cfg) : await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 30, max: 30 }, width: { ideal: cfg.width || 1920 }, height: { ideal: cfg.height || 1080 } },
      audio: false,
    });
  } catch (e) {
    throw new CaptureError('screen', describe(e, 'screen capture'));
  }
  const vt = S.streams.screen.getVideoTracks()[0];
  if (!vt) throw new CaptureError('screen', 'screen capture returned no video track');
  vt.addEventListener('ended', () => R.notify('ended', { stream: 'screen' }));

  if (cfg.camera !== 'none') {
    const { cameras } = await enumerate();
    if (!cameras.length) {
      if (cfg.camera === null) notes.push('no camera found: recording without camera');
      else throw new CaptureError('camera', 'camera: no camera found (pass --camera none to record without one)');
    } else {
      const video = { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } };
      if (cfg.camera && cfg.camera !== 'default') video.deviceId = { exact: cfg.camera };
      try {
        S.streams.camera = await navigator.mediaDevices.getUserMedia({ video, audio: false });
      } catch (e) {
        if (cfg.camera === null) notes.push(`${describe(e, 'camera')}: recording without camera`);
        else throw new CaptureError('camera', describe(e, 'camera') + (video.deviceId ? ` (deviceId ${cfg.camera}; see --list-devices)` : ''));
      }
    }
  }

  if (cfg.mic) {
    try {
      S.streams.mic = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: { ideal: 1 } },
        video: false,
      });
    } catch (e) {
      throw new CaptureError('mic', describe(e, 'microphone') + ' (pass --no-mic to record without it)');
    }
  }
  return notes;
}

function makeRecorder(name, stream, options) {
  const rec = new MediaRecorder(stream, options);
  S.queues[name] = Promise.resolve();
  rec.ondataavailable = (e) => {
    if (!e.data || !e.data.size) return;
    const blob = e.data;
    S.queues[name] = S.queues[name]
      .then(async () => R.chunk(name, new Uint8Array(await blob.arrayBuffer())))
      .catch((err) => R.notify('error', { message: `writing ${name}.webm failed: ${err.message}` }));
  };
  rec.onerror = (e) => R.notify('error', { message: `${name} recorder error: ${(e.error && e.error.message) || 'unknown'}` });
  const started = new Promise((resolve) => {
    rec.addEventListener('start', (e) => {
      const ts = e.timeStamp > 0 ? performance.timeOrigin + e.timeStamp : nowEpoch();
      resolve(Math.min(ts, nowEpoch()));
    }, { once: true });
  });
  S.recs[name] = rec;
  return started;
}

function startLevelMeter() {
  if (!S.streams.mic) return;
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(S.streams.mic);
  const an = ctx.createAnalyser();
  an.fftSize = 1024;
  src.connect(an);
  const buf = new Float32Array(an.fftSize);
  S.audio = ctx;
  S.levelTimer = setInterval(() => {
    an.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const db = 20 * Math.log10(Math.sqrt(sum / buf.length) + 1e-9);
    R.level(Math.max(0, Math.min(1, (db + 60) / 60)));
  }, 80);
}

async function start(cfg) {
  const notes = await acquire(cfg).catch((e) => { stopTracks(); throw e; });
  const vcodec = cfg.screenCodec || 'vp9';
  const vmimes = [`video/webm;codecs=${vcodec}`, 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  const starts = {};
  const pending = [];
  const plan = [['screen', { mimeType: pickMime(vmimes), videoBitsPerSecond: cfg.screenBitrate || 8_000_000 }]];
  if (S.streams.camera) plan.push(['camera', { mimeType: pickMime(vmimes), videoBitsPerSecond: 5_000_000 }]);
  if (S.streams.mic) plan.push(['mic', { mimeType: pickMime(['audio/webm;codecs=opus', 'audio/webm']), audioBitsPerSecond: 160_000 }]);
  for (const [name, options] of plan) pending.push(makeRecorder(name, S.streams[name], options).then((t) => { starts[name] = t; }));
  for (const [name] of plan) S.recs[name].start(1000); // 1 s chunks: a crash loses at most ~1 s
  await Promise.race([
    Promise.all(pending),
    new Promise((_, rej) => setTimeout(() => rej(new CaptureError('start', 'MediaRecorder did not start within 10 s')), 10000)),
  ]);
  const t0 = Math.min(...Object.values(starts));
  const offsets = {};
  for (const [k, v] of Object.entries(starts)) offsets[k] = (v - t0) / 1000;
  startLevelMeter();
  const vs = S.streams.screen.getVideoTracks()[0];
  const set = vs.getSettings();
  const info = (name) => {
    const s = S.streams[name];
    if (!s) return null;
    const t = s.getTracks()[0];
    return { label: t.label, settings: t.getSettings(), mimeType: S.recs[name].mimeType };
  };
  return {
    t0,
    offsets,
    notes,
    screen: { width: set.width, height: set.height, label: vs.label, displaySurface: set.displaySurface || null, mimeType: S.recs.screen.mimeType },
    camera: info('camera'),
    mic: info('mic'),
  };
}

function pause() {
  const at = nowEpoch();
  for (const r of Object.values(S.recs)) if (r.state === 'recording') r.pause();
  return { at };
}

function resume() {
  const at = nowEpoch();
  for (const r of Object.values(S.recs)) if (r.state === 'paused') r.resume();
  return { at };
}

async function stop() {
  const at = nowEpoch();
  await Promise.all(Object.values(S.recs).map((r) => new Promise((resolve) => {
    if (r.state === 'inactive') { resolve(); return; }
    r.addEventListener('stop', () => resolve(), { once: true });
    r.stop();
  })));
  await Promise.all(Object.values(S.queues));
  clearInterval(S.levelTimer);
  stopTracks();
  if (S.audio) S.audio.close().catch(() => {});
  return { at };
}

R.onRpc(async (method, args) => {
  switch (method) {
    case 'enumerate': return enumerateWithLabels();
    case 'start': return start(args || {});
    case 'pause': return pause();
    case 'resume': return resume();
    case 'stop': return stop();
    case 'ping': return 'pong';
    default: throw new Error(`unknown method ${method}`);
  }
});
