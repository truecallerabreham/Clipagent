'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { RecordingClock } = require('../src/lib/clock');
const { EventNormalizer, normalizePoint } = require('../src/lib/events');

const T = 1_700_000_000_000;
function setup(platform = 'linux') {
  const clock = new RecordingClock();
  clock.start(T);
  const out = [];
  const n = new EventNormalizer({ clock, sink: (e) => out.push(e), rect: { x: 0, y: 0, width: 2000, height: 1000 }, platform });
  return { clock, out, n };
}
const NOMODS = { ctrl: false, alt: false, shift: false, meta: false };

test('plain typing never stores the character', () => {
  const { out, n } = setup();
  n.input({ kind: 'key', name: 'H', mods: NOMODS, ts: T + 100 });
  n.input({ kind: 'key', name: 'Space', mods: NOMODS, ts: T + 200 });
  n.input({ kind: 'key', name: 'A', mods: { ...NOMODS, shift: true }, ts: T + 300 }); // capital A
  n.input({ kind: 'key', name: 'Slash', mods: { ...NOMODS, shift: true }, ts: T + 400 }); // '?'
  n.input({ kind: 'key', name: null, mods: NOMODS, ts: T + 500 }); // unknown key
  assert.deepEqual(out, [
    { t: 0.1, type: 'typing' }, { t: 0.2, type: 'typing' }, { t: 0.3, type: 'typing' },
    { t: 0.4, type: 'typing' }, { t: 0.5, type: 'typing' },
  ]);
  for (const e of out) assert.deepEqual(Object.keys(e).sort(), ['t', 'type']);
});

test('shortcuts with a modifier, and special keys alone', () => {
  const { out, n } = setup();
  n.input({ kind: 'key', name: 'P', mods: { ...NOMODS, ctrl: true, shift: true }, ts: T + 7800 });
  n.input({ kind: 'key', name: 'F5', mods: NOMODS, ts: T + 8000 });
  n.input({ kind: 'key', name: 'Escape', mods: NOMODS, ts: T + 8100 });
  n.input({ kind: 'key', name: 'Enter', mods: NOMODS, ts: T + 8200 });
  n.input({ kind: 'key', name: 'Tab', mods: { ...NOMODS, shift: true }, ts: T + 8300 });
  n.input({ kind: 'key', name: 'Slash', mods: { ...NOMODS, ctrl: true }, ts: T + 8400 });
  assert.deepEqual(out, [
    { t: 7.8, type: 'shortcut', keys: ['Ctrl', 'Shift', 'P'] },
    { t: 8, type: 'shortcut', keys: ['F5'] },
    { t: 8.1, type: 'shortcut', keys: ['Esc'] },
    { t: 8.2, type: 'shortcut', keys: ['Enter'] },
    { t: 8.3, type: 'shortcut', keys: ['Shift', 'Tab'] },
    { t: 8.4, type: 'shortcut', keys: ['Ctrl', '/'] },
  ]);
});

test('bare modifier presses are not recorded; macOS labels', () => {
  const { out, n } = setup('darwin');
  n.input({ kind: 'key', name: 'Meta', mods: NOMODS, ts: T + 10 });
  n.input({ kind: 'key', name: 'ShiftRight', mods: NOMODS, ts: T + 20 });
  n.input({ kind: 'key', name: 'K', mods: { ...NOMODS, meta: true, alt: true }, ts: T + 30 });
  assert.deepEqual(out, [{ t: 0.03, type: 'shortcut', keys: ['Option', 'Cmd', 'K'] }]);
});

test('clicks, scrolls and moves are normalized to the display', () => {
  const { out, n } = setup();
  n.input({ kind: 'down', button: 'left', x: 820, y: 620, ts: T + 3210 });
  n.input({ kind: 'wheel', dy: -3, x: 1000, y: 500, ts: T + 5020 });
  n.input({ kind: 'down', button: 'right', x: 2500, y: 10, ts: T + 5100 }); // other display: dropped
  assert.deepEqual(out, [
    { t: 3.21, type: 'click', x: 0.41, y: 0.62, button: 'left' },
    { t: 5.02, type: 'scroll', x: 0.5, y: 0.5, dy: -3 },
  ]);
});

test('moves are sampled at <= 20 Hz and deduplicated', () => {
  const { out, n } = setup();
  for (let i = 0; i < 100; i++) n.input({ kind: 'move', x: 10 * i, y: 100, ts: T + 1000 + i * 5 }); // 200 Hz for 0.5 s
  n.input({ kind: 'move', x: 990, y: 100, ts: T + 2000 });
  n.input({ kind: 'move', x: 990, y: 100, ts: T + 2100 }); // same spot
  assert.ok(out.length <= 12, `got ${out.length} moves`);
  for (let i = 1; i < out.length; i++) assert.ok(out[i].t - out[i - 1].t >= 0.05 - 1e-9);
  assert.ok(out.every((e) => e.type === 'move' && e.x >= 0 && e.x <= 1));
});

test('evdev-style input without absolute position: clicks with null x/y, no moves', () => {
  const { out, n } = setup();
  n.input({ kind: 'down', button: 'left', x: null, y: null, ts: T + 1000 });
  n.input({ kind: 'wheel', dy: 1, x: null, y: null, ts: T + 1100 });
  n.input({ kind: 'move', x: null, y: null, ts: T + 1200 });
  assert.deepEqual(out, [
    { t: 1, type: 'click', x: null, y: null, button: 'left' },
    { t: 1.1, type: 'scroll', x: null, y: null, dy: 1 },
  ]);
});

test('events during a pause or before t=0 are dropped; markers land at the pause position', () => {
  const { clock, out, n } = setup();
  n.input({ kind: 'key', name: 'A', mods: NOMODS, ts: T - 50 });
  const at = clock.pause(T + 2000);
  n.control('pause', at);
  n.input({ kind: 'key', name: 'A', mods: NOMODS, ts: T + 2500 });
  n.marker(T + 2600);
  clock.resume(T + 4000);
  n.control('resume', at);
  n.input({ kind: 'key', name: 'A', mods: NOMODS, ts: T + 4500 });
  assert.deepEqual(out, [
    { t: 2, type: 'pause' },
    { t: 2, type: 'marker', kind: 'scratch' },
    { t: 2, type: 'resume' },
    { t: 2.5, type: 'typing' },
  ]);
});

test('normalizePoint', () => {
  assert.deepEqual(normalizePoint(150, 50, { x: 100, y: 0, width: 100, height: 100 }), { x: 0.5, y: 0.5 });
  assert.equal(normalizePoint(50, 50, { x: 100, y: 0, width: 100, height: 100 }), null);
  assert.deepEqual(normalizePoint(null, null, { x: 0, y: 0, width: 1, height: 1 }), { x: null, y: null });
});
