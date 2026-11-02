'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { parseArgs, userArgv, UsageError } = require('../src/lib/cli');

test('record mode with all options', () => {
  const o = parseArgs(['--session', '/tmp/s', '--camera', 'abc123', '--no-mic', '--display', '42']);
  assert.equal(o.mode, 'record');
  assert.equal(o.session, '/tmp/s');
  assert.equal(o.camera, 'abc123');
  assert.equal(o.mic, false);
  assert.equal(o.display, '42');
  assert.deepEqual(o.warnings, []);
});

test('defaults: camera not given, mic on', () => {
  const o = parseArgs(['--session', 's']);
  assert.equal(o.camera, null);
  assert.equal(o.mic, true);
  assert.equal(o.display, null);
});

test('--camera none/default and --opt=value form', () => {
  assert.equal(parseArgs(['--session=s', '--camera=none']).camera, 'none');
  assert.equal(parseArgs(['--session', 's', '--camera', 'default']).camera, 'default');
});

test('stop and list-devices modes', () => {
  const s = parseArgs(['--stop', '/x', '--no-wait', '--timeout', '5']);
  assert.equal(s.mode, 'stop');
  assert.equal(s.session, '/x');
  assert.equal(s.wait, false);
  assert.equal(s.timeout, 5);
  assert.equal(parseArgs(['--list-devices']).mode, 'list-devices');
});

test('usage errors', () => {
  assert.throws(() => parseArgs([]), UsageError);
  assert.throws(() => parseArgs(['--session']), UsageError);
  assert.throws(() => parseArgs(['--session', '--no-mic']), UsageError);
  assert.throws(() => parseArgs(['--session', 's', '--camera']), UsageError);
  assert.throws(() => parseArgs(['--session', 's', '--stop', 's']), UsageError);
  assert.throws(() => parseArgs(['--stop', 's', '--timeout', 'abc']), UsageError);
});

test('chromium switches are ignored, unknown options warn', () => {
  const o = parseArgs(['--no-sandbox', '--ozone-platform=x11', '--enable-features=X', '--session', 's', '--bogus']);
  assert.equal(o.session, 's');
  assert.deepEqual(o.warnings, ['ignoring unknown option --bogus']);
});

test('userArgv: dev, dev with switches, packaged', () => {
  assert.deepEqual(userArgv(['electron', '.', '--', '--session', 's'], false), ['--session', 's']);
  assert.deepEqual(userArgv(['electron', '--no-sandbox', '/app', '--', '--list-devices'], false), ['--list-devices']);
  assert.deepEqual(userArgv(['electron', '/app', '--session', 's'], false), ['--session', 's']);
  assert.deepEqual(userArgv(['/opt/clipagent-recorder', '--session', 's'], true), ['--session', 's']);
});
