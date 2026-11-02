'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {
  InputEventParser, parseInputEvent, encodeInputEvent, eventSize, parseBitmap, hasBit,
  parseProcDevices, classifyDevice, EvdevTranslator, EV_KEY, EV_REL, EV_SYN, REL_WHEEL,
} = require('../src/lib/evdev');

const ev = (type, code, value, ms = 0) => ({ sec: 1_700_000_000, usec: ms * 1000, type, code, value });

test('struct input_event is 24 bytes on 64-bit, 16 on 32-bit', () => {
  assert.equal(eventSize('x64'), 24);
  assert.equal(eventSize('arm64'), 24);
  assert.equal(eventSize('ia32'), 16);
  assert.equal(eventSize('arm'), 16);
});

test('parses a 24-byte event', () => {
  const b = encodeInputEvent({ sec: 1_700_000_123, usec: 456_789, type: EV_KEY, code: 30, value: 1 }, 24);
  assert.equal(b.length, 24);
  const e = parseInputEvent(b, 0, 24);
  assert.equal(e.sec, 1_700_000_123);
  assert.equal(e.usec, 456_789);
  assert.equal(e.type, EV_KEY);
  assert.equal(e.code, 30);
  assert.equal(e.value, 1);
  assert.equal(e.ts, 1_700_000_123_456.789);
});

test('parses negative values (REL_WHEEL down) and 16-byte events', () => {
  const e = parseInputEvent(encodeInputEvent(ev(EV_REL, REL_WHEEL, -1), 16), 0, 16);
  assert.equal(e.value, -1);
  assert.equal(e.code, REL_WHEEL);
});

test('streaming parser handles reads split mid-event', () => {
  const all = Buffer.concat([
    encodeInputEvent(ev(EV_KEY, 30, 1, 1)), encodeInputEvent(ev(EV_SYN, 0, 0, 1)), encodeInputEvent(ev(EV_KEY, 30, 0, 2)),
  ]);
  const p = new InputEventParser(24);
  const out = [...p.push(all.subarray(0, 10)), ...p.push(all.subarray(10, 50)), ...p.push(all.subarray(50))];
  assert.deepEqual(out.map((e) => [e.type, e.code, e.value]), [[EV_KEY, 30, 1], [EV_SYN, 0, 0], [EV_KEY, 30, 0]]);
  assert.equal(p.rest.length, 0);
});

const PROC = `I: Bus=0019 Vendor=0000 Product=0001 Version=0000
N: Name="Power Button"
P: Phys=LNXPWRBN/button/input0
H: Handlers=kbd event3
B: PROP=0
B: EV=3
B: KEY=8000 10000000000000 0

I: Bus=0011 Vendor=0001 Product=0001 Version=ab83
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event4 leds
B: PROP=0
B: EV=120013
B: KEY=6000000000000020 0 0 110500f02100007 ff803078f900d401 feffffdfffcfffff fffffffffffffffe
B: MSC=10
B: LED=7

I: Bus=0003 Vendor=046d Product=c52b Version=0111
N: Name="Logitech USB Receiver Mouse"
H: Handlers=mouse1 event7
B: PROP=0
B: EV=17
B: KEY=ffff0000 0 0 0 0
B: REL=1943
B: MSC=10

I: Bus=0019 Vendor=0000 Product=0005 Version=0000
N: Name="Lid Switch"
H: Handlers=event1
B: PROP=0
B: EV=21
B: SW=1
`;

test('parses /proc/bus/input/devices and classifies keyboards and mice', () => {
  const devs = parseProcDevices(PROC);
  assert.equal(devs.length, 4);
  assert.equal(devs[1].name, 'AT Translated Set 2 keyboard');
  assert.equal(devs[1].event, 'event4');
  assert.deepEqual(devs.map(classifyDevice), [null, 'keyboard', 'mouse', null]);
});

test('bitmap parsing', () => {
  const b = parseBitmap('1 0');
  assert.ok(hasBit(b, 64));
  assert.ok(!hasBit(b, 0));
  assert.ok(hasBit(parseBitmap('ffff0000 0 0 0 0'), 0x110)); // BTN_LEFT
});

test('translator: modifiers, typing, shortcuts, buttons, wheel, autorepeat', () => {
  const tr = new EvdevTranslator();
  const out = [];
  const feed = (type, code, value, ms) => {
    const r = tr.feed({ type, code, value, ts: ms });
    if (r) out.push(r);
  };
  feed(EV_KEY, 29, 1, 1); // LeftCtrl down
  feed(EV_KEY, 56, 1, 2); // LeftAlt down
  feed(EV_KEY, 45, 1, 3); // X
  feed(EV_KEY, 45, 2, 4); // repeat: ignored
  feed(EV_KEY, 45, 0, 5);
  feed(EV_KEY, 56, 0, 6);
  feed(EV_KEY, 29, 0, 7);
  feed(EV_KEY, 30, 1, 8); // a, no mods
  feed(EV_KEY, 0x110, 1, 9); // BTN_LEFT
  feed(EV_KEY, 0x110, 0, 10);
  feed(EV_REL, REL_WHEEL, 1, 11); // wheel up
  feed(EV_REL, 0, 5, 12); // REL_X: ignored
  feed(EV_KEY, 113, 1, 13); // KEY_MUTE: ignored
  assert.deepEqual(out, [
    { kind: 'key', name: 'Ctrl', mods: { ctrl: false, alt: false, shift: false, meta: false }, ts: 1 },
    { kind: 'key', name: 'Alt', mods: { ctrl: true, alt: false, shift: false, meta: false }, ts: 2 },
    { kind: 'key', name: 'X', mods: { ctrl: true, alt: true, shift: false, meta: false }, ts: 3 },
    { kind: 'key', name: 'A', mods: { ctrl: false, alt: false, shift: false, meta: false }, ts: 8 },
    { kind: 'down', button: 'left', x: null, y: null, ts: 9 },
    { kind: 'wheel', dy: -1, x: null, y: null, ts: 11 },
  ]);
});
