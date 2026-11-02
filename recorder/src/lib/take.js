'use strict';
// Take files: paths, atomic JSON writes, state.json, take.json manifest (Contract 1 in docs/design.md).

const fs = require('fs');
const path = require('path');
const { round3 } = require('./clock');

const APP_VERSION = require('../../package.json').version;
const STATUSES = ['starting', 'recording', 'paused', 'stopping', 'done', 'error'];

function takePaths(sessionDir) {
  const dir = path.join(path.resolve(sessionDir), 'take');
  return {
    dir,
    screen: path.join(dir, 'screen.webm'),
    camera: path.join(dir, 'camera.webm'),
    mic: path.join(dir, 'mic.webm'),
    events: path.join(dir, 'events.jsonl'),
    state: path.join(dir, 'state.json'),
    take: path.join(dir, 'take.json'),
    stop: path.join(dir, 'stop'),
  };
}

/** Write JSON via temp file + rename so readers never see a half-written file. */
function writeJsonAtomic(file, obj) {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n');
  try {
    fs.renameSync(tmp, file);
  } catch (e) {
    // Windows can refuse to rename over a file another process has open; fall back to a direct write.
    fs.writeFileSync(file, JSON.stringify(obj, null, 2) + '\n');
    try { fs.unlinkSync(tmp); } catch { /* ignore */ }
  }
}

function buildState(status, { error = null, elapsed = 0 } = {}) {
  if (!STATUSES.includes(status)) throw new Error(`invalid status ${status}`);
  return { status, error: error ? String(error) : null, elapsed: round3(Math.max(0, elapsed)) };
}

function writeState(paths, status, extra) {
  writeJsonAtomic(paths.state, buildState(status, extra));
}

/**
 * Build the take.json manifest. Streams that were not recorded are omitted.
 * @param {object} o
 * @param {string|Date|number} o.startedAt   wall-clock time of take t=0
 * @param {number} o.duration                recorded seconds, pauses excluded
 * @param {{width,height,scale}} o.display   physical px of the captured display
 * @param {{screen:{start_offset}, camera?:{start_offset,label}|null, mic?:{start_offset,label}|null}} o.streams
 * @param {{source:'uiohook'|'evdev'|'none', warning:string|null}} o.input
 * @param {number[]|null} o.overlayRect      [x,y,w,h] 0-1 of the display, or null
 * @param {number[]} o.pauses                recorded-time positions of pauses
 */
function buildTake(o) {
  const streams = {};
  const s = o.streams || {};
  if (!s.screen) throw new Error('take has no screen stream');
  streams.screen = { file: 'screen.webm', start_offset: round3(s.screen.start_offset || 0) };
  if (s.camera) streams.camera = { file: 'camera.webm', start_offset: round3(s.camera.start_offset || 0), label: s.camera.label || '' };
  if (s.mic) streams.mic = { file: 'mic.webm', start_offset: round3(s.mic.start_offset || 0), label: s.mic.label || '' };
  const d = o.display || {};
  const rect = o.overlayRect && o.overlayRect.length === 4 ? o.overlayRect.map((v) => Math.round(v * 10000) / 10000) : null;
  return {
    version: 1,
    app: `clipagent-recorder ${o.appVersion || APP_VERSION}`,
    platform: o.platform || process.platform,
    started_at: new Date(o.startedAt).toISOString(),
    duration: round3(Math.max(0, o.duration || 0)),
    display: { width: Math.round(d.width || 0), height: Math.round(d.height || 0), scale: Number(d.scale || 1) },
    streams,
    input: { source: (o.input && o.input.source) || 'none', warning: (o.input && o.input.warning) || null },
    overlay_rect: rect,
    pauses: (o.pauses || []).map((t) => [round3(t), round3(t)]),
  };
}

function writeTake(paths, o) {
  const manifest = buildTake(o);
  writeJsonAtomic(paths.take, manifest);
  return manifest;
}

/** Append-only events.jsonl writer (sync appends: a crash loses at most the current line). */
class EventsWriter {
  constructor(file) {
    this.fd = fs.openSync(file, 'a');
    this.count = 0;
  }

  write(ev) {
    if (this.fd === null) return;
    fs.writeSync(this.fd, JSON.stringify(ev) + '\n');
    this.count++;
  }

  close() {
    if (this.fd !== null) { fs.closeSync(this.fd); this.fd = null; }
  }
}

/** Throws if <take> already holds a finished or in-progress Take (the Take is never modified). */
function assertFreshTake(paths) {
  for (const f of [paths.take, paths.screen]) {
    if (fs.existsSync(f)) throw new Error(`a Take already exists in ${paths.dir} (${path.basename(f)} present); use a new session directory`);
  }
}

module.exports = { takePaths, writeJsonAtomic, buildState, writeState, buildTake, writeTake, EventsWriter, assertFreshTake, APP_VERSION, STATUSES };
