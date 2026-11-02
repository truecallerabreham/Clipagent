'use strict';
// Integration: evdev worker child process + translator through startInput(), fed from a FIFO.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { encodeInputEvent, EV_KEY, EV_SYN, EV_REL, REL_WHEEL } = require('../src/lib/evdev');
const { matchHotkey } = require('../src/lib/keys');

test('evdev worker streams keys, buttons and wheel; hotkeys are detectable', { skip: process.platform !== 'linux' }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clipagent-evdev-'));
  const kbd = path.join(dir, 'kbd');
  const mouse = path.join(dir, 'mouse');
  execFileSync('mkfifo', [kbd, mouse]);
  const wk = fs.openSync(kbd, 'r+'); // O_RDWR: does not block, lets the worker's O_RDONLY open succeed
  const wm = fs.openSync(mouse, 'r+');
  process.env.CLIPAGENT_INPUT = 'evdev';
  process.env.CLIPAGENT_EVDEV_PATHS = `${kbd}:keyboard,${mouse}:mouse`;
  const { startInput } = require('../src/main/input');
  const raws = [];
  let got;
  const enough = new Promise((r) => { got = r; });
  const input = await startInput({ onRaw: (x) => { raws.push(x); if (raws.length >= 6) got(); } });
  try {
    assert.equal(input.source, 'evdev');
    assert.equal(input.warning, null);
    const sec = Math.floor(Date.now() / 1000);
    const e = (type, code, value, usec) => encodeInputEvent({ sec, usec, type, code, value });
    fs.writeSync(wk, Buffer.concat([
      e(EV_KEY, 29, 1, 1), e(EV_SYN, 0, 0, 1), e(EV_KEY, 56, 1, 2), e(EV_KEY, 45, 1, 3), // Ctrl+Alt+X
      e(EV_KEY, 45, 0, 4), e(EV_KEY, 56, 0, 5), e(EV_KEY, 29, 0, 6), e(EV_KEY, 35, 1, 7), // then 'h'
    ]));
    fs.writeSync(wm, Buffer.concat([e(EV_KEY, 0x111, 1, 8), e(EV_REL, REL_WHEEL, -2, 9)]));
    await Promise.race([enough, new Promise((_, rej) => setTimeout(() => rej(new Error(`only ${raws.length} events`)), 5000))]);
    const keys = raws.filter((r) => r.kind === 'key');
    assert.deepEqual(keys.map((k) => k.name), ['Ctrl', 'Alt', 'X', 'H']);
    assert.equal(matchHotkey(keys[2].name, keys[2].mods, 'linux'), 'marker');
    assert.equal(matchHotkey(keys[3].name, keys[3].mods, 'linux'), null);
    assert.deepEqual(raws.find((r) => r.kind === 'down'), { kind: 'down', button: 'right', x: null, y: null, ts: sec * 1000 + 0.008 });
    assert.equal(raws.find((r) => r.kind === 'wheel').dy, 2);
  } finally {
    input.stop();
    fs.closeSync(wk);
    fs.closeSync(wm);
    delete process.env.CLIPAGENT_EVDEV_PATHS;
    delete process.env.CLIPAGENT_INPUT;
  }
});

test('evdev unreadable devices yield source "none" with the input-group hint', { skip: process.platform !== 'linux' }, async () => {
  process.env.CLIPAGENT_INPUT = 'evdev';
  process.env.CLIPAGENT_EVDEV_PATHS = '/root/definitely-not-readable:keyboard';
  const { startInput } = require('../src/main/input');
  const input = await startInput({ onRaw: () => {} });
  delete process.env.CLIPAGENT_EVDEV_PATHS;
  delete process.env.CLIPAGENT_INPUT;
  assert.equal(input.source, 'none');
  assert.match(input.warning, /usermod -aG input/);
});
