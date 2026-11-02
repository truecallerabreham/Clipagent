'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {
  takePaths, buildTake, writeTake, writeState, buildState, EventsWriter, assertFreshTake, APP_VERSION,
} = require('../src/lib/take');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'clipagent-take-'));

test('take.json follows Contract 1 exactly', () => {
  const m = buildTake({
    platform: 'linux',
    startedAt: Date.parse('2026-11-02T20:31:07.120Z'),
    duration: 312.40000001,
    display: { width: 2560, height: 1440, scale: 1 },
    streams: {
      screen: { start_offset: 0 },
      camera: { start_offset: 0.0311, label: 'HD Webcam' },
      mic: { start_offset: 0.012, label: 'Built-in mic' },
    },
    input: { source: 'evdev', warning: null },
    overlayRect: [0.8, 0.02, 0.18, 0.05],
    pauses: [120.5],
  });
  assert.deepEqual(m, {
    version: 1,
    app: `clipagent-recorder ${APP_VERSION}`,
    platform: 'linux',
    started_at: '2026-11-02T20:31:07.120Z',
    duration: 312.4,
    display: { width: 2560, height: 1440, scale: 1 },
    streams: {
      screen: { file: 'screen.webm', start_offset: 0 },
      camera: { file: 'camera.webm', start_offset: 0.031, label: 'HD Webcam' },
      mic: { file: 'mic.webm', start_offset: 0.012, label: 'Built-in mic' },
    },
    input: { source: 'evdev', warning: null },
    overlay_rect: [0.8, 0.02, 0.18, 0.05],
    pauses: [[120.5, 120.5]],
  });
  assert.deepEqual(Object.keys(m), ['version', 'app', 'platform', 'started_at', 'duration', 'display', 'streams', 'input', 'overlay_rect', 'pauses']);
});

test('streams that were not recorded are omitted; overlay null; no screen is an error', () => {
  const m = buildTake({ startedAt: 0, duration: 1, display: { width: 1, height: 1, scale: 1 }, streams: { screen: {} }, input: { source: 'none', warning: 'w' }, overlayRect: null, pauses: [] });
  assert.deepEqual(Object.keys(m.streams), ['screen']);
  assert.equal(m.overlay_rect, null);
  assert.deepEqual(m.input, { source: 'none', warning: 'w' });
  assert.throws(() => buildTake({ startedAt: 0, streams: {} }));
});

test('writeTake / writeState write atomically readable JSON', () => {
  const dir = tmp();
  const p = takePaths(dir);
  fs.mkdirSync(p.dir);
  writeState(p, 'recording', { elapsed: 12.34567 });
  assert.deepEqual(JSON.parse(fs.readFileSync(p.state, 'utf8')), { status: 'recording', error: null, elapsed: 12.346 });
  writeTake(p, { startedAt: 0, duration: 2, display: { width: 10, height: 10, scale: 1 }, streams: { screen: {} }, input: { source: 'none' }, pauses: [] });
  assert.equal(JSON.parse(fs.readFileSync(p.take, 'utf8')).duration, 2);
  assert.deepEqual(fs.readdirSync(p.dir).sort(), ['state.json', 'take.json']);
  assert.throws(() => assertFreshTake(p), /already exists/);
});

test('state validation', () => {
  assert.deepEqual(buildState('error', { error: 'boom' }), { status: 'error', error: 'boom', elapsed: 0 });
  assert.throws(() => buildState('bogus'));
});

test('EventsWriter appends JSON lines', () => {
  const dir = tmp();
  const f = path.join(dir, 'events.jsonl');
  const w = new EventsWriter(f);
  w.write({ t: 1, type: 'typing' });
  w.write({ t: 2, type: 'marker', kind: 'scratch' });
  w.close();
  w.write({ t: 3, type: 'typing' }); // after close: ignored
  const lines = fs.readFileSync(f, 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  assert.deepEqual(lines, [{ t: 1, type: 'typing' }, { t: 2, type: 'marker', kind: 'scratch' }]);
});

test('takePaths', () => {
  const p = takePaths('/s');
  assert.equal(p.dir, path.resolve('/s/take'));
  assert.equal(p.stop, path.resolve('/s/take/stop'));
});
