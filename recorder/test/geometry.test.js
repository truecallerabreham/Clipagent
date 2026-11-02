'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { matchDisplay, overlayRect, inputRect, barPosition } = require('../src/lib/geometry');

const A = { id: 1, bounds: { x: 0, y: 0, width: 1536, height: 864 }, scaleFactor: 1.25 };
const B = { id: 2, bounds: { x: 1536, y: 0, width: 2560, height: 1440 }, scaleFactor: 1 };

test('matchDisplay by id, physical size, aspect, primary', () => {
  assert.equal(matchDisplay([A, B], { id: 2 }).id, 2);
  assert.equal(matchDisplay([A, B], { width: 1920, height: 1080, primaryId: 2 }).id, 1);
  assert.equal(matchDisplay([A, B], { width: 2560, height: 1440, primaryId: 1 }).id, 2);
  assert.equal(matchDisplay([A, B], { width: 1280, height: 720, primaryId: 2 }).id, 2); // both 16:9: primary first
  assert.equal(matchDisplay([A, B], { primaryId: 2 }).id, 2);
  assert.equal(matchDisplay([], {}), null);
});

test('overlayRect normalizes and clips to the display', () => {
  assert.deepEqual(overlayRect({ x: 1280, y: 16, width: 236, height: 48 }, A.bounds), [0.8333, 0.0185, 0.1536, 0.0556]);
  assert.equal(overlayRect({ x: 1600, y: 16, width: 236, height: 48 }, A.bounds), null);
  assert.deepEqual(overlayRect({ x: 1500, y: 0, width: 100, height: 864 }, A.bounds), [0.9766, 0, 0.0234, 1]);
});

test('inputRect per platform', () => {
  assert.deepEqual(inputRect(A, 'darwin'), A.bounds);
  assert.deepEqual(inputRect(A, 'linux'), { x: 0, y: 0, width: 1920, height: 1080 });
  assert.deepEqual(inputRect(A, 'win32', (r) => ({ ...r, width: r.width * 2 })), { x: 0, y: 0, width: 3072, height: 864 });
});

test('barPosition top-right of the work area', () => {
  assert.deepEqual(barPosition({ x: 0, y: 32, width: 1536, height: 832 }, { width: 236, height: 48 }), { x: 1284, y: 48, width: 236, height: 48 });
});
