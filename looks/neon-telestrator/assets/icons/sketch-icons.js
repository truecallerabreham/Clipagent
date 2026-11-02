/* neon-telestrator sketch icons: original line art for the ClipAgent project (license: CC0-1.0, see LICENSE.txt).
 * Each icon is a list of pen strokes in a 100 x 100 box, drawn in order by the Icon primitive.
 *   ['line', x1, y1, x2, y2]            straight stroke (gets a slight hand bow)
 *   ['circle', cx, cy, r]               closed loop
 *   ['ellipse', cx, cy, rx, ry, a0, a1] arc in degrees (0 = right, 90 = down); full ellipse when a0/a1 omitted
 *   ['rect', x, y, w, h, r]             rounded rectangle, one stroke
 *   ['poly', [[x, y], ...], closed]     polyline
 *   ['path', 'svg d']                   any SVG path (sampled)
 *   ['dot', cx, cy, r]                  small filled dot
 *   ['text', cx, cy, 'TXT', size]       handwritten text
 * Options on any stroke: { w: width multiplier, c: 'accent' (use the icon's accent color) }
 */
(function () {
  const nn = [];
  const L1 = [[16, 24], [16, 50], [16, 76]];
  const L2 = [[50, 13], [50, 38], [50, 62], [50, 87]];
  const L3 = [[84, 34], [84, 66]];
  const R = 7;
  const link = (a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy);
    return ['line', a[0] + (dx / l) * R, a[1] + (dy / l) * R, b[0] - (dx / l) * R, b[1] - (dy / l) * R, { w: 0.62 }];
  };
  L1.forEach((p) => nn.push(['circle', p[0], p[1], R]));
  L1.forEach((a) => L2.forEach((b) => nn.push(link(a, b))));
  L2.forEach((p) => nn.push(['circle', p[0], p[1], R]));
  L2.forEach((a) => L3.forEach((b) => nn.push(link(a, b))));
  L3.forEach((p) => nn.push(['circle', p[0], p[1], R, { c: 'accent' }]));

  const server = [];
  [10, 38, 66].forEach((y) => {
    server.push(['rect', 12, y, 76, 24, 5]);
    server.push(['dot', 22, y + 12, 2.6, { c: 'accent' }]);
    server.push(['dot', 30, y + 12, 2.6]);
    server.push(['line', 50, y + 12, 78, y + 12, { w: 0.7 }]);
  });

  const gpu = [['rect', 20, 20, 60, 60, 6], ['rect', 32, 32, 36, 36, 3, { w: 0.8 }]];
  [34, 50, 66].forEach((o) => {
    gpu.push(['line', o, 20, o, 8, { w: 0.7 }], ['line', o, 80, o, 92, { w: 0.7 }]);
    gpu.push(['line', 20, o, 8, o, { w: 0.7 }], ['line', 80, o, 92, o, { w: 0.7 }]);
  });
  gpu.push(['text', 50, 51, 'GPU', 15, { c: 'accent' }]);

  window.NT_ICONS = {
    'neural-net': nn,
    server,
    user: [
      ['circle', 50, 31, 17],
      ['path', 'M16,90 C16,68 31,57 50,57 C69,57 84,68 84,90'],
    ],
    database: [
      ['ellipse', 50, 20, 32, 10],
      ['line', 18, 20, 18, 80],
      ['line', 82, 20, 82, 80],
      ['ellipse', 50, 40, 32, 10, 0, 180, { w: 0.8 }],
      ['ellipse', 50, 60, 32, 10, 0, 180, { w: 0.8 }],
      ['ellipse', 50, 80, 32, 10, 0, 180],
    ],
    gpu,
    dollar: [
      ['circle', 50, 50, 41],
      ['path', 'M63,35 C60,29 55,27 49,27 C41,27 36,32 36,38 C36,46 44,48 50,50 C58,52 65,55 65,63 C65,70 58,73 50,73 C43,73 37,70 35,64'],
      ['line', 50, 18, 50, 27],
      ['line', 50, 73, 50, 82],
    ],
    cloud: [
      ['path', 'M28,74 C13,74 9,57 22,51 C20,37 36,29 46,37 C52,23 75,25 76,43 C90,43 93,61 84,70 C81,73 77,74 73,74 L28,74'],
    ],
    document: [
      ['path', 'M24,10 L62,10 L78,26 L78,90 L24,90 Z'],
      ['path', 'M62,10 L62,26 L78,26', { w: 0.8 }],
      ['line', 34, 44, 68, 44, { w: 0.7 }],
      ['line', 34, 58, 68, 58, { w: 0.7 }],
      ['line', 34, 72, 56, 72, { w: 0.7 }],
    ],
    bolt: [['poly', [[58, 8], [26, 56], [48, 56], [40, 92], [74, 42], [52, 42], [58, 8]], false]],
    lock: [
      ['rect', 22, 44, 56, 46, 6],
      ['path', 'M34,44 L34,32 C34,14 66,14 66,32 L66,44'],
      ['dot', 50, 64, 4],
      ['line', 50, 66, 50, 76, { w: 0.8 }],
    ],
    clock: [
      ['circle', 50, 50, 40],
      ['line', 50, 50, 50, 26],
      ['line', 50, 50, 67, 60],
    ],
    chat: [
      ['path', 'M18,22 L82,22 C86,22 88,24 88,28 L88,62 C88,66 86,68 82,68 L44,68 L28,84 L30,68 L18,68 C14,68 12,66 12,62 L12,28 C12,24 14,22 18,22 Z'],
      ['line', 28, 38, 72, 38, { w: 0.7 }],
      ['line', 28, 52, 60, 52, { w: 0.7 }],
    ],
  };
  const alias = { neural: 'neural-net', nn: 'neural-net', brain: 'neural-net', model: 'neural-net', servers: 'server', 'server-stack': 'server',
    avatar: 'user', person: 'user', db: 'database', chip: 'gpu', cpu: 'gpu', money: 'dollar', coin: 'dollar', doc: 'document', file: 'document',
    lightning: 'bolt', fast: 'bolt', time: 'clock', latency: 'clock', message: 'chat', prompt: 'chat' };
  for (const k in alias) window.NT_ICONS[k] = window.NT_ICONS[alias[k]];
})();
