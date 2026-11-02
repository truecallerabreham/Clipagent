'use strict';
// Recorded-time clock (pure). Maps wall-clock timestamps (epoch ms, high resolution)
// to seconds of recorded time since take t=0, with pauses excluded.

class RecordingClock {
  constructor() {
    this.t0 = null; // epoch ms of take t=0
    this.segments = []; // [{ start: epochMs, end: epochMs|null, base: recordedSecondsAtStart }]
    this.pauses = []; // recorded-time positions where a pause happened
  }

  get started() { return this.t0 !== null; }
  get paused() { return this.started && this.segments[this.segments.length - 1].end !== null; }

  start(epochMs) {
    if (this.started) throw new Error('clock already started');
    this.t0 = epochMs;
    this.segments.push({ start: epochMs, end: null, base: 0 });
  }

  /** Pause at epochMs. Returns the recorded-time position of the pause. */
  pause(epochMs) {
    if (!this.started || this.paused) return null;
    const seg = this.segments[this.segments.length - 1];
    seg.end = Math.max(epochMs, seg.start);
    const at = seg.base + (seg.end - seg.start) / 1000;
    this.pauses.push(at);
    return at;
  }

  /** Resume at epochMs. Returns the recorded-time position (same as the pause position). */
  resume(epochMs) {
    if (!this.paused) return null;
    const last = this.segments[this.segments.length - 1];
    const base = last.base + (last.end - last.start) / 1000;
    this.segments.push({ start: Math.max(epochMs, last.end), end: null, base });
    return base;
  }

  /**
   * Recorded seconds for a wall-clock timestamp.
   * Returns { t, paused } where paused=true means the timestamp falls inside a pause
   * (t is then the pause position), or null when before t=0.
   */
  at(epochMs) {
    if (!this.started || epochMs < this.t0) return null;
    for (let i = this.segments.length - 1; i >= 0; i--) {
      const s = this.segments[i];
      if (epochMs >= s.start) {
        if (s.end === null || epochMs <= s.end) return { t: s.base + (epochMs - s.start) / 1000, paused: false };
        return { t: s.base + (s.end - s.start) / 1000, paused: true };
      }
    }
    return null;
  }

  /** Total recorded seconds up to epochMs (pauses excluded). */
  elapsed(epochMs) {
    const r = this.at(epochMs);
    return r ? r.t : 0;
  }
}

/** Round seconds to milliseconds precision. */
function round3(x) { return Math.round(x * 1000) / 1000; }

module.exports = { RecordingClock, round3 };
