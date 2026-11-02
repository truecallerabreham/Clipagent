'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { RecordingClock } = require('../src/lib/clock');

test('maps wall time to recorded time with pauses excluded', () => {
  const c = new RecordingClock();
  const T = 1_700_000_000_000;
  assert.equal(c.at(T), null);
  c.start(T);
  assert.equal(c.at(T - 1), null);
  assert.deepEqual(c.at(T + 1500), { t: 1.5, paused: false });
  assert.equal(c.pause(T + 2000), 2);
  assert.ok(c.paused);
  assert.deepEqual(c.at(T + 3000), { t: 2, paused: true });
  assert.equal(c.resume(T + 5000), 2);
  assert.deepEqual(c.at(T + 6000), { t: 3, paused: false });
  assert.equal(c.elapsed(T + 7000), 4);
  assert.deepEqual(c.pauses, [2]);
});

test('pause/resume are idempotent', () => {
  const c = new RecordingClock();
  c.start(0);
  assert.equal(c.resume(10), null);
  c.pause(1000);
  assert.equal(c.pause(1500), null);
  c.resume(2000);
  c.pause(3000);
  c.resume(4000);
  assert.deepEqual(c.pauses, [1, 2]);
  assert.equal(c.elapsed(5000), 3);
});

test('timestamps from before a resume land in the pause', () => {
  const c = new RecordingClock();
  c.start(0);
  c.pause(1000);
  c.resume(3000);
  assert.deepEqual(c.at(500), { t: 0.5, paused: false });
  assert.deepEqual(c.at(2999), { t: 1, paused: true });
});
