'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { requestStop } = require('../src/lib/stopper');
const { takePaths, writeState } = require('../src/lib/take');

test('--stop without a take dir fails', async () => {
  const r = await requestStop(fs.mkdtempSync(path.join(os.tmpdir(), 'clipagent-stop-')));
  assert.equal(r.code, 1);
});

test('--stop creates take/stop and waits for done', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clipagent-stop-'));
  const p = takePaths(dir);
  fs.mkdirSync(p.dir);
  writeState(p, 'recording', { elapsed: 1 });
  setTimeout(() => {
    assert.ok(fs.existsSync(p.stop));
    writeState(p, 'done', { elapsed: 2 });
  }, 100);
  const r = await requestStop(dir, { timeout: 5, poll: 20 });
  assert.equal(r.code, 0);
  assert.equal(r.state.status, 'done');
});

test('--stop --no-wait returns immediately; timeout reports code 2', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'clipagent-stop-'));
  const p = takePaths(dir);
  fs.mkdirSync(p.dir);
  writeState(p, 'recording');
  assert.equal((await requestStop(dir, { wait: false })).code, 0);
  assert.ok(fs.existsSync(p.stop));
  assert.equal((await requestStop(dir, { timeout: 0.1, poll: 20 })).code, 2);
});
