'use strict';
// Linux evdev support (pure parts): struct input_event parsing, /proc/bus/input/devices
// parsing + device classification, and translation of kernel events into raw input.

const { EVDEV_KEYS, EVDEV_BUTTONS, modifierOf } = require('./keys');

const EV_SYN = 0x00, EV_KEY = 0x01, EV_REL = 0x02, EV_ABS = 0x03, EV_REP = 0x14;
const REL_WHEEL = 0x08;
const KEY_A = 30, KEY_Z = 44, KEY_SPACE = 57, BTN_LEFT = 0x110;

/** sizeof(struct input_event): timeval (2 longs) + u16 type + u16 code + s32 value. */
function eventSize(arch = process.arch) {
  return ['x64', 'arm64', 'ppc64', 's390x', 'riscv64', 'loong64', 'mips64el'].includes(arch) ? 24 : 16;
}

/**
 * Streaming parser for /dev/input/event* reads. Handles reads that split an event.
 * push(buf) returns [{sec, usec, type, code, value, ts}] with ts in epoch ms (CLOCK_REALTIME, the default).
 */
class InputEventParser {
  constructor(size = eventSize()) {
    this.size = size;
    this.rest = Buffer.alloc(0);
  }

  push(chunk) {
    const buf = this.rest.length ? Buffer.concat([this.rest, chunk]) : chunk;
    const n = Math.floor(buf.length / this.size);
    const out = new Array(n);
    for (let i = 0; i < n; i++) out[i] = parseInputEvent(buf, i * this.size, this.size);
    this.rest = Buffer.from(buf.subarray(n * this.size));
    return out;
  }
}

function parseInputEvent(buf, off = 0, size = 24) {
  let sec, usec, p;
  if (size === 24) {
    sec = Number(buf.readBigInt64LE(off));
    usec = Number(buf.readBigInt64LE(off + 8));
    p = off + 16;
  } else {
    sec = buf.readInt32LE(off);
    usec = buf.readInt32LE(off + 4);
    p = off + 8;
  }
  const type = buf.readUInt16LE(p);
  const code = buf.readUInt16LE(p + 2);
  const value = buf.readInt32LE(p + 4);
  return { sec, usec, type, code, value, ts: sec * 1000 + usec / 1000 };
}

/** Build a struct input_event (for tests and tooling). */
function encodeInputEvent({ sec, usec, type, code, value }, size = 24) {
  const b = Buffer.alloc(size);
  let p;
  if (size === 24) { b.writeBigInt64LE(BigInt(sec), 0); b.writeBigInt64LE(BigInt(usec), 8); p = 16; }
  else { b.writeInt32LE(sec, 0); b.writeInt32LE(usec, 4); p = 8; }
  b.writeUInt16LE(type, p); b.writeUInt16LE(code, p + 2); b.writeInt32LE(value, p + 4);
  return b;
}

/** Parse a "B: KEY=..." style bitmap (space-separated hex longs, most significant first) into a BigInt. */
function parseBitmap(str, wordBits = 64) {
  const words = String(str || '').trim().split(/\s+/).filter(Boolean);
  let v = 0n;
  for (const w of words) v = (v << BigInt(wordBits)) | BigInt('0x' + w);
  return v;
}

function hasBit(bitmap, bit) { return ((bitmap >> BigInt(bit)) & 1n) === 1n; }

/** Parse /proc/bus/input/devices into [{name, handlers:[], event:'event4'|null, bits:{EV,KEY,REL,ABS}}]. */
function parseProcDevices(text, wordBits = 64) {
  const devices = [];
  for (const block of String(text).split(/\n\s*\n/)) {
    if (!block.trim()) continue;
    const dev = { name: '', handlers: [], event: null, bits: {} };
    for (const line of block.split('\n')) {
      const m = /^([A-Z]): (.*)$/.exec(line.trim());
      if (!m) continue;
      const [, k, rest] = m;
      if (k === 'N') dev.name = (/Name="(.*)"/.exec(rest) || [, rest])[1];
      else if (k === 'H') {
        dev.handlers = rest.replace(/^Handlers=/, '').trim().split(/\s+/).filter(Boolean);
        dev.event = dev.handlers.find((h) => /^event\d+$/.test(h)) || null;
      } else if (k === 'B') {
        const b = /^(\w+)=(.*)$/.exec(rest);
        if (b) dev.bits[b[1]] = parseBitmap(b[2], wordBits);
      }
    }
    devices.push(dev);
  }
  return devices;
}

/** 'keyboard' | 'mouse' | null */
function classifyDevice(dev) {
  const ev = dev.bits.EV || 0n;
  const key = dev.bits.KEY || 0n;
  if (!dev.event || !hasBit(ev, EV_KEY)) return null;
  if (hasBit(key, KEY_A) && hasBit(key, KEY_Z) && hasBit(key, KEY_SPACE)) return 'keyboard';
  if (hasBit(key, BTN_LEFT) && (hasBit(ev, EV_REL) || hasBit(ev, EV_ABS))) return 'mouse';
  return null;
}

/**
 * Translates kernel events (from all keyboards and mice) into raw input for the EventNormalizer.
 * Keeps modifier state across devices. Mice give relative motion only, so clicks/scrolls carry x/y null
 * and no moves are produced (the engine estimates pointer position from the video).
 */
class EvdevTranslator {
  constructor() { this.down = new Set(); }

  mods() {
    const m = { ctrl: false, alt: false, shift: false, meta: false };
    for (const code of this.down) {
      const mod = modifierOf(EVDEV_KEYS[code]);
      if (mod) m[mod] = true;
    }
    return m;
  }

  /** Returns a raw input object or null. */
  feed(e) {
    if (e.type === EV_KEY) {
      if (e.value === 0) { this.down.delete(e.code); return null; }
      if (e.value !== 1) return null; // 2 = autorepeat
      if (EVDEV_BUTTONS[e.code]) return { kind: 'down', button: EVDEV_BUTTONS[e.code], x: null, y: null, ts: e.ts };
      const name = EVDEV_KEYS[e.code];
      if (!name) return null; // media keys, touchpad BTN_TOOL_*, etc.
      const mods = this.mods(); // modifiers held before this key
      this.down.add(e.code);
      return { kind: 'key', name, mods, ts: e.ts };
    }
    if (e.type === EV_REL && e.code === REL_WHEEL && e.value !== 0) {
      return { kind: 'wheel', dy: -e.value, x: null, y: null, ts: e.ts };
    }
    return null;
  }
}

module.exports = {
  EV_SYN, EV_KEY, EV_REL, EV_ABS, EV_REP, REL_WHEEL,
  eventSize, InputEventParser, parseInputEvent, encodeInputEvent,
  parseBitmap, hasBit, parseProcDevices, classifyDevice, EvdevTranslator,
};
