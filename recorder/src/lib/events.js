'use strict';
// Input-event normalizer + privacy filter (pure apart from the injected sink).
//
// Sources (uiohook, evdev) feed "raw" input:
//   {kind:'key',   name, mods:{ctrl,alt,shift,meta}, ts}
//   {kind:'down',  button:'left'|'right'|'middle'|..., x, y, ts}   x/y: absolute input-space px, or null
//   {kind:'move',  x, y, ts}
//   {kind:'wheel', dy, x, y, ts}                                   dy < 0 = scroll up
// ts is epoch ms. The normalizer turns them into Contract-1 events.jsonl objects.

const { classifyKey } = require('./keys');
const { round3 } = require('./clock');

const MOVE_INTERVAL = 0.05; // seconds: moves sampled at <= 20 Hz

function round4(x) { return Math.round(x * 10000) / 10000; }

/**
 * Normalize an absolute point to 0-1 of rect {x, y, width, height} (same coordinate space as the input).
 * Returns {x, y} rounded, {x:null, y:null} when the source has no absolute position, or null when outside.
 */
function normalizePoint(x, y, rect) {
  if (x === null || x === undefined || y === null || y === undefined || !rect) return { x: null, y: null };
  const nx = (x - rect.x) / rect.width;
  const ny = (y - rect.y) / rect.height;
  if (!(nx >= 0 && nx <= 1 && ny >= 0 && ny <= 1)) return null;
  return { x: round4(nx), y: round4(ny) };
}

class EventNormalizer {
  /**
   * @param {object} o
   * @param {import('./clock').RecordingClock} o.clock
   * @param {(ev:object)=>void} o.sink  receives finished events
   * @param {{x,y,width,height}|null} [o.rect]  captured display in input coordinates
   * @param {string} [o.platform]
   */
  constructor({ clock, sink, rect = null, platform = process.platform }) {
    this.clock = clock;
    this.sink = sink;
    this.rect = rect;
    this.platform = platform;
    this.lastMoveT = -Infinity;
    this.lastMove = null;
  }

  setRect(rect) { this.rect = rect; }

  _time(ts) {
    const r = this.clock.at(ts);
    if (!r || r.paused) return null; // before t=0 or during a pause: not part of the recorded video
    return round3(r.t);
  }

  input(raw) {
    const t = this._time(raw.ts);
    if (t === null) return null;
    let ev = null;
    switch (raw.kind) {
      case 'key': {
        const c = classifyKey(raw.name, raw.mods || {}, this.platform);
        if (!c) return null;
        ev = c.type === 'typing' ? { t, type: 'typing' } : { t, type: 'shortcut', keys: c.keys };
        break;
      }
      case 'down': {
        const p = normalizePoint(raw.x, raw.y, this.rect);
        if (!p) return null; // click on another display
        ev = { t, type: 'click', x: p.x, y: p.y, button: raw.button || 'left' };
        break;
      }
      case 'move': {
        const p = normalizePoint(raw.x, raw.y, this.rect);
        if (!p || p.x === null) return null;
        if (t - this.lastMoveT < MOVE_INTERVAL) return null;
        if (this.lastMove && this.lastMove.x === p.x && this.lastMove.y === p.y) return null;
        this.lastMoveT = t;
        this.lastMove = p;
        ev = { t, type: 'move', x: p.x, y: p.y };
        break;
      }
      case 'wheel': {
        if (!raw.dy) return null;
        const p = normalizePoint(raw.x, raw.y, this.rect);
        if (!p) return null;
        ev = { t, type: 'scroll', x: p.x, y: p.y, dy: raw.dy };
        break;
      }
      default:
        return null;
    }
    this.sink(ev);
    return ev;
  }

  /** Scratch Marker. Allowed during a pause (placed at the pause position). */
  marker(ts, kind = 'scratch') {
    const r = this.clock.at(ts);
    if (!r) return null;
    const ev = { t: round3(r.t), type: 'marker', kind };
    this.sink(ev);
    return ev;
  }

  /** pause/resume events at a recorded-time position. */
  control(type, t) {
    const ev = { t: round3(t), type };
    this.sink(ev);
    return ev;
  }
}

module.exports = { EventNormalizer, normalizePoint, MOVE_INTERVAL };
