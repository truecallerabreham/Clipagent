'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { classifyKey, matchHotkey, invertUiohookKeys, EVDEV_KEYS } = require('../src/lib/keys');

const M = (o = {}) => ({ ctrl: false, alt: false, shift: false, meta: false, ...o });

test('recorder hotkeys', () => {
  assert.equal(matchHotkey('S', M({ ctrl: true, alt: true }), 'linux'), 'stop');
  assert.equal(matchHotkey('P', M({ ctrl: true, alt: true }), 'win32'), 'pause');
  assert.equal(matchHotkey('X', M({ ctrl: true, alt: true }), 'linux'), 'marker');
  assert.equal(matchHotkey('S', M({ meta: true, alt: true }), 'darwin'), 'stop');
  assert.equal(matchHotkey('S', M({ ctrl: true, alt: true }), 'darwin'), null);
  assert.equal(matchHotkey('S', M({ ctrl: true, alt: true, shift: true }), 'linux'), null);
  assert.equal(matchHotkey('S', M({ ctrl: true }), 'linux'), null);
});

test('classifyKey labels per platform', () => {
  assert.deepEqual(classifyKey('ArrowUp', M({ meta: true }), 'linux'), { type: 'shortcut', keys: ['Super', 'Up'] });
  assert.deepEqual(classifyKey('Numpad5', M({ ctrl: true }), 'win32'), { type: 'shortcut', keys: ['Ctrl', '5'] });
  assert.deepEqual(classifyKey('F12', M(), 'win32'), { type: 'shortcut', keys: ['F12'] });
  assert.deepEqual(classifyKey('ArrowUp', M(), 'linux'), { type: 'typing' });
  assert.equal(classifyKey('CtrlRight', M({ ctrl: true }), 'linux'), null);
});

test('uiohook key table inversion', () => {
  const inv = invertUiohookKeys({ A: 30, Escape: 1, Ctrl: 29 });
  assert.equal(inv[30], 'A');
  assert.equal(inv[1], 'Escape');
});

test('evdev table covers letters, digits and F-keys', () => {
  const names = new Set(Object.values(EVDEV_KEYS));
  for (const c of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') assert.ok(names.has(c), c);
  for (let i = 1; i <= 24; i++) assert.ok(names.has(`F${i}`), `F${i}`);
});
