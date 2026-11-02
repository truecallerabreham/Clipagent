/* neon-telestrator Look: Primitives. Scene vocabulary is documented in PRIMITIVES.md.
 *
 * Ink engine: every hand-drawn mark is a Stroke, a dense polyline (seeded wobble) rendered as a filled
 * outline whose width follows a simulated stylus pressure (taper in, taper out, pen-tip taper at the
 * leading edge, slow pressure noise). Drawing on = recomputing the outline up to the drawn length, so the
 * pen tip is always correctly tapered. Strokes get a per-primitive SVG filter (grain + edge roughness +
 * two-level neon glow). Handwritten text writes on glyph by glyph with a feathered wipe.
 * Everything is compiled from Beats into tracks/windows at build time; render(t) is pure.
 */
(function () {
  'use strict';
  const CA = window.CA;
  const {
    Primitive, Track, Events, PathLUT, register, registerLayout, el, svgEl, css, attr, text,
    clamp, lerp, prog, bump, getEase, ease, cubicBezier, rgba, mixColor, formatNumber, parseNumber, hashStr,
  } = CA;

  const INK = { white: '#FFFFFF', green: '#2ECC71', red: '#FF2A2A', purple: '#D946EF', blue: '#3B82F6', yellow: '#FACC15', grid: '#222222', dim: '#A1A1AA' };
  const SERIES = [INK.purple, INK.blue, INK.green, INK.yellow, INK.white];
  const PEN_SPEED = 1500;          // design px per second at the nominal pen speed
  const CHAR_TIME = 0.045;         // seconds per handwritten glyph
  const penEase = cubicBezier(0.3, 0.02, 0.4, 1);

  // ------------------------------------------------------------------ media (Screenshot src)
  const params = new URLSearchParams(location.search);
  const specUrl = params.get('spec');
  const specBase = specUrl ? new URL(specUrl, location.href) : new URL(location.href);
  /** Map a spec `src` to a URL: absolute local paths go through the renderer's /@file/ route,
   *  relative paths resolve against the spec file, URLs pass through. */
  function mediaUrl(src) {
    const s = String(src || '');
    if (/^(https?:|data:|blob:)/i.test(s) || s.startsWith('/@file/') || s.startsWith('/spec/') || s.startsWith('/looks/')) return s;
    if (s.startsWith('/') || /^[A-Za-z]:[\\/]/.test(s)) {
      const p = s.replace(/\\/g, '/');
      return '/@file' + (p.startsWith('/') ? '' : '/') + encodeURI(p).replace(/#/g, '%23').replace(/\?/g, '%3F');
    }
    if (s.startsWith('file://')) return mediaUrl(decodeURI(s.slice(7)));
    return new URL(s, specBase).href;
  }
  // Preload + decode every image the spec references before the scene is built, by extending the
  // promise the runtime awaits (document.fonts.ready) - images are then ready for the first seek().
  const IMG = new Map();
  const imgErrors = [];
  const theSpec = (window.clipagent && window.clipagent.spec) || {};
  const srcs = new Set();
  for (const d of (theSpec.scene && theSpec.scene.elements) || []) if (d && d.props && d.props.src) srcs.add(d.props.src);
  const imagesReady = Promise.all([...srcs].map((src) => new Promise((res) => {
    const im = new Image();
    const url = mediaUrl(src);
    im.onload = () => { (im.decode ? im.decode() : Promise.resolve()).catch(() => null).then(() => { IMG.set(src, im); res(); }); };
    im.onerror = () => { imgErrors.push(`Screenshot: cannot load image "${src}" (as ${url}). Use an absolute path to a .png/.jpg/.webp/.gif or a path relative to the spec file.`); res(); };
    im.src = url;
  })));
  try {
    const desc = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(document.fonts), 'ready');
    if (desc && desc.get && srcs.size) {
      Object.defineProperty(document.fonts, 'ready', { configurable: true, get() { return Promise.all([desc.get.call(document.fonts), imagesReady]).then(() => document.fonts); } });
    }
  } catch (e) { /* older engines: images still load, just not awaited */ }

  // ------------------------------------------------------------------ deterministic noise
  function hash2(a, b) {
    let h = Math.imul((a | 0) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((b | 0) + 0x632be5ab, 0xc2b2ae35);
    h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15;
    return (h >>> 0) / 4294967296;
  }
  function vnoise(seed, x) {
    const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
    const a = hash2(seed, i) * 2 - 1, b = hash2(seed, i + 1) * 2 - 1;
    return a + (b - a) * u;
  }
  const fbm = (seed, x) => vnoise(seed, x) * 0.72 + vnoise(seed + 101, x * 2.3) * 0.28;
  const rnd = (seed, i) => hash2(seed, i);
  const sm = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };

  // ------------------------------------------------------------------ geometry
  const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
  function resample(pts, step) {
    if (pts.length < 2) return [pts[0], pts[0]];
    const lut = PathLUT.fromPoints(pts);
    const n = Math.max(2, Math.ceil(lut.length / step));
    const out = [];
    for (let i = 0; i <= n; i++) { const q = lut.at((lut.length * i) / n); out.push([q.x, q.y]); }
    return out;
  }
  function polyLen(pts) { let L = 0; for (let i = 1; i < pts.length; i++) L += dist(pts[i - 1], pts[i]); return L; }
  /** Seeded low-frequency hand wobble along the normal. */
  function wobble(pts, seed, amp, wl) {
    const n = pts.length, out = [];
    let s = 0;
    for (let i = 0; i < n; i++) {
      if (i) s += dist(pts[i - 1], pts[i]);
      const a = pts[Math.max(0, i - 1)], b = pts[Math.min(n - 1, i + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
      const o = amp * fbm(seed, s / wl);
      out.push([pts[i][0] - (dy / l) * o, pts[i][1] + (dx / l) * o]);
    }
    return out;
  }
  /** Raw points -> hand-drawn points (uniform spacing + wobble scaled to the stroke size). */
  function handPts(pts, seed, k = 1) {
    const P = resample(pts, 3);
    const L = polyLen(P);
    const amp = clamp(0.45 + L * 0.0022, 0.45, 2.4) * k;
    return wobble(P, seed, amp, clamp(L * 0.28, 30, 170));
  }
  function bowLine(a, b, seed, amt = 0.025) {
    const L = dist(a, b), n = Math.max(4, Math.ceil(L / 4));
    const nx = -(b[1] - a[1]) / (L || 1), ny = (b[0] - a[0]) / (L || 1);
    const bow = L * amt * (rnd(seed, 5) * 2 - 1);
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const f = i / n, k = 4 * f * (1 - f) * bow;
      pts.push([lerp(a[0], b[0], f) + nx * k, lerp(a[1], b[1], f) + ny * k]);
    }
    return pts;
  }
  function ellipsePts(cx, cy, rx, ry, a0, a1, rot = 0) {
    const n = Math.max(12, Math.ceil((Math.abs(a1 - a0) * Math.max(rx, ry)) / 3));
    const c = Math.cos(rot), s = Math.sin(rot), out = [];
    for (let i = 0; i <= n; i++) {
      const a = lerp(a0, a1, i / n), x = Math.cos(a) * rx, y = Math.sin(a) * ry;
      out.push([cx + x * c - y * s, cy + x * s + y * c]);
    }
    return out;
  }
  function rectPts(x, y, w, h, r, overshoot = 0) {
    r = Math.min(r, w / 2, h / 2);
    const pts = [];
    const arc = (cx, cy, a0) => { for (let i = 0; i <= 6; i++) { const a = a0 + (Math.PI / 2) * (i / 6); pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } };
    pts.push([x + r, y]);
    arc(x + w - r, y + r, -Math.PI / 2);
    arc(x + w - r, y + h - r, 0);
    arc(x + r, y + h - r, Math.PI / 2);
    arc(x + r, y + r, Math.PI);
    pts.push([x + r + overshoot, y + (overshoot ? -1.5 : 0)]);
    return pts;
  }
  function pathPts(d, step = 2) { return PathLUT.fromPath(d, step).points(); }
  function quadPts(a, c, b, n) {
    const out = [];
    for (let i = 0; i <= n; i++) {
      const t = i / n, u = 1 - t;
      out.push([u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]]);
    }
    return out;
  }
  function catmull(pts, per = 12) {
    if (pts.length < 3) return pts.slice();
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
      for (let j = 0; j < per; j++) {
        const t = j / per, t2 = t * t, t3 = t2 * t;
        out.push([0, 1].map((k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)));
      }
    }
    out.push(pts[pts.length - 1]);
    return out;
  }
  const bbox = (pts) => {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const p of pts) { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
    return CA.box((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0);
  };
  const unionBox = (bs) => {
    bs = bs.filter(Boolean);
    if (!bs.length) return CA.box(0, 0, 0, 0);
    const x0 = Math.min(...bs.map((b) => b.x)), y0 = Math.min(...bs.map((b) => b.y));
    const x1 = Math.max(...bs.map((b) => b.r)), y1 = Math.max(...bs.map((b) => b.b));
    return CA.box((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0);
  };
  const padBox = (b, px, py = px) => CA.box(b.cx, b.cy, b.w + 2 * px, b.h + 2 * py);
  /** Point where the ray from the box center toward `toward` leaves the box (+gap). */
  function boxExit(b, toward, gap = 0) {
    const dx = toward[0] - b.cx, dy = toward[1] - b.cy;
    if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) return [b.cx, b.cy];
    const hw = b.w / 2 + gap, hh = b.h / 2 + gap;
    const k = Math.min(Math.abs(dx) > 1e-6 ? hw / Math.abs(dx) : Infinity, Math.abs(dy) > 1e-6 ? hh / Math.abs(dy) : Infinity);
    return [b.cx + dx * k, b.cy + dy * k];
  }
  const f1 = (v) => (Math.round(v * 10) / 10).toString();
  const pt = (p) => f1(p[0]) + ',' + f1(p[1]);

  // ------------------------------------------------------------------ Stroke: pressure-sensitive ink
  class Stroke {
    constructor(pts, o = {}) {
      this.P = resample(pts, 2);
      this.cum = new Float64Array(this.P.length);
      for (let i = 1; i < this.P.length; i++) this.cum[i] = this.cum[i - 1] + dist(this.P[i - 1], this.P[i]);
      this.L = this.cum[this.P.length - 1] || 0.001;
      this.width = o.width ?? 4;
      this.seed = o.seed | 0;
      this.taper = o.taper ?? 1;
    }
    widthAt(s, Ld) {
      const L = this.L, tp = this.taper;
      const tin = Math.min(14, L * 0.22), tout = Math.min(30, L * 0.32);
      let pr = 1 - tp * 0.6 * (1 - sm(s / tin));
      pr *= 1 - tp * 0.72 * (1 - sm((L - s) / tout));
      pr *= 0.5 + 0.5 * sm((Ld - s) / 7);
      pr *= 1 + 0.17 * vnoise(this.seed, s / 40) + 0.06 * vnoise(this.seed + 3, s / 8);
      return Math.max(0.7, this.width * pr);
    }
    /** Filled outline d-string of the stroke drawn up to fraction p. */
    d(p) {
      const Ld = clamp(p) * this.L;
      if (Ld < 0.8) return '';
      const P = this.P, cum = this.cum, pts = [], ss = [];
      let i = 0;
      for (; i < P.length && cum[i] < Ld; i++) { pts.push(P[i]); ss.push(cum[i]); }
      if (i < P.length && i > 0) {
        const a = P[i - 1], b = P[i], f = (Ld - cum[i - 1]) / (cum[i] - cum[i - 1] || 1);
        pts.push([lerp(a[0], b[0], f), lerp(a[1], b[1], f)]); ss.push(Ld);
      }
      const n = pts.length;
      if (n < 2) return '';
      const Lf = [], Rt = [];
      let w0 = 1, wn = 1;
      for (let j = 0; j < n; j++) {
        const a = pts[Math.max(0, j - 2)], b = pts[Math.min(n - 1, j + 2)];
        let dx = b[0] - a[0], dy = b[1] - a[1];
        const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
        const w = this.widthAt(ss[j], Ld) / 2;
        if (j === 0) w0 = w;
        if (j === n - 1) wn = w;
        Lf.push([pts[j][0] - dy * w, pts[j][1] + dx * w]);
        Rt.push([pts[j][0] + dy * w, pts[j][1] - dx * w]);
      }
      let d = 'M' + pt(Lf[0]);
      for (let j = 1; j < n; j++) d += 'L' + pt(Lf[j]);
      d += `A${f1(wn)} ${f1(wn)} 0 0 0 ${pt(Rt[n - 1])}`;
      for (let j = n - 2; j >= 0; j--) d += 'L' + pt(Rt[j]);
      d += `A${f1(w0)} ${f1(w0)} 0 0 0 ${pt(Lf[0])}Z`;
      return d;
    }
  }

  // ------------------------------------------------------------------ handwritten text (write-on)
  const textGlow = (c, k = 1) => (k <= 0 ? '0 0 3px rgba(0,0,0,0.5)' : `0 0 ${(4 * k).toFixed(1)}px ${rgba(c, 0.5)}, 0 0 ${(14 * k).toFixed(1)}px ${rgba(c, 0.25)}, 0 0 3px rgba(0,0,0,0.55)`);
  class HandText {
    /** o: {x, y, size, color, font: 'hand'|'script', bold, align: left|center|right, valign: top|middle|bottom, rotate, glow, opacity} */
    constructor(parent, str, o) {
      this.o = o;
      this.el = el('div', { class: 'nt-hand' + (o.font === 'script' ? ' script' : '') + (o.bold ? ' bold' : '') }, parent);
      this.el.style.fontSize = (o.size || 40) + 'px';
      this.el.style.color = o.color || INK.white;
      this.el.style.textShadow = textGlow(o.color || INK.white, o.glow ?? 1);
      if (o.opacity != null) this.el.style.opacity = String(o.opacity);
      this.setText(str, true);
      this.layout();
    }
    setText(str, initial) {
      this.str = String(str);
      this.el.textContent = '';
      this.chars = [];
      for (const line of this.str.split('\n')) {
        const ln = el('div', { class: 'ln' }, this.el);
        ln.style.textAlign = this.o.align || 'center';
        if (!line.length) { ln.innerHTML = '&nbsp;'; continue; }
        for (const ch of line) { const s = el('span', { class: 'ch' }, ln); s.textContent = ch; this.chars.push({ el: s, ch }); }
      }
      let acc = 0;
      const avg = (this.o.size || 40) * 0.5;
      for (const c of this.chars) { c.a = acc; acc += c.ch === ' ' ? avg * 0.35 : Math.max(4, c.el.offsetWidth); c.b = acc; }
      this.total = acc || 1;
      this._p = initial ? -1 : 2;
      if (!initial) for (const c of this.chars) { c.el.style.visibility = 'visible'; c.el.style.maskImage = 'none'; c.state = 2; }
    }
    layout() {
      const o = this.o;
      this.w = this.el.offsetWidth; this.h = this.el.offsetHeight;
      const al = o.align || 'center', va = o.valign || 'middle';
      this.x = al === 'left' ? o.x : al === 'right' ? o.x - this.w : o.x - this.w / 2;
      this.y = va === 'top' ? o.y : va === 'bottom' ? o.y - this.h : o.y - this.h / 2;
      this.el.style.left = this.x.toFixed(1) + 'px';
      this.el.style.top = this.y.toFixed(1) + 'px';
      if (o.rotate) this.el.style.transform = `rotate(${o.rotate.toFixed(2)}deg)`;
    }
    get box() { return CA.box(this.x + this.w / 2, this.y + this.h / 2, this.w, this.h); }
    get dur() { return clamp(this.chars.length * CHAR_TIME, 0.2, 2.4); }
    render(p) {
      if (p === this._p) return;
      this._p = p;
      const pos = p * this.total;
      for (const c of this.chars) {
        let st;
        if (pos >= c.b) st = 2; else if (pos <= c.a) st = 0; else st = 1;
        if (st !== 1 && c.state === st) continue;
        c.state = st;
        if (st === 2) { css(c.el, 'visibility', 'visible'); css(c.el, 'maskImage', 'none'); }
        else if (st === 0) css(c.el, 'visibility', 'hidden');
        else {
          const q = (pos - c.a) / (c.b - c.a);
          css(c.el, 'visibility', 'visible');
          css(c.el, 'maskImage', `linear-gradient(100deg, #000 ${(q * 150 - 50).toFixed(1)}%, transparent ${(q * 150).toFixed(1)}%)`);
        }
      }
    }
  }

  // ------------------------------------------------------------------ references to things on the canvas
  /** A ref is: an element id string, [x, y] (canvas fractions), [x, y, w, h] (canvas fractions), or an
   *  object {target, region, at, box, line, bar, point, series, index, pad, dx, dy}. Returns {box, pt}. */
  function normRef(r) {
    if (r == null) return null;
    if (typeof r === 'string') return { target: r };
    if (Array.isArray(r)) return r.length >= 4 ? { box: r } : { at: r };
    return r;
  }
  function resolveRef(S, r0, t) {
    const r = normRef(r0);
    if (!r) throw new Error('missing target (give "target", "box" or "at")');
    let b;
    if (r.target) {
      const e = S.get(r.target);
      b = e.refBox ? e.refBox(r, t) : e.box;
    } else if (r.box) b = CA.box((r.box[0] + r.box[2] / 2) * S.W, (r.box[1] + r.box[3] / 2) * S.H, r.box[2] * S.W, r.box[3] * S.H);
    else if (r.at) b = CA.box(r.at[0] * S.W, r.at[1] * S.H, 0, 0);
    else throw new Error('ref needs "target", "box" or "at": ' + JSON.stringify(r0));
    if (r.pad) b = padBox(b, r.pad);
    if (r.dx || r.dy) b = CA.box(b.cx + (r.dx || 0), b.cy + (r.dy || 0), b.w, b.h);
    return { box: b, pt: [b.cx, b.cy] };
  }
  /** Sub-box from fractional region [x, y, w, h] of a box. */
  function regionOf(b, reg) {
    if (!reg) return b;
    return CA.box(b.x + (reg[0] + reg[2] / 2) * b.w, b.y + (reg[1] + reg[3] / 2) * b.h, reg[2] * b.w, reg[3] * b.h);
  }
  const refKeys = ['target', 'region', 'at', 'box', 'line', 'bar', 'point', 'series', 'index', 'pad', 'dx', 'dy', 'part'];
  const pickRef = (o) => { const r = {}; for (const k of refKeys) if (o[k] != null) r[k] = o[k]; return r; };

  // ------------------------------------------------------------------ ink filter (grain + roughness + neon glow)
  function inkFilter(S, id, bb, glow = 1) {
    const m = 48;
    const f = svgEl('filter', { id, filterUnits: 'userSpaceOnUse', x: Math.floor(bb.x - m), y: Math.floor(bb.y - m), width: Math.ceil(bb.w + 2 * m), height: Math.ceil(bb.h + 2 * m), 'color-interpolation-filters': 'sRGB' }, S.defs);
    svgEl('feTurbulence', { type: 'fractalNoise', baseFrequency: '0.85', numOctaves: 2, seed: 7, result: 'n' }, f);
    svgEl('feDisplacementMap', { in: 'SourceGraphic', in2: 'n', scale: 1.7, xChannelSelector: 'R', yChannelSelector: 'G', result: 'r' }, f);
    svgEl('feColorMatrix', { in: 'n', type: 'matrix', values: '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.2 2.05', result: 'a' }, f);
    svgEl('feComposite', { in: 'r', in2: 'a', operator: 'in', result: 'ink' }, f);
    if (glow > 0) {
      svgEl('feGaussianBlur', { in: 'ink', stdDeviation: 2.2, result: 'g1' }, f);
      svgEl('feGaussianBlur', { in: 'ink', stdDeviation: 8, result: 'g2' }, f);
      const c1 = svgEl('feComponentTransfer', { in: 'g1', result: 'g1b' }, f); svgEl('feFuncA', { type: 'linear', slope: (0.75 * glow).toFixed(2) }, c1);
      const c2 = svgEl('feComponentTransfer', { in: 'g2', result: 'g2b' }, f); svgEl('feFuncA', { type: 'linear', slope: (0.7 * glow).toFixed(2) }, c2);
      // soft dark under-halo: invisible on the black canvas, keeps neon ink legible over light screenshots
      svgEl('feColorMatrix', { in: 'ink', type: 'matrix', values: '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.5 0', result: 'sh0' }, f);
      svgEl('feGaussianBlur', { in: 'sh0', stdDeviation: 2.5, result: 'sh' }, f);
      const mg = svgEl('feMerge', {}, f);
      for (const r of ['sh', 'g2b', 'g1b', 'ink']) svgEl('feMergeNode', { in: r }, mg);
    }
    return `url(#${id})`;
  }

  // ------------------------------------------------------------------ InkPrim: base for everything drawn with the pen
  const DRAW_ACTIONS = new Set(['enter', 'draw', 'write', 'point']);
  class InkPrim extends Primitive {
    static layer = 'pills';
    static lazy = false; // true: geometry depends on other elements and is built at the first draw
    static defaults = { color: null, width: 4, seed: null, glow: 1 };
    static actions = {
      enter: { ease: 'inOut' }, draw: { ease: 'inOut' }, write: { ease: 'inOut' }, erase: { dur: 0.45, ease: 'inOut' },
      exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, pulse: { dur: 0.7 },
    };
    defaultColor() { return INK.white; }
    get color() { return this.scene.resolveColor(this.props.color) || this.defaultColor(); }
    get isLazy() { return this.constructor.lazy; }
    build() {
      const S = this.scene;
      this.root.classList.add('nt-ink');
      Object.assign(this.root.style, { width: S.W + 'px', height: S.H + 'px', left: '0px', top: '0px' });
      this.svg = svgEl('svg', { width: S.W, height: S.H, viewBox: `0 0 ${S.W} ${S.H}` }, this.root);
      this.under = svgEl('g', {}, this.svg); // unfiltered fills under the ink
      this.g = svgEl('g', {}, this.svg);
      this.items = [];
      this.seed = this.props.seed != null ? this.props.seed | 0 : hashStr(this.id) & 0xffff;
      this.events = new Events();
      this._built = false;
      this.texts = [];
      this.build2();
    }
    build2() {}
    measure() { this.w = this.scene.W; this.h = this.scene.H; return { w: this.w, h: this.h }; }
    place() { this.cx = this.scene.W / 2; this.cy = this.scene.H / 2; }
    afterLayout() { if (!this.isLazy) this.ensure(0); }
    ensure(t) {
      if (this._built) return;
      this._built = true;
      this.geometry(t);
      this.finishGeometry();
    }
    geometry() {}
    // ---- items
    addStroke(pts, o = {}) {
      const s = new Stroke(o.raw ? pts : handPts(pts, this.seed + this.items.length * 13 + 1, o.wobble ?? 1), {
        width: (o.width ?? this.props.width ?? 4), seed: this.seed + this.items.length * 7, taper: o.taper,
      });
      const color = o.color || this.color;
      const path = svgEl('path', { fill: color, d: '' }, o.parent || this.g);
      if (o.opacity != null) attr(path, 'opacity', o.opacity);
      const it = { kind: 'stroke', s, el: path, weight: (s.L / PEN_SPEED) * (o.speed ? 1 / o.speed : 1), pause: o.pause ?? 0.05, box: bbox(s.P), _p: -1, group: o.group };
      this.items.push(it);
      return it;
    }
    addText(str, o) {
      const ht = new HandText(this.root, str, Object.assign({ color: this.color, glow: this.props.glow }, o));
      const it = { kind: 'text', ht, weight: ht.dur * (o.speed ? 1 / o.speed : 1), pause: o.pause ?? 0.08, box: ht.box, group: o.group };
      this.items.push(it);
      this.texts.push(ht);
      return it;
    }
    addDot(cx, cy, r, color, o = {}) {
      const c = svgEl('circle', { cx: f1(cx), cy: f1(cy), r: 0, fill: color || this.color }, o.parent || this.g);
      const it = { kind: 'dot', el: c, r, weight: 0.06, pause: o.pause ?? 0.02, box: CA.box(cx, cy, 2 * r, 2 * r), group: o.group };
      this.items.push(it);
      return it;
    }
    addFade(elem, o = {}) {
      const it = { kind: 'fade', el: elem, weight: o.weight ?? 0.15, pause: o.pause ?? 0, box: o.box || null, max: o.max ?? 1, group: o.group, html: !!o.html };
      this.items.push(it);
      return it;
    }
    finishGeometry() {
      const bs = this.items.filter((i) => i.kind !== 'text' && i.box).map((i) => i.box);
      this.geomBox = unionBox(this.items.map((i) => i.box));
      if (bs.length && this.props.glow !== 0) attr(this.g, 'filter', inkFilter(this.scene, 'nt-f-' + this.id.replace(/[^\w-]/g, '_'), unionBox(bs), this.props.glow ?? 1));
      let acc = 0;
      for (const it of this.items) { it.f0 = acc; acc += it.weight; it.f1 = acc; acc += it.pause; }
      this.totalWeight = Math.max(0.001, acc - (this.items.length ? this.items[this.items.length - 1].pause : 0));
      for (const it of this.items) { it.f0 /= this.totalWeight; it.f1 = Math.min(1, it.f1 / this.totalWeight); }
    }
    refBox(r, t) { this.ensure(t ?? 0); return regionOf(this.geomBox, r && r.region); }
    hasDrawBeat() {
      if (this._hasDraw == null) {
        this._hasDraw = (this.scene.spec.beats || []).some((b) => DRAW_ACTIONS.has(b.action) && (Array.isArray(b.target) ? b.target.includes(this.id) : b.target === this.id));
      }
      return this._hasDraw;
    }
    autoDur() { return clamp(this.totalWeight, 0.25, this.constructor.maxDur || 2.6); }
    a_enter(at, dur, e, args, beat) { if (beat && beat.auto && this.hasDrawBeat()) return; this.drawAt(at, args); }
    a_draw(at, dur, e, args) { this.drawAt(at, args); }
    a_write(at, dur, e, args) { this.drawAt(at, args); }
    drawAt(at, args = {}) {
      this.ensure(at);
      const D = args.dur != null ? Math.max(0.05, +args.dur) : this.autoDur();
      this.events.add(at, { kind: 'draw', D });
      this.vis.to(at, 1, 0);
      if (this.enterAt == null || at < this.enterAt) this.enterAt = at;
      return D;
    }
    a_erase(at, dur) { this.events.add(at, { kind: 'erase', D: dur }); this.vis.to(at + dur, 0, 0); }
    /** Draw progress 0..1 of one item at t. */
    itemP(it, t) {
      const ev = this.events.last(t);
      if (!ev) return 0;
      if (ev.kind === 'erase') return 1 - ease.inOut(clamp((t - ev.at) / ev.D));
      const a = ev.at + it.f0 * ev.D, b = ev.at + it.f1 * ev.D;
      return b <= a ? (t >= a ? 1 : 0) : clamp((t - a) / (b - a));
    }
    renderItem(it, p) {
      if (it.kind === 'stroke') {
        const q = Math.round(penEase(p) * 2000) / 2000;
        if (q !== it._p) { it._p = q; attr(it.el, 'd', it.s.d(q)); }
      } else if (it.kind === 'text') it.ht.render(p);
      else if (it.kind === 'dot') attr(it.el, 'r', (it.r * ease.outBack(clamp(p))).toFixed(2));
      else if (it.kind === 'fade') { if (it.html) css(it.el, 'opacity', (p * it.max).toFixed(3)); else attr(it.el, 'opacity', (p * it.max).toFixed(3)); }
    }
    render(t) {
      super.render(t);
      if (!this._built) return;
      for (const it of this.items) this.renderItem(it, this.itemP(it, t));
      const f = this.flashAt(t);
      css(this.svg, 'filter', f.amt > 0.01 ? `drop-shadow(0 0 ${(14 * f.amt).toFixed(1)}px ${rgba(f.color === '#FFFFFF' ? this.color : f.color, 0.9 * f.amt)})` : 'none');
    }
  }

  // ------------------------------------------------------------------ InkStroke / Sketch
  class InkStroke extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { points: null, d: null, smooth: true, closed: false, wobble: 1, strokes: null });
    geometry() {
      const S = this.scene, p = this.props;
      const toPx = (q) => [q[0] * S.W, q[1] * S.H];
      const one = (def) => {
        if (typeof def === 'string') return pathPts(def, 2);
        let pts = def.map(toPx);
        if (p.closed) pts = pts.concat([pts[0]]);
        return p.smooth && pts.length > 2 ? catmull(pts, 14) : pts;
      };
      const list = p.strokes || [p.d || p.points];
      for (const def of list) {
        if (!def) throw new Error(`InkStroke "${this.id}" needs "points" ([[x,y],...] canvas fractions), "d" (SVG path in design px) or "strokes"`);
        this.addStroke(one(def), { wobble: p.wobble });
      }
    }
  }

  // ------------------------------------------------------------------ InkText
  class InkText extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { text: '', x: 0.5, y: 0.5, size: 44, font: 'hand', bold: false, align: null, valign: null, rotate: null, target: null, side: 'right', gap: 18, speed: 1 });
    get isLazy() { return !!this.props.target; }
    textOpts(t) {
      const S = this.scene, p = this.props;
      let x = p.x * S.W, y = p.y * S.H, align = p.align || 'center', valign = p.valign || 'middle';
      if (p.target) {
        const b = resolveRef(S, pickRef(p), t).box, g = p.gap;
        if (p.side === 'left') { x = b.x - g; y = b.cy; align = p.align || 'right'; }
        else if (p.side === 'top') { x = b.cx; y = b.y - g; valign = 'bottom'; }
        else if (p.side === 'bottom') { x = b.cx; y = b.b + g; valign = 'top'; }
        else if (p.side === 'center') { x = b.cx; y = b.cy; }
        else { x = b.r + g; y = b.cy; align = p.align || 'left'; }
        x += p.dx || 0; y += p.dy || 0;
      }
      const rot = p.rotate != null ? p.rotate : (rnd(this.seed, 9) * 2 - 1) * 1.6;
      return { x, y, align, valign, size: p.size, font: p.font, bold: p.bold, rotate: rot, speed: p.speed };
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      return regionOf(this.texts[0].box, r && r.region);
    }
    geometry(t) { this.addText(this.props.text, this.textOpts(t)); }
  }

  // Title (scene.title): large bold handwriting at the top with a yellow underline
  class Title extends InkText {
    static defaults = Object.assign({}, InkText.defaults, { size: 64, bold: true, underline: true, underlineColor: null, y: null });
    static autoEnterAt = 0.05;
    geometry(t) {
      const S = this.scene, p = this.props;
      const o = this.textOpts(t);
      if (p.y == null) o.y = S.portrait ? S.H * 0.075 : S.H * 0.095;
      o.rotate = p.rotate ?? -0.8;
      const it = this.addText(p.text, o);
      if (p.underline) {
        const b = it.ht.box, y = b.b + 2;
        this.addStroke(bowLine([b.x + b.w * 0.04, y + 3], [b.r - b.w * 0.02, y - 2], this.seed, 0.02), { color: S.resolveColor(p.underlineColor) || INK.yellow, width: 4.5, pause: 0 });
      }
    }
  }

  // ------------------------------------------------------------------ Icon (sketched)
  class Icon extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { icon: 'server', x: 0.5, y: 0.5, size: 150, accent: null, label: '', labelSize: 34, labelColor: null, labelSide: 'bottom' });
    static maxDur = 2.2;
    defaultColor() { return /dollar|money|coin/.test(this.props.icon) ? INK.green : INK.white; }
    geometry() {
      const S = this.scene, p = this.props;
      const ops = (window.NT_ICONS || {})[p.icon];
      if (!ops) throw new Error(`Icon "${this.id}": unknown icon "${p.icon}". Known: ${Object.keys(window.NT_ICONS || {}).join(', ')}`);
      const sz = p.size, ox = p.x * S.W - sz / 2, oy = p.y * S.H - sz / 2, k = sz / 100;
      const X = (u) => ox + u * k, Y = (v) => oy + v * k;
      const bw = clamp(3.2 * Math.sqrt(sz / 150) * (p.width / 4), 2.6, 5.5);
      const accent = S.resolveColor(p.accent) || this.color;
      ops.forEach((op, i) => {
        const opt = (typeof op[op.length - 1] === 'object' && !Array.isArray(op[op.length - 1])) ? op[op.length - 1] : {};
        const col = opt.c === 'accent' ? accent : this.color;
        const w = bw * (opt.w || 1);
        const sd = this.seed + i * 31;
        const kind = op[0];
        if (kind === 'line') this.addStroke(bowLine([X(op[1]), Y(op[2])], [X(op[3]), Y(op[4])], sd, 0.03), { color: col, width: w, pause: 0.02 });
        else if (kind === 'circle' || kind === 'ellipse') {
          const full = kind === 'circle' || op[5] == null || typeof op[5] === 'object';
          const rx = op[3] * k, ry = (kind === 'circle' ? op[3] : op[4]) * k;
          const a0 = full ? -Math.PI * (0.55 + 0.3 * rnd(sd, 1)) : (op[5] * Math.PI) / 180;
          const a1 = full ? a0 + Math.PI * 2 * 1.06 : (op[6] * Math.PI) / 180;
          this.addStroke(ellipsePts(X(op[1]), Y(op[2]), rx, ry, a0, a1), { color: col, width: w, pause: 0.03, wobble: 0.5 });
        } else if (kind === 'rect') this.addStroke(rectPts(X(op[1]), Y(op[2]), op[3] * k, op[4] * k, (op[5] || 0) * k, 4), { color: col, width: w, pause: 0.03, wobble: 0.6 });
        else if (kind === 'poly') { const pts = op[1].map((q) => [X(q[0]), Y(q[1])]); if (op[2] === true) pts.push(pts[0]); this.addStroke(pts, { color: col, width: w, wobble: 0.6 }); }
        else if (kind === 'path') {
          const pts = pathPts(op[1], 1).map((q) => [X(q[0]), Y(q[1])]);
          this.addStroke(pts, { color: col, width: w, wobble: 0.6 });
        } else if (kind === 'dot') this.addDot(X(op[1]), Y(op[2]), op[3] * k, col);
        else if (kind === 'text') this.addText(op[3], { x: X(op[1]), y: Y(op[2]), size: op[4] * k, color: col, bold: true, glow: 0.6 });
      });
      this.iconBox = CA.box(p.x * S.W, p.y * S.H, sz, sz);
      if (p.label) {
        const side = p.labelSide, g = 12;
        const o = { size: p.labelSize, color: S.resolveColor(p.labelColor) || INK.white, rotate: (rnd(this.seed, 3) * 2 - 1) * 1.2 };
        if (side === 'top') Object.assign(o, { x: this.iconBox.cx, y: this.iconBox.y - g, valign: 'bottom' });
        else if (side === 'left') Object.assign(o, { x: this.iconBox.x - g - 6, y: this.iconBox.cy, align: 'right' });
        else if (side === 'right') Object.assign(o, { x: this.iconBox.r + g + 6, y: this.iconBox.cy, align: 'left' });
        else Object.assign(o, { x: this.iconBox.cx, y: this.iconBox.b + g, valign: 'top' });
        this.labelIt = this.addText(p.label, o);
      }
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      if (r && r.part === 'label' && this.labelIt) return this.labelIt.ht.box;
      if (r && r.part === 'all') return this.geomBox;
      return regionOf(this.iconBox, r && r.region);
    }
  }

  // ------------------------------------------------------------------ Loop (circle-around)
  class Loop extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { pad: 12, turns: 1.1, shape: 'ellipse' });
    defaultColor() { return INK.purple; }
    geometry(t) {
      const S = this.scene, p = this.props;
      const b = resolveRef(S, Object.assign(pickRef(p), { pad: 0 }), t).box;
      const sd = this.seed;
      if (p.shape === 'box' || p.shape === 'rect') {
        const pb = padBox(b, p.pad + 4);
        this.addStroke(rectPts(pb.x, pb.y, pb.w, pb.h, Math.min(22, pb.h / 3), 18), { wobble: 1.2 });
        return;
      }
      const rx = (b.w / 2) * 1.2 + p.pad + 6, ry = (b.h / 2) * 1.28 + p.pad + 4;
      const a0 = -Math.PI * (0.62 + 0.12 * rnd(sd, 1));
      const turns = p.turns;
      const rot = ((rnd(sd, 2) * 2 - 1) * 3 * Math.PI) / 180;
      const n = Math.ceil((turns * Math.PI * 2 * Math.max(rx, ry)) / 3);
      const pts = [];
      for (let i = 0; i <= n; i++) {
        const f = i / n, a = a0 + f * turns * Math.PI * 2;
        const k = 1 + 0.035 * vnoise(sd + 4, a * 1.4) + 0.055 * f - 0.02;
        const x = Math.cos(a) * rx * k, y = Math.sin(a) * ry * k;
        pts.push([b.cx + x * Math.cos(rot) - y * Math.sin(rot), b.cy + x * Math.sin(rot) + y * Math.cos(rot)]);
      }
      this.addStroke(pts, { wobble: 0.6 });
    }
  }

  // ------------------------------------------------------------------ Underline
  class Underline extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { style: 'single', offset: 8, extend: 0.05 });
    defaultColor() { return INK.purple; }
    geometry(t) {
      const S = this.scene, p = this.props;
      const b = resolveRef(S, pickRef(p), t).box;
      const ext = Math.max(6, b.w * p.extend);
      const slope = (rnd(this.seed, 1) * 2 - 1) * Math.min(6, b.w * 0.012);
      const y = b.b + p.offset;
      const a = [b.x - ext, y + slope], c = [b.r + ext * 1.3, y - slope];
      if (p.style === 'wavy') {
        const pts = [], n = Math.ceil(dist(a, c) / 3);
        for (let i = 0; i <= n; i++) { const f = i / n; pts.push([lerp(a[0], c[0], f), lerp(a[1], c[1], f) + Math.sin(f * dist(a, c) / 13) * 4.5]); }
        this.addStroke(pts, { wobble: 0.4 });
      } else {
        this.addStroke(bowLine(a, c, this.seed, 0.012));
        if (p.style === 'double') this.addStroke(bowLine([a[0] + ext * 0.8, a[1] + 10], [c[0] - ext * 0.6, c[1] + 9], this.seed + 1, 0.015), { width: p.width * 0.85 });
      }
    }
  }

  // ------------------------------------------------------------------ Bracket
  class Bracket extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { side: 'left', kind: 'category', style: 'curly', depth: 28, gap: 16, label: '', labelSize: 36, labelColor: null, overhang: 4 });
    defaultColor() { return this.props.kind === 'tradeoff' ? INK.purple : (this.props.kind === 'tradeoff-b' ? INK.blue : INK.yellow); }
    geometry(t) {
      const S = this.scene, p = this.props;
      const b = resolveRef(S, pickRef(p), t).box;
      const side = p.side, d = p.depth, g = p.gap, oh = p.overhang;
      const vertical = side === 'left' || side === 'right';
      const len = (vertical ? b.h : b.w) + 2 * oh;
      const q = Math.min(d * 0.9, len / 4);
      // local brace along +v (0..len), tip pointing to -u at depth d
      let loc;
      if (p.style === 'square') loc = [[0, 0], [-d * 0.6, 0], [-d * 0.6, len], [0, len]];
      else {
        const h = len, m = h / 2, u = -d * 0.5;
        const dd = `M0,0 C${-d * 0.45},0 ${u},${q * 0.15} ${u},${q} L${u},${m - q} C${u},${m - q * 0.2} ${-d * 0.75},${m} ${-d},${m} C${-d * 0.75},${m} ${u},${m + q * 0.2} ${u},${m + q} L${u},${h - q} C${u},${h - q * 0.15} ${-d * 0.45},${h} 0,${h}`;
        loc = pathPts(dd, 2);
      }
      let map, tip;
      if (side === 'left') { const x0 = b.x - g, y0 = b.y - oh; map = (q2) => [x0 + q2[0], y0 + q2[1]]; tip = [x0 - d, b.cy]; }
      else if (side === 'right') { const x0 = b.r + g, y0 = b.y - oh; map = (q2) => [x0 - q2[0], y0 + q2[1]]; tip = [x0 + d, b.cy]; }
      else if (side === 'top') { const y0 = b.y - g, x0 = b.x - oh; map = (q2) => [x0 + q2[1], y0 + q2[0]]; tip = [b.cx, y0 - d]; }
      else { const y0 = b.b + g, x0 = b.x - oh; map = (q2) => [x0 + q2[1], y0 - q2[0]]; tip = [b.cx, y0 + d]; }
      if (p.style === 'square') this.addStroke(loc.map(map), { wobble: 0.5 });
      else this.addStroke(loc.map(map), { wobble: 0.5 });
      if (p.label) {
        const o = { size: p.labelSize, color: S.resolveColor(p.labelColor) || this.color, rotate: (rnd(this.seed, 4) * 2 - 1) * 1.5, bold: true };
        const lg = 14;
        if (side === 'left') Object.assign(o, { x: tip[0] - lg, y: tip[1], align: 'right' });
        else if (side === 'right') Object.assign(o, { x: tip[0] + lg, y: tip[1], align: 'left' });
        else if (side === 'top') Object.assign(o, { x: tip[0], y: tip[1] - lg + 4, valign: 'bottom' });
        else Object.assign(o, { x: tip[0], y: tip[1] + lg - 4, valign: 'top' });
        this.addText(p.label, o);
      }
    }
  }

  // ------------------------------------------------------------------ CrossOut
  class CrossOut extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { style: 'x', pad: 6, width: 5 });
    defaultColor() { return INK.red; }
    geometry(t) {
      const S = this.scene, p = this.props;
      const b = padBox(resolveRef(S, pickRef(p), t).box, p.pad);
      if (p.style === 'strike' || p.style === 'double') {
        const y = b.cy + b.h * 0.04;
        this.addStroke(bowLine([b.x - 6, y + b.h * 0.12], [b.r + 8, y - b.h * 0.1], this.seed, 0.01));
        if (p.style === 'double') this.addStroke(bowLine([b.x, y + b.h * 0.28], [b.r + 4, y + b.h * 0.08], this.seed + 1, 0.01));
      } else if (p.style === 'scribble') {
        const pts = [], n = Math.max(4, Math.round(b.w / 26));
        for (let i = 0; i <= n; i++) { const x = b.x + (b.w * i) / n; pts.push([x, i % 2 ? b.y + b.h * 0.2 : b.b - b.h * 0.2]); }
        this.addStroke(catmull(pts, 6), { wobble: 0.6 });
      } else {
        this.addStroke(bowLine([b.x, b.y], [b.r, b.b], this.seed, 0.03), { pause: 0.06 });
        this.addStroke(bowLine([b.r + 2, b.y + 3], [b.x - 2, b.b - 2], this.seed + 1, 0.03));
      }
    }
  }

  // ------------------------------------------------------------------ HatchZone (red diagonal hatch fill)
  class HatchZone extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { spacing: 18, angle: 45, outline: true, label: '', labelSize: 34, labelSide: 'top', fill: 0.07, width: 3.5, hatchWidth: 2.4, pad: 0 });
    defaultColor() { return INK.red; }
    geometry(t) {
      const S = this.scene, p = this.props;
      const b = padBox(resolveRef(S, pickRef(p), t).box, p.pad);
      this.zoneBox = b;
      const col = this.color;
      const fill = svgEl('rect', { x: f1(b.x), y: f1(b.y), width: f1(b.w), height: f1(b.h), rx: 6, fill: col, opacity: 0 }, this.under);
      if (p.outline) this.addStroke(rectPts(b.x, b.y, b.w, b.h, 8, 14), { wobble: 0.9, pause: 0.02 });
      this.addFade(fill, { max: p.fill, weight: 0.05, box: b });
      const ang = (p.angle * Math.PI) / 180, dx = Math.cos(ang), dy = -Math.sin(ang); // hatch direction
      const nx = -dy, ny = dx; // normal
      const proj = (x, y) => x * nx + y * ny;
      const cs = [proj(b.x, b.y), proj(b.r, b.y), proj(b.x, b.b), proj(b.r, b.b)];
      const c0 = Math.min(...cs), c1 = Math.max(...cs);
      const inset = 5;
      const ib = padBox(b, -inset);
      let i = 0;
      for (let c = c0 + p.spacing * 0.5; c < c1; c += p.spacing, i++) {
        // intersect line {x*nx + y*ny = c} with box ib
        const hits = [];
        const tryX = (x) => { if (Math.abs(ny) < 1e-6) return; const y = (c - x * nx) / ny; if (y >= ib.y - 0.01 && y <= ib.b + 0.01) hits.push([x, y]); };
        const tryY = (y) => { if (Math.abs(nx) < 1e-6) return; const x = (c - y * ny) / nx; if (x >= ib.x - 0.01 && x <= ib.r + 0.01) hits.push([x, y]); };
        tryX(ib.x); tryX(ib.r); tryY(ib.y); tryY(ib.b);
        if (hits.length < 2) continue;
        hits.sort((a2, b2) => a2[0] - b2[0]);
        const a = hits[0], e = hits[hits.length - 1];
        if (dist(a, e) < 6) continue;
        const j = (rnd(this.seed, i) - 0.5) * 4;
        this.addStroke(bowLine([a[0] + j, a[1]], [e[0], e[1] + j], this.seed + i, 0.02), { width: p.hatchWidth, pause: 0.0, speed: 2.6, wobble: 0.4 });
      }
      if (p.label) {
        const o = { size: p.labelSize, color: col, bold: true, rotate: (rnd(this.seed, 8) * 2 - 1) * 1.5 };
        if (p.labelSide === 'bottom') Object.assign(o, { x: b.cx, y: b.b + 10, valign: 'top' });
        else if (p.labelSide === 'center') Object.assign(o, { x: b.cx, y: b.cy });
        else Object.assign(o, { x: b.cx, y: b.y - 10, valign: 'bottom' });
        this.labelIt = this.addText(p.label, o);
      }
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      if (r && r.part === 'label' && this.labelIt) return this.labelIt.ht.box;
      return regionOf(this.zoneBox, r && r.region);
    }
  }

  // ------------------------------------------------------------------ Arrow (hand-drawn connector)
  class Arrow extends InkPrim {
    static lazy = true;
    static defaults = Object.assign({}, InkPrim.defaults, { from: null, to: null, fromSide: null, toSide: null, bend: 0.18, head: 22, gap: 14, fromGap: null, label: '', labelSize: 32, labelColor: null, double: false });
    defaultColor() { return INK.yellow; }
    geometry(t) {
      const S = this.scene, p = this.props;
      const A = resolveRef(S, p.from, t).box, B = resolveRef(S, p.to, t).box;
      const ac = [A.cx, A.cy], bc = [B.cx, B.cy];
      const fg = p.fromGap ?? p.gap;
      // aim through the curve's control point so the ends leave the boxes in the right direction
      const mid0 = [(ac[0] + bc[0]) / 2, (ac[1] + bc[1]) / 2];
      const L0 = dist(ac, bc) || 1;
      const nx = -(bc[1] - ac[1]) / L0, ny = (bc[0] - ac[0]) / L0;
      const ctrl0 = [mid0[0] + nx * p.bend * L0, mid0[1] + ny * p.bend * L0];
      const side = (b, sd, g) => { const e = CA.edgePoint(b, sd, 0); const o = { left: [-g, 0], right: [g, 0], top: [0, -g], bottom: [0, g] }[sd]; return [e[0] + o[0], e[1] + o[1]]; };
      const p0 = p.fromSide ? side(A, p.fromSide, fg) : A.w || A.h ? boxExit(A, ctrl0, fg) : ac;
      const p1 = p.toSide ? side(B, p.toSide, p.gap) : B.w || B.h ? boxExit(B, ctrl0, p.gap) : bc;
      const L = dist(p0, p1) || 1;
      const mid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
      const n2x = -(p1[1] - p0[1]) / L, n2y = (p1[0] - p0[0]) / L;
      const ctrl = [mid[0] + n2x * p.bend * L, mid[1] + n2y * p.bend * L];
      const pts = quadPts(p0, ctrl, p1, Math.max(8, Math.ceil(L / 4)));
      const shaft = this.addStroke(pts, { pause: 0.03 });
      const P = shaft.s.P, n = P.length;
      const head = (tip, prev) => {
        const ang = Math.atan2(tip[1] - prev[1], tip[0] - prev[0]);
        const h = p.head, sp = 0.48;
        const b1 = [tip[0] - Math.cos(ang - sp) * h, tip[1] - Math.sin(ang - sp) * h];
        const b2 = [tip[0] - Math.cos(ang + sp) * h * 1.05, tip[1] - Math.sin(ang + sp) * h * 1.05];
        this.addStroke(bowLine(b1, tip, this.seed + 3, 0.04), { pause: 0.0, wobble: 0.3 });
        this.addStroke(bowLine(tip, b2, this.seed + 4, 0.04), { pause: 0.0, wobble: 0.3 });
      };
      head(P[n - 1], P[Math.max(0, n - 7)]);
      if (p.double) head(P[0], P[Math.min(n - 1, 6)]);
      if (p.label) {
        const q = quadPts(p0, ctrl, p1, 2)[1];
        const side = n2x * (ctrl[0] - mid[0]) + n2y * (ctrl[1] - mid[1]) >= 0 ? 1 : -1;
        const off = 28 * side;
        this.addText(p.label, { x: q[0] + n2x * off, y: q[1] + n2y * off, size: p.labelSize, color: S.resolveColor(p.labelColor) || this.color, rotate: (rnd(this.seed, 6) * 2 - 1) * 2 });
      }
    }
  }

  // ------------------------------------------------------------------ Panel (hand-drawn frame)
  class Panel extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { box: [0.1, 0.15, 0.35, 0.6], radius: 18, title: '', titleSize: 34, titleColor: null, width: 3.4, dashed: false });
    geometry() {
      const S = this.scene, p = this.props;
      const r = p.box;
      const b = CA.box((r[0] + r[2] / 2) * S.W, (r[1] + r[3] / 2) * S.H, r[2] * S.W, r[3] * S.H);
      this.panelBox = b;
      this.addStroke(rectPts(b.x, b.y, b.w, b.h, p.radius, 16), { wobble: 1 });
      if (p.title) this.addText(p.title, { x: b.x + 22, y: b.y + 16, align: 'left', valign: 'top', size: p.titleSize, bold: true, color: S.resolveColor(p.titleColor) || this.color, rotate: -0.8 });
    }
    refBox(r, t) { this.ensure(t ?? 0); return regionOf(this.panelBox, r && r.region); }
  }

  // ------------------------------------------------------------------ RedPointer (bold solid arrow)
  class RedPointer extends InkPrim {
    static layer = 'text';
    static lazy = true;
    static autoEnter = false;
    static defaults = Object.assign({}, InkPrim.defaults, { from: 'auto', length: 150, hold: 1.2, size: 1, gap: 6, label: '', labelSize: 32, labelColor: null });
    static actions = { point: { dur: 0.28, ease: 'outBack' }, enter: { dur: 0.28, ease: 'outBack' }, exit: { dur: 0.25 }, dim: { dur: 0.4 }, undim: { dur: 0.4 } };
    defaultColor() { return INK.red; }
    build2() {
      this.wins = [];
      const k = this.props.size, Lr = this.props.length * k;
      const hl = 52 * k, hw = 31 * k, sw = 10.5 * k;
      const d = `M0,0 L${-hl},${-hw} L${-hl + 9 * k},${-sw} L${-Lr},${-sw * 0.78} Q${-Lr - 9 * k},0 ${-Lr},${sw * 0.78} L${-hl + 9 * k},${sw} L${-hl},${hw} Z`;
      this.arrow = svgEl('path', { d, fill: this.color, 'stroke-linejoin': 'round', stroke: this.color, 'stroke-width': 2 }, this.g);
      css(this.g, 'filter', `drop-shadow(0 0 12px ${rgba(this.color, 0.55)}) drop-shadow(0 5px 10px rgba(0,0,0,0.65))`);
      attr(this.arrow, 'visibility', 'hidden');
    }
    finishGeometry() { this.geomBox = CA.box(0, 0, 0, 0); this.totalWeight = 0.3; }
    ensure() { this._built = true; }
    a_enter(at, dur, e, args) { this.a_point(at, dur, e, args); }
    a_point(at, dur, e, args = {}) {
      const ref = Object.keys(pickRef(args)).length ? pickRef(args) : pickRef(this.props);
      const hold = clamp(args.hold ?? this.props.hold, 0.8, 1.5);
      const from = args.from ?? this.props.from;
      this.wins.push({ at, dur: Math.max(0.12, dur), hold, ref, from, out: 0.26 });
      this.vis.to(at, 1, 0);
      this.vis.to(at + dur + hold + 0.26, 0, 0);
      if (this.props.label && !this.labelHt) {
        this.labelHt = new HandText(this.root, this.props.label, { x: 0, y: 0, size: this.props.labelSize, color: this.scene.resolveColor(this.props.labelColor) || INK.white, bold: true, glow: 0.8 });
        this.labelHt.render(1);
      }
    }
    a_exit(at, dur) { for (const w of this.wins) if (w.at <= at && at < w.at + w.dur + w.hold) w.hold = Math.max(0, at - w.at - w.dur); this.vis.to(at + dur, 0, 0); }
    dirFor(target, from) {
      const S = this.scene;
      const named = { left: 180, right: 0, top: -90, bottom: 90, 'top-left': -135, 'top-right': -45, 'bottom-left': 135, 'bottom-right': 45 };
      let deg;
      if (typeof from === 'number') deg = from;
      else if (named[from] != null) deg = named[from];
      else {
        const vx = S.W * 0.5 - target[0], vy = S.H * 0.55 - target[1];
        deg = (Math.atan2(vy, vx) * 180) / Math.PI;
        deg = Math.round(deg / 45) * 45;
        if (Math.abs(vx) < S.W * 0.08 && Math.abs(vy) < S.H * 0.08) deg = 135;
      }
      return (deg * Math.PI) / 180; // direction from target toward the tail
    }
    render(t) {
      super.render(t);
      let w = null;
      for (const x of this.wins) if (t >= x.at && t <= x.at + x.dur + x.hold + x.out) w = x;
      if (!w) { attr(this.arrow, 'visibility', 'hidden'); if (this.labelHt) css(this.labelHt.el, 'opacity', '0'); return; }
      const { box: b } = resolveRef(this.scene, w.ref, t);
      const a = this.dirFor([b.cx, b.cy], w.from);
      const far = [b.cx + Math.cos(a) * 4000, b.cy + Math.sin(a) * 4000];
      const tip = b.w || b.h ? boxExit(b, far, this.props.gap) : [b.cx + Math.cos(a) * this.props.gap, b.cy + Math.sin(a) * this.props.gap];
      const pin = getEase('outBack')(clamp((t - w.at) / w.dur));
      const tEnd = w.at + w.dur + w.hold;
      const pout = clamp((t - tEnd) / w.out);
      const poke = 7 * bump(t, w.at + w.dur + 0.05, 0.3) + 4 * bump(t, w.at + w.dur + 0.38, 0.26);
      const back = (1 - pin) * 70 + ease.in(pout) * 46 + poke;
      const sc = 0.82 + 0.18 * clamp(pin, 0, 1.2);
      const op = clamp(pin * 3) * (1 - pout);
      const rot = a + Math.PI; // arrow points from the tail to the target (+x local)
      const x = tip[0] + Math.cos(a) * back, y = tip[1] + Math.sin(a) * back;
      attr(this.arrow, 'visibility', op > 0.002 ? 'visible' : 'hidden');
      attr(this.arrow, 'transform', `translate(${f1(x)},${f1(y)}) rotate(${((rot * 180) / Math.PI).toFixed(2)}) scale(${sc.toFixed(3)})`);
      attr(this.arrow, 'opacity', op.toFixed(3));
      if (this.labelHt) {
        const L = this.props.length * this.props.size + 16;
        const lx = x + Math.cos(a) * L, ly = y + Math.sin(a) * L;
        const hx = Math.cos(a) > 0.3 ? 'left' : Math.cos(a) < -0.3 ? 'right' : 'center';
        const hb = this.labelHt;
        const ox = hx === 'left' ? 0 : hx === 'right' ? -hb.w : -hb.w / 2;
        const oy = Math.sin(a) > 0.3 ? 0 : Math.sin(a) < -0.3 ? -hb.h : -hb.h / 2;
        css(hb.el, 'left', f1(lx + ox) + 'px'); css(hb.el, 'top', f1(ly + oy) + 'px');
        css(hb.el, 'opacity', op.toFixed(3));
      }
    }
  }

  // ------------------------------------------------------------------ Metric (counter, gains, struck old price)
  class Metric extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { value: '0', label: '', x: 0.5, y: 0.5, size: 120, tone: null, color: null, labelSize: 34, align: 'center', strikeSide: 'right' });
    static actions = Object.assign({}, InkPrim.actions, { set: { dur: 1.0, ease: 'smooth' }, strike: { dur: 0.9, ease: 'inOut' } });
    defaultColor() { const t = this.props.tone; return t === 'gain' || t === 'up' ? INK.green : t === 'loss' || t === 'down' ? INK.red : INK.white; }
    geometry() {
      const S = this.scene, p = this.props;
      this.valIt = this.addText(String(p.value), { x: p.x * S.W, y: p.y * S.H, size: p.size, bold: true, align: p.align, rotate: (rnd(this.seed, 2) * 2 - 1) * 1.2, glow: 1.3 });
      const vb = this.valIt.ht.box;
      if (p.label) this.labelIt = this.addText(p.label, { x: vb.cx, y: vb.b - p.size * 0.06, valign: 'top', size: p.labelSize, color: '#D4D4D8', glow: 0.4 });
      this.values = [{ at: -1, value: String(p.value), dur: 0, color: this.color }];
    }
    a_set(at, dur, e, args) {
      this.ensure(at);
      const col = args.tone ? (args.tone === 'gain' || args.tone === 'up' ? INK.green : args.tone === 'loss' || args.tone === 'down' ? INK.red : INK.white) : (this.scene.resolveColor(args.color) || null);
      this.values.push({ at, value: String(args.value), dur, color: col || this.values[this.values.length - 1].color });
      this.flash(at + dur * 0.9, 0.6, col || this.color);
    }
    a_strike(at, dur, e, args) {
      this.ensure(at);
      const S = this.scene, p = this.props;
      const vb = this.valIt.ht.box;
      const sb = CA.box(vb.cx, vb.cy + vb.h * 0.05, vb.w * 0.92, vb.h * 0.5);
      const strike = this.addStroke(bowLine([sb.x - 8, sb.b], [sb.r + 10, sb.y], this.seed + 77, 0.02), { color: INK.red, width: Math.max(5, p.size * 0.05) });
      strike.f0 = 0; strike.f1 = 1; strike.own = { at, dur: dur * 0.4 };
      const to = args.to ?? args.value;
      if (to != null) {
        const side = args.side || p.strikeSide;
        const gap = p.size * 0.35;
        const o = { size: (args.size ?? p.size), bold: true, color: args.tone === 'loss' ? INK.red : (S.resolveColor(args.color) || INK.green), rotate: (rnd(this.seed, 5) * 2 - 1) * 1.5, glow: 1.3 };
        if (side === 'below') Object.assign(o, { x: vb.cx, y: vb.b + gap * 0.2, valign: 'top' });
        else if (side === 'left') Object.assign(o, { x: vb.x - gap, y: vb.cy, align: 'right' });
        else Object.assign(o, { x: vb.r + gap, y: vb.cy, align: 'left' });
        const nt = (this.newIt = this.addText(String(to), o));
        nt.f0 = 0; nt.f1 = 1; nt.own = { at: at + dur * 0.42, dur: dur * 0.58 };
        if (this.labelIt && side === 'below') this.labelHide = at + dur * 0.3;
      }
      this.dimOld = { at: at + dur * 0.3, dur: 0.4 };
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      if (r && r.part === 'label' && this.labelIt) return this.labelIt.ht.box;
      if (r && r.part === 'new' && this.newIt) return this.newIt.ht.box;
      return regionOf(this.valIt.ht.box, r && r.region);
    }
    itemP(it, t) { if (it.own) return clamp((t - it.own.at) / it.own.dur); return super.itemP(it, t); }
    render(t) {
      super.render(t);
      if (!this._built) return;
      // counter
      let i = 0;
      for (let k = 0; k < this.values.length; k++) if (this.values[k].at <= t) i = k;
      const v = this.values[i], prev = this.values[Math.max(0, i - 1)];
      const pp = v.dur > 0 ? clamp((t - v.at) / v.dur) : 1;
      let str = v.value;
      if (i > 0 && pp < 1) {
        const a = parseNumber(prev.value), b = parseNumber(v.value);
        if (a && b) str = formatNumber(lerp(a.num, b.num, ease.smooth(pp)), { decimals: b.decimals, prefix: b.prefix, suffix: b.suffix, sep: b.sep || a.sep });
        else str = pp < 0.5 ? prev.value : v.value;
      }
      const ht = this.valIt.ht;
      if (i > 0 && ht.str !== str) ht.setText(str, false);
      const col = i > 0 ? mixColor(prev.color, v.color, clamp(pp * 1.5)) : v.color;
      css(ht.el, 'color', col);
      css(ht.el, 'textShadow', textGlow(col, 1.3));
      if (this.dimOld) css(ht.el, 'opacity', (1 - 0.45 * prog(t, this.dimOld.at, this.dimOld.dur, 'smooth')).toFixed(3));
      if (this.labelHide != null) css(this.labelIt.ht.el, 'opacity', (1 - prog(t, this.labelHide, 0.3, 'smooth')).toFixed(3));
    }
  }

  // ------------------------------------------------------------------ BarChart (hand-drawn)
  function fmtVal(v, p) { return formatNumber(v, { decimals: p.decimals ?? 0, prefix: p.prefix || '', suffix: p.suffix || '', sep: p.sep ?? ',' }); }
  function boxFromFrac(S, r) { return CA.box((r[0] + r[2] / 2) * S.W, (r[1] + r[3] / 2) * S.H, r[2] * S.W, r[3] * S.H); }

  class BarChart extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { box: [0.12, 0.2, 0.76, 0.66], bars: [], max: null, prefix: '', suffix: '', decimals: 0, title: '', titleSize: 40, labelSize: 30, valueSize: 32, values: true, fill: 0.16, axisColor: null });
    static actions = Object.assign({}, InkPrim.actions, { set: { dur: 0.9, ease: 'smooth' } });
    static maxDur = 3.2;
    geometry() {
      const S = this.scene, p = this.props;
      const B = boxFromFrac(S, p.box);
      this.B = B;
      const top = B.y + (p.title ? p.titleSize * 1.5 : 0) + (p.values ? p.valueSize * 1.4 : 10);
      const base = B.b - p.labelSize * 1.6;
      this.plot = { x: B.x, r: B.r, top, base };
      const n = Math.max(1, p.bars.length);
      const vmax = p.max ?? Math.max(...p.bars.map((b) => +b.value || 0), ...(this.scene.spec.beats || []).filter((b) => b.target === this.id && b.action === 'set').map((b) => +b.args.value || 0)) * 1.05;
      this.vmax = vmax || 1;
      const axisCol = S.resolveColor(p.axisColor) || INK.white;
      if (p.title) this.addText(p.title, { x: B.x, y: B.y, align: 'left', valign: 'top', size: p.titleSize, bold: true, rotate: -0.8 });
      this.addStroke(bowLine([B.x + 4, top - 12], [B.x, base + 2], this.seed + 1, 0.01), { color: axisCol, width: 3.4, pause: 0.02 });
      this.addStroke(bowLine([B.x - 6, base], [B.r + 4, base + 1], this.seed + 2, 0.008), { color: axisCol, width: 3.4, pause: 0.08 });
      const slot = (B.r - B.x - 20) / n;
      const bw = Math.min(slot * 0.56, 170);
      this.bars = p.bars.map((bar, i) => {
        const cx = B.x + 20 + slot * (i + 0.5);
        const col = S.resolveColor(bar.color) || (bar.tone === 'gain' ? INK.green : bar.tone === 'loss' ? INK.red : INK.white);
        const h0 = this.hFor(+bar.value || 0);
        const fill = svgEl('rect', { fill: col, opacity: 0, x: f1(cx - bw / 2), width: f1(bw), y: f1(base - h0), height: f1(h0), rx: 3 }, this.under);
        const it = this.addStroke(this.barPts(cx, bw, h0), { color: col, width: 3.8, pause: 0.02 });
        const fillIt = null;
        const lab = bar.label != null ? this.addText(String(bar.label), { x: cx, y: base + 12, valign: 'top', size: p.labelSize, color: '#E4E4E7', glow: 0.4, pause: 0.02 }) : null;
        const vl = p.values ? this.addText(bar.display ?? fmtVal(+bar.value, p), { x: cx, y: base - h0 - 10, valign: 'bottom', size: p.valueSize, color: col, bold: true, pause: 0.1 }) : null;
        return { i, cx, bw, col, it, fill, fillIt, lab, vl, h: h0, hT: new Track(+bar.value || 0), value: +bar.value || 0, display: bar.display };
      });
    }
    hFor(v) { return (clamp(v / this.vmax, 0, 1.2)) * (this.plot.base - this.plot.top); }
    barPts(cx, bw, h) {
      const base = this.plot.base, x0 = cx - bw / 2, x1 = cx + bw / 2;
      return [[x0, base], [x0, base - h], [x1, base - h], [x1, base]].reduce((acc, q, i, arr) => (i ? acc.concat(bowLine(arr[i - 1], q, this.seed + i, 0.01).slice(1)) : [q]), []);
    }
    a_set(at, dur, e, args) {
      this.ensure(at);
      const b = this.barIndex(args.bar);
      this.bars[b].hT.to(at, +args.value, dur, e);
      if (args.color || args.tone) this.bars[b].newCol = { at, col: this.scene.resolveColor(args.color) || (args.tone === 'gain' ? INK.green : args.tone === 'loss' ? INK.red : INK.white) };
    }
    barIndex(r) {
      if (typeof r === 'number') return clamp(r, 0, this.bars.length - 1);
      const i = this.props.bars.findIndex((b) => String(b.label).toLowerCase() === String(r).toLowerCase());
      if (i < 0) throw new Error(`BarChart "${this.id}": no bar "${r}"`);
      return i;
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      if (r && r.bar != null) {
        const b = this.bars[this.barIndex(r.bar)];
        const h = this.hFor(b.hT.value(t ?? 0));
        if (r.part === 'value' && b.vl) return CA.box(b.cx, this.plot.base - h - 10 - b.vl.ht.h / 2, b.vl.ht.w, b.vl.ht.h);
        if (r.part === 'label' && b.lab) return b.lab.ht.box;
        return regionOf(CA.box(b.cx, this.plot.base - h / 2, b.bw, h), r.region);
      }
      return regionOf(this.B, r && r.region);
    }
    render(t) {
      super.render(t);
      if (!this._built) return;
      for (const b of this.bars) {
        const v = b.hT.value(t);
        const p = this.itemP(b.it, t);
        if (Math.abs(v - b.value) > 1e-6) {
          b.value = v;
          const h = this.hFor(v);
          b.it.s = new Stroke(handPts(this.barPts(b.cx, b.bw, h), this.seed + b.i * 5, 0.5), { width: 3.8, seed: this.seed + b.i });
          b.it._p = -1;
          attr(b.fill, 'y', f1(this.plot.base - h)); attr(b.fill, 'height', f1(h));
          if (b.vl) { b.vl.ht.setText(b.display && v === +this.props.bars[b.i].value ? b.display : fmtVal(v, this.props), false); b.vl.ht.o.y = this.plot.base - h - 10; b.vl.ht.layout(); }
          this.renderItem(b.it, p);
        }
        const fp = ease.inOut(p);
        const h = this.hFor(v);
        attr(b.fill, 'height', f1(h * fp)); attr(b.fill, 'y', f1(this.plot.base - h * fp));
        attr(b.fill, 'opacity', (this.props.fill * clamp(p * 2.5)).toFixed(3));
        if (b.newCol && t >= b.newCol.at) {
          const c = b.newCol.col;
          attr(b.it.el, 'fill', c); attr(b.fill, 'fill', c); if (b.vl) { css(b.vl.ht.el, 'color', c); css(b.vl.ht.el, 'textShadow', textGlow(c)); }
        }
      }
    }
  }

  // ------------------------------------------------------------------ LineChart (hand-drawn)
  class LineChart extends InkPrim {
    static defaults = Object.assign({}, InkPrim.defaults, { box: [0.12, 0.2, 0.76, 0.66], series: [], labels: [], yMin: null, yMax: null, prefix: '', suffix: '', decimals: 0, title: '', titleSize: 40, labelSize: 26, smooth: true, dots: true, yTicks: 3, endLabels: true });
    static maxDur = 3.4;
    geometry() {
      const S = this.scene, p = this.props;
      const B = boxFromFrac(S, p.box);
      this.B = B;
      const all = p.series.flatMap((s) => s.values.map((v) => (Array.isArray(v) ? v[1] : v)));
      const y0 = p.yMin ?? Math.min(0, ...all), y1 = p.yMax ?? Math.max(...all) * 1.08;
      const left = B.x + (p.yTicks ? 70 : 10), top = B.y + (p.title ? p.titleSize * 1.6 : 16), base = B.b - (p.labels.length ? p.labelSize * 1.7 : 10);
      let endW = 0;
      if (p.endLabels) {
        const m = el('div', { class: 'nt-hand bold' }, this.root);
        m.style.fontSize = p.labelSize * 1.15 + 'px';
        for (const sr of p.series) { m.textContent = sr.name || ''; endW = Math.max(endW, m.offsetWidth); }
        m.remove();
      }
      const right = B.r - (p.endLabels ? endW + 30 : 10);
      this.plot = { left, top, base, right };
      const nMax = Math.max(...p.series.map((s) => s.values.length));
      const X = (i, n) => left + 16 + ((right - left - 32) * i) / Math.max(1, n - 1);
      const Y = (v) => base - ((v - y0) / (y1 - y0 || 1)) * (base - top);
      this.X = X; this.Y = Y;
      if (p.title) this.addText(p.title, { x: B.x, y: B.y, align: 'left', valign: 'top', size: p.titleSize, bold: true, rotate: -0.8 });
      this.addStroke(bowLine([left + 3, top - 6], [left, base + 2], this.seed + 1, 0.01), { width: 3.4, pause: 0.02 });
      this.addStroke(bowLine([left - 6, base], [right + 6, base + 1], this.seed + 2, 0.008), { width: 3.4, pause: 0.05 });
      if (p.yTicks) {
        for (let k = 0; k < p.yTicks; k++) {
          const v = y0 + ((y1 - y0) * k) / Math.max(1, p.yTicks - 1);
          this.addText(fmtVal(v, p), { x: left - 14, y: Y(v), align: 'right', size: p.labelSize * 0.9, color: '#A1A1AA', glow: 0, pause: 0, speed: 3 });
        }
      }
      this.xLabels = p.labels.map((lab, i) => this.addText(String(lab), { x: X(i, p.labels.length), y: base + 10, valign: 'top', size: p.labelSize, color: '#D4D4D8', glow: 0.3, pause: 0, speed: 3 }));
      this.series = p.series.map((s, si) => {
        const col = S.resolveColor(s.color) || SERIES[si % SERIES.length];
        const pts = s.values.map((v, i) => (Array.isArray(v) ? [X(v[0], nMax), Y(v[1])] : [X(i, s.values.length), Y(v)]));
        const line = this.addStroke(p.smooth ? catmull(pts, 10) : pts, { color: col, width: s.width ?? 4.5, pause: 0.02, wobble: 0.5 });
        const dots = p.dots ? pts.map((q) => { const c = svgEl('circle', { cx: f1(q[0]), cy: f1(q[1]), r: 0, fill: col }, this.g); return { el: c, q }; }) : [];
        // dot appearance fractions along the drawn line
        const lut = line.s; let k = 0;
        for (const d of dots) { let best = 0, bd = Infinity; for (; k < lut.P.length; k++) { const dd = dist(lut.P[k], d.q); if (dd < bd) { bd = dd; best = k; } else if (dd > bd + 20) break; } d.f = lut.cum[best] / lut.L; k = best; }
        const end = pts[pts.length - 1];
        const lab = p.endLabels && s.name ? this.addText(s.name, { x: end[0] + 16, y: end[1] - 4, align: 'left', size: p.labelSize * 1.15, color: col, bold: true, pause: 0.1 }) : null;
        return { col, pts, line, dots, lab };
      });
    }
    refBox(r, t) {
      this.ensure(t ?? 0);
      if (r && r.part === 'label' && this.xLabels[r.index ?? 0]) return this.xLabels[r.index ?? 0].ht.box;
      if (r && (r.point != null || r.index != null)) {
        const s = this.series[clamp(r.series | 0, 0, this.series.length - 1)];
        const idx = (i) => (i < 0 ? s.pts.length + i : clamp(i, 0, s.pts.length - 1));
        const i = r.index ?? r.point;
        if (Array.isArray(i)) { const b = bbox(s.pts.slice(idx(i[0]), idx(i[1]) + 1)); return CA.box(b.cx, b.cy, Math.max(b.w, 22), Math.max(b.h, 22)); }
        const q = s.pts[idx(i)];
        return CA.box(q[0], q[1], 22, 22);
      }
      if (r && r.series != null) return bbox(this.series[clamp(r.series | 0, 0, this.series.length - 1)].pts);
      if (r && r.region) return regionOf(CA.box((this.plot.left + this.plot.right) / 2, (this.plot.top + this.plot.base) / 2, this.plot.right - this.plot.left, this.plot.base - this.plot.top), r.region);
      return this.B;
    }
    render(t) {
      super.render(t);
      if (!this._built) return;
      for (const s of this.series) {
        const p = penEase(this.itemP(s.line, t));
        for (const d of s.dots) attr(d.el, 'r', (5.5 * ease.outBack(clamp((p - d.f) * 12 + (p >= 0.999 ? 1 : 0)))).toFixed(2));
      }
    }
  }

  // ------------------------------------------------------------------ Screenshot (image with telestration on top)
  class Screenshot extends Primitive {
    static layer = 'nodes';
    static defaults = { src: '', source: '', mode: 'full', box: null, radius: 10 };
    static actions = { enter: { dur: 0.7, ease: 'out' }, exit: { dur: 0.45 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, spotlight: { dur: 0.5, ease: 'smooth' }, unspotlight: { dur: 0.45, ease: 'smooth' }, pulse: { dur: 0.6 } };
    areaBox() {
      const S = this.scene, p = this.props;
      if (p.box) return p.box;
      if (p.mode === 'dock') return S.portrait ? [0.05, 0.6, 0.9, 0.34] : [0.08, 0.5, 0.84, 0.46];
      return S.portrait ? [0.04, 0.22, 0.92, 0.56] : [0.05, 0.06, 0.9, 0.87];
    }
    build() {
      const S = this.scene, p = this.props;
      if (imgErrors.length) throw new Error(imgErrors.join('\n'));
      const im = IMG.get(p.src);
      if (!im) throw new Error(`Screenshot "${this.id}": image "${p.src}" did not load`);
      const r = this.areaBox();
      const A = boxFromFrac(S, r);
      const srcH = p.source ? 30 : 0;
      const iw = im.naturalWidth, ih = im.naturalHeight;
      const k = Math.min(A.w / iw, (A.h - srcH) / ih);
      const w = Math.round(iw * k), h = Math.round(ih * k);
      const x = Math.round(A.cx - w / 2);
      const y = Math.round(p.mode === 'dock' ? A.b - srcH - h : A.y + (A.h - srcH - h) / 2);
      this.IR = CA.box(x + w / 2, y + h / 2, w, h);
      this.A = CA.box(x + w / 2, y + (h + srcH) / 2, w, h + srcH);
      this.root.classList.add('nt-shot');
      Object.assign(this.root.style, { width: w + 'px', height: h + srcH + 'px' });
      this.frame = el('div', { class: 'frame' }, this.root);
      Object.assign(this.frame.style, { left: '0px', top: '0px', width: w + 'px', height: h + 'px', borderRadius: p.radius + 'px' });
      this.frame.appendChild(im);
      this.spot = el('div', { class: 'spot' }, this.frame);
      this.spotT = new Track(0); this.spotR = new Events();
      if (p.source) {
        this.src = el('div', { class: 'source' }, this.root);
        this.src.innerHTML = 'source: <b></b>';
        this.src.querySelector('b').textContent = p.source;
        Object.assign(this.src.style, { right: '2px', top: h + 9 + 'px' });
      }
    }
    measure() { this.w = this.A.w; this.h = this.A.h; return { w: this.w, h: this.h }; }
    layoutSelf() { this.place(this.A.cx, this.A.cy); }
    refBox(r) {
      if (r && r.part === 'source' && this.src) return CA.box(this.A.r - this.src.offsetWidth / 2, this.IR.b + 9 + this.src.offsetHeight / 2, this.src.offsetWidth, this.src.offsetHeight);
      return regionOf(this.IR, r && r.region);
    }
    get linkBox() { return this.IR; }
    a_spotlight(at, dur, e, args) { this.spotR.add(at, { region: args.region || [0, 0, 1, 1], level: args.level ?? 0.62 }); this.spotT.to(at, 1, dur, e); }
    a_unspotlight(at, dur, e) { this.spotT.to(at, 0, dur, e); }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      css(this.root, 'transform', v >= 0.999 ? 'none' : `translateY(${((1 - v) * 26).toFixed(1)}px) scale(${(0.98 + 0.02 * v).toFixed(4)})`);
      css(this.root, 'filter', v >= 0.999 ? 'none' : `blur(${((1 - v) * 8).toFixed(1)}px)`);
      const fl = this.flashAt(t);
      css(this.frame, 'boxShadow', fl.amt > 0.01 ? `0 0 0 1px rgba(255,255,255,0.14), 0 0 ${(30 * fl.amt).toFixed(1)}px ${rgba(fl.color, 0.8 * fl.amt)}, 0 24px 70px rgba(0,0,0,0.7)` : '');
      const s = this.spotT.value(t), ev = this.spotR.last(t);
      if (s > 0.001 && ev) {
        const R = ev.region, w = this.IR.w, h = this.IR.h;
        Object.assign(this.spot.style, { display: 'block', left: R[0] * w - 6 + 'px', top: R[1] * h - 6 + 'px', width: R[2] * w + 12 + 'px', height: R[3] * h + 12 + 'px' });
        css(this.spot, 'boxShadow', `0 0 0 4000px rgba(0,0,0,${(ev.level * s).toFixed(3)})`);
      } else css(this.spot, 'boxShadow', 'none');
    }
  }

  // ------------------------------------------------------------------ CodeSnippet
  const KW = new Set('def return if elif else for while in import from as class const let var function async await new true false null None True False self this try except catch finally with yield lambda pass break continue raise throw export default fn pub mut struct impl use match int float str bool void'.split(' '));
  function highlightCode(line) {
    const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const re = /(#.*$|\/\/.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`[^`]*`)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)(?=\s*\()|([A-Za-z_]\w*)/g;
    let out = '', last = 0, m;
    while ((m = re.exec(line))) {
      out += esc(line.slice(last, m.index));
      if (m[1]) out += `<span class="c">${esc(m[1])}</span>`;
      else if (m[2]) out += `<span class="s">${esc(m[2])}</span>`;
      else if (m[3]) out += `<span class="n">${esc(m[3])}</span>`;
      else if (m[4]) out += KW.has(m[4]) ? `<span class="k">${esc(m[4])}</span>` : `<span class="f">${esc(m[4])}</span>`;
      else out += KW.has(m[5]) ? `<span class="k">${esc(m[5])}</span>` : esc(m[5]);
      last = re.lastIndex;
    }
    return out + esc(line.slice(last));
  }
  class CodeSnippet extends Primitive {
    static layer = 'nodes';
    static defaults = { code: '', title: '', box: [0.08, 0.2, 0.5], fontSize: 26, lineNumbers: true, startLine: 1 };
    static actions = { enter: { dur: null, ease: 'out' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, mark: { dur: null }, pulse: { dur: 0.6 } };
    build() {
      const S = this.scene, p = this.props;
      const r = p.box;
      this.root.classList.add('nt-code');
      this.root.style.width = r[2] * S.W + 'px';
      if (r[3]) this.root.style.minHeight = r[3] * S.H + 'px';
      const bar = el('div', { class: 'bar' }, this.root);
      el('i', {}, bar); el('i', {}, bar); el('i', {}, bar);
      if (p.title) el('span', { text: p.title }, bar);
      const body = el('div', { class: 'body' }, this.root);
      body.style.fontSize = p.fontSize + 'px';
      body.style.lineHeight = '1.6';
      const lines = Array.isArray(p.code) ? p.code : String(p.code).replace(/\n$/, '').split('\n');
      this.lines = lines.map((ln, i) => {
        const row = el('div', { class: 'line' }, body);
        if (p.lineNumbers) el('span', { class: 'no', text: String(i + p.startLine) }, row); else row.style.paddingLeft = '28px';
        const tx = el('span', { class: 'txt' }, row, highlightCode(ln) || ' ');
        return { row, tx, text: ln };
      });
      this.marks = 0;
      this.revealAt = null;
    }
    layoutSelf() { const S = this.scene, r = this.props.box; this.place(r[0] * S.W + this.w / 2, r[1] * S.H + this.h / 2); }
    lineIndex(l) {
      if (typeof l === 'number') return clamp(l - this.props.startLine, 0, this.lines.length - 1);
      const i = this.lines.findIndex((x) => x.text.includes(String(l)));
      if (i < 0) throw new Error(`CodeSnippet "${this.id}": no line containing "${l}"`);
      return i;
    }
    refBox(r) {
      if (r && r.line != null) {
        const ls = Array.isArray(r.line) ? r.line.map((l) => this.lineIndex(l)) : [this.lineIndex(r.line)];
        const bs = [];
        for (let i = Math.min(...ls); i <= Math.max(...ls); i++) {
          const tx = this.lines[i].tx, str = this.lines[i].text;
          let x = 0, y = 0;
          for (let e = tx; e && e !== this.root; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
          const b = this.box;
          const cw = tx.offsetWidth / Math.max(1, str.length); // monospace: trim indentation and trailing spaces
          const lead = str.length - str.trimStart().length, used = str.trimEnd().length;
          const x0 = x + lead * cw, w = Math.max(cw, (used - lead) * cw);
          bs.push(CA.box(b.x + x0 + w / 2, b.y + y + tx.offsetHeight / 2, w, tx.offsetHeight * 0.9));
        }
        return regionOf(unionBox(bs), r.region);
      }
      return regionOf(this.box, r && r.region);
    }
    a_enter(at, dur, e, args) {
      const n = this.lines.length, per = args.lineDur ?? 0.16, st = args.stagger ?? 0.1;
      const D = args.dur ?? 0.35 + (n - 1) * st + per;
      this.vis.to(at, 1, 0.35, 'out');
      this.reveal = { at: at + 0.25, per, st: n > 1 ? Math.min(st, (D - 0.25 - per) / (n - 1)) : st };
      if (this.enterAt == null) this.enterAt = at;
    }
    a_mark(at, dur, e, args) {
      const S = this.scene, n = ++this.marks;
      const style = args.style || 'underline';
      const prim = style === 'loop' ? 'Loop' : style === 'box' ? 'Loop' : style === 'bracket' ? 'Bracket' : style === 'cross' ? 'CrossOut' : 'Underline';
      const props = { target: this.id, line: args.line, color: args.color || (style === 'cross' ? 'red' : 'purple'), auto: false };
      if (style === 'box') { props.shape = 'box'; props.pad = 2; }
      if (style === 'bracket') { props.side = args.side || 'left'; props.kind = args.kind || 'tradeoff'; props.gap = 64; }
      if (style === 'loop') props.pad = 4;
      const m = S.spawn({ id: `${this.id}-mark${n}`, primitive: prim, props });
      const D = m.drawAt(at, args.dur != null ? { dur: args.dur } : {});
      if (args.note) {
        const nt = S.spawn({ id: `${this.id}-note${n}`, primitive: 'InkText', props: { text: args.note, target: this.id, line: args.line, side: args.noteSide || 'right', gap: args.noteGap ?? 40, size: args.noteSize ?? 36, color: args.noteColor || args.color || 'purple', auto: false, dx: args.noteDx || 0 } });
        nt.drawAt(at + D * 0.8, {});
      }
    }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      css(this.root, 'transform', v >= 0.999 ? 'none' : `translateY(${((1 - v) * 18).toFixed(1)}px)`);
      const fl = this.flashAt(t);
      css(this.root, 'boxShadow', fl.amt > 0.01 ? `0 0 ${(30 * fl.amt).toFixed(1)}px ${rgba(fl.color, 0.7 * fl.amt)}, 0 24px 60px rgba(0,0,0,0.7)` : '');
      const R = this.reveal;
      this.lines.forEach((l, i) => {
        const p = R ? clamp((t - R.at - i * R.st) / R.per) : 0;
        css(l.tx, 'maskImage', p >= 1 ? 'none' : `linear-gradient(90deg, #000 ${(p * 130 - 30).toFixed(1)}%, transparent ${(p * 130).toFixed(1)}%)`);
        css(l.tx, 'visibility', p <= 0 ? 'hidden' : 'visible');
      });
    }
  }

  // ------------------------------------------------------------------ Chart3D (three.js)
  const FRAME_P = 18.6, FRAME_O = 13.4; // visible world height: perspective / orthographic views (cube = 10)
  class Chart3D extends Primitive {
    static layer = 'nodes';
    static defaults = { box: [0.06, 0.1, 0.88, 0.84], axes: {}, series: [], camera: { azimuth: 35, elevation: 22 }, zoom: 1, grid: 5, fov: 32, autoDraw: true, thickness: 1 };
    static actions = {
      enter: { dur: 1.0, ease: 'out' }, exit: { dur: 0.5 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, pulse: { dur: 0.6 },
      drawSeries: { dur: 1.4, ease: 'inOut' }, orbit: { dur: 1.8, ease: 'smooth' }, view: { dur: 1.6, ease: 'smooth' },
      highlightSeries: { dur: 0.5, ease: 'smooth' }, unhighlightSeries: { dur: 0.5, ease: 'smooth' },
    };
    build() {
      const S = this.scene, p = this.props;
      if (!window.THREE) throw new Error('Chart3D needs three.js (assets/vendor/three/three.min.js)');
      const T = window.THREE;
      this.B = boxFromFrac(S, p.box);
      const W = Math.round(this.B.w), H = Math.round(this.B.h);
      this.root.classList.add('nt-chart');
      Object.assign(this.root.style, { width: W + 'px', height: H + 'px' });
      this.canvas = el('canvas', {}, this.root);
      Object.assign(this.canvas.style, { width: W + 'px', height: H + 'px' });
      const r = (this.renderer = new T.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' }));
      r.setPixelRatio(S.k);
      r.setSize(W, H, false);
      r.setClearColor(0x000000, 0);
      this.aspect = W / H;
      const sc = (this.s3 = new T.Scene());
      sc.add(new T.AmbientLight(0xffffff, 1.6));
      const dl = new T.DirectionalLight(0xffffff, 1.6); dl.position.set(3, 8, 6); sc.add(dl);
      this.persp = new T.PerspectiveCamera(p.fov, this.aspect, 0.1, 500);
      this.ortho = new T.OrthographicCamera(-1, 1, 1, -1, 0.1, 500);
      // axes
      const ax = (k) => Object.assign({ label: k, min: 0, max: 1, ticks: p.grid, prefix: '', suffix: '', decimals: null }, (p.axes || {})[k] || {});
      this.ax = { x: ax('x'), y: ax('y'), z: ax('z') };
      const n = p.grid;
      // walls: floor (y=-5), x-walls (x=+-5), z-walls (z=+-5)
      const wall = (fixed, val) => {
        const pos = [], edge = [];
        for (let i = 0; i <= n; i++) {
          const u = -5 + (10 * i) / n;
          const seg = (a, b, isEdge) => (isEdge ? edge : pos).push(...a, ...b);
          const isE = i === 0 || i === n;
          if (fixed === 'y') { seg([u, val, -5], [u, val, 5], isE); seg([-5, val, u], [5, val, u], isE); }
          if (fixed === 'x') { seg([val, u, -5], [val, u, 5], isE); seg([val, -5, u], [val, 5, u], isE); }
          if (fixed === 'z') { seg([u, -5, val], [u, 5, val], isE); seg([-5, u, val], [5, u, val], isE); }
        }
        const mk = (arr, color) => {
          const g = new T.BufferGeometry(); g.setAttribute('position', new T.Float32BufferAttribute(arr, 3));
          const m = new T.LineBasicMaterial({ color, transparent: true, opacity: 1, depthWrite: false });
          const ls = new T.LineSegments(g, m); sc.add(ls); return m;
        };
        return { grid: mk(pos, 0x222222), edge: mk(edge, 0x3a3a3a) };
      };
      this.walls = { floor: wall('y', -5), xn: wall('x', -5), xp: wall('x', 5), zn: wall('z', -5), zp: wall('z', 5) };
      // series
      this.series = (p.series || []).map((s, si) => {
        const col = S.resolveColor(s.color) || SERIES[si % SERIES.length];
        const pts = s.points.map((q) => this.toWorld(q));
        const path = new T.CurvePath();
        for (let i = 1; i < pts.length; i++) path.add(new T.LineCurve3(pts[i - 1], pts[i]));
        let total = 0; const cum = [0];
        for (let i = 1; i < pts.length; i++) { total += pts[i].distanceTo(pts[i - 1]); cum.push(total); }
        const tub = Math.max(64, Math.round(total * 14));
        const rad = 8, th = p.thickness * (s.width || 1);
        const tube = (radius, color, opacity, additive) => {
          const g = new T.TubeGeometry(path, tub, radius, rad, false);
          const m = new T.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, depthWrite: !additive, blending: additive ? T.AdditiveBlending : T.NormalBlending });
          const mesh = new T.Mesh(g, m); sc.add(mesh); return { g, m, mesh };
        };
        const core = tube(0.055 * th, mixColor(col, '#FFFFFF', 0.35), 1, false);
        const g1 = tube(0.15 * th, col, 0.32, true);
        const g2 = tube(0.34 * th, col, 0.09, true);
        const marker = s.marker || 'sphere';
        const markers = pts.map((q, i) => {
          const grp = new T.Group(); grp.position.copy(q);
          if (marker === 'cross') {
            const mat = new T.MeshBasicMaterial({ color: mixColor(col, '#FFFFFF', 0.25) });
            const bx = new T.BoxGeometry(0.46, 0.07, 0.07);
            const a = new T.Mesh(bx, mat), b = new T.Mesh(bx, mat), c2 = new T.Mesh(bx, mat);
            a.rotation.z = Math.PI / 4; b.rotation.z = -Math.PI / 4; c2.rotation.y = Math.PI / 2; c2.rotation.z = Math.PI / 4;
            grp.add(a, b, c2);
          } else {
            grp.add(new T.Mesh(new T.SphereGeometry(0.16, 20, 14), new T.MeshLambertMaterial({ color: col, emissive: new T.Color(col).multiplyScalar(0.55) })));
          }
          const halo = new T.Mesh(new T.SphereGeometry(0.34, 16, 10), new T.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.16, depthWrite: false, blending: T.AdditiveBlending }));
          grp.add(halo);
          grp.scale.setScalar(0.0001);
          sc.add(grp);
          return { grp, f: cum[i] / (total || 1) };
        });
        return { s, col, pts, tubes: [core, g1, g2], tub, rad, markers, drawWins: [], dimT: new Track(1), name: s.name || '' };
      });
      // labels
      const lab = (cls, txt, color) => { const d = el('div', { class: 'lab3d ' + cls, text: txt }, this.root); if (color) { d.style.color = color; d.style.textShadow = textGlow(color, 0.8); } return d; };
      this.ticks = { x: [], y: [], z: [] };
      for (const k of ['x', 'y', 'z']) {
        const a = this.ax[k], tn = a.ticks;
        for (let i = 0; i <= tn; i++) {
          const v = a.min + ((a.max - a.min) * i) / tn;
          const dec = a.decimals ?? (Math.abs(a.max - a.min) / tn < 1 ? 1 : 0);
          this.ticks[k].push({ el: lab('tick', formatNumber(v, { decimals: dec, prefix: a.prefix, suffix: a.suffix, sep: '' })), u: -5 + (10 * i) / tn });
        }
      }
      this.titles = { x: lab('title', this.ax.x.label), y: lab('title', this.ax.y.label), z: lab('title', this.ax.z.label) };
      this.seriesLabels = this.series.map((s) => (s.name ? lab('series', s.name, s.col) : null));
      // tracks
      const cam = p.camera || {};
      this.azT = new Track(cam.azimuth ?? 35); this.elT = new Track(cam.elevation ?? 22);
      this.orthoT = new Track(cam.ortho ? 1 : 0);
      this.frameT = new Track(FRAME_P / (p.zoom || 1));
      this.gridT = new Track(0);
      this._v = new T.Vector3();
    }
    measure() { this.w = Math.round(this.B.w); this.h = Math.round(this.B.h); return { w: this.w, h: this.h }; }
    layoutSelf() { this.place(this.B.cx, this.B.cy); }
    toWorld(q) {
      const T = window.THREE, a = this.ax;
      const m = (v, A) => ((v - A.min) / (A.max - A.min || 1) - 0.5) * 10;
      return new T.Vector3(m(q[0], a.x), m(q[1], a.y), m(q[2] ?? a.z.min, a.z));
    }
    seriesIndex(s) {
      if (typeof s === 'number') return clamp(s, 0, this.series.length - 1);
      const i = this.series.findIndex((x) => x.name.toLowerCase() === String(s).toLowerCase());
      if (i < 0) throw new Error(`Chart3D "${this.id}": no series "${s}"`);
      return i;
    }
    /** Configure and return the camera for time t. */
    cameraAt(t) {
      const az = (this.azT.value(t) * Math.PI) / 180;
      const elv = (clamp(this.elT.value(t), -89.9, 89.9) * Math.PI) / 180;
      const o = ease.inOut(clamp(this.orthoT.value(t)));
      const halfH = this.frameT.value(t) / 2; // frameT = visible world height
      const dir = [Math.cos(elv) * Math.sin(az), Math.sin(elv), Math.cos(elv) * Math.cos(az)];
      const up = [-Math.sin(elv) * Math.sin(az), Math.cos(elv), -Math.sin(elv) * Math.cos(az)];
      this.dir = dir;
      const ty = -1.5 * (1 - o) * Math.cos(elv); // aim a little below center in perspective (the near corner projects large)
      let cam;
      if (o >= 0.999) {
        cam = this.ortho;
        Object.assign(cam, { left: -halfH * this.aspect, right: halfH * this.aspect, top: halfH, bottom: -halfH, near: 0.1, far: 200 });
        cam.position.set(dir[0] * 60, dir[1] * 60 + ty, dir[2] * 60);
      } else {
        cam = this.persp;
        const t0 = Math.tan((this.props.fov * Math.PI) / 360), t1 = Math.tan((0.3 * Math.PI) / 180);
        const th = Math.exp(lerp(Math.log(t0), Math.log(t1), o));
        const d = halfH / th;
        cam.fov = (2 * Math.atan(th) * 180) / Math.PI;
        cam.near = Math.max(0.1, d - 30); cam.far = d + 30; cam.aspect = this.aspect;
        cam.position.set(dir[0] * d, dir[1] * d + ty, dir[2] * d);
      }
      cam.up.set(up[0], up[1], up[2]);
      cam.lookAt(0, ty, 0);
      cam.updateProjectionMatrix();
      cam.updateMatrixWorld(true);
      return cam;
    }
    project(v3, cam) {
      const v = this._v.copy(v3).project(cam);
      return [(v.x + 1) / 2 * this.B.w, (1 - v.y) / 2 * this.B.h, v.z];
    }
    refBox(r, t) {
      const T = window.THREE;
      let w = null;
      if (r && Array.isArray(r.point)) w = this.toWorld(r.point);
      else if (r && r.series != null) { const s = this.series[this.seriesIndex(r.series)]; const i = r.index ?? s.pts.length - 1; w = s.pts[i < 0 ? s.pts.length + i : clamp(i, 0, s.pts.length - 1)]; }
      if (w) { const cam = this.cameraAt(t ?? 0); const q = this.project(new T.Vector3().copy(w), cam); return CA.box(this.B.x + q[0], this.B.y + q[1], 18, 18); }
      return regionOf(this.B, r && r.region);
    }
    a_enter(at, dur, e) {
      this.vis.to(at, 1, Math.min(0.5, dur), 'out');
      this.gridT.to(at, 1, dur, 'out');
      if (this.enterAt == null) this.enterAt = at;
      const explicit = (this.scene.spec.beats || []).some((b) => b.target === this.id && b.action === 'drawSeries');
      if (this.props.autoDraw && !explicit) this.series.forEach((s, i) => s.drawWins.push({ at: at + dur * 0.6 + i * 0.9, dur: 1.3 }));
    }
    a_drawSeries(at, dur, e, args) {
      const which = args.series == null || args.series === 'all' ? this.series.map((_, i) => i) : [].concat(args.series).map((s) => this.seriesIndex(s));
      which.forEach((i, k) => this.series[i].drawWins.push({ at: at + k * (args.stagger ?? 0.5), dur }));
    }
    a_orbit(at, dur, e, args) {
      if (args.azimuth != null) this.azT.to(at, args.azimuth, dur, e);
      if (args.elevation != null) this.elT.to(at, args.elevation, dur, e);
      if (args.zoom != null) this.frameT.to(at, FRAME_P / args.zoom, dur, e);
      if (args.perspective) this.orthoT.to(at, 0, dur, e);
    }
    a_view(at, dur, e, args) {
      const mode = args.mode || 'top';
      const presets = { top: [0, 90], front: [0, 0], side: [90, 0], perspective: [null, null] };
      const pr = presets[mode] || presets.top;
      if (mode === 'perspective') {
        this.orthoT.to(at, 0, dur, e);
        this.azT.to(at, args.azimuth ?? (this.props.camera.azimuth ?? 35), dur, e);
        this.elT.to(at, args.elevation ?? (this.props.camera.elevation ?? 22), dur, e);
        this.frameT.to(at, FRAME_P / (args.zoom ?? this.props.zoom ?? 1), dur, e);
        return;
      }
      this.azT.to(at, args.azimuth ?? pr[0], dur, e);
      this.elT.to(at, pr[1], dur, e);
      this.orthoT.to(at, args.ortho === false ? 0 : 1, dur, e);
      this.frameT.to(at, FRAME_O / (args.zoom ?? 1), dur, e);
    }
    a_highlightSeries(at, dur, e, args) {
      const keep = new Set([].concat(args.series).map((s) => this.seriesIndex(s)));
      this.series.forEach((s, i) => s.dimT.to(at, keep.has(i) ? 1 : (args.level ?? 0.18), dur, e));
    }
    a_unhighlightSeries(at, dur, e) { this.series.forEach((s) => s.dimT.to(at, 1, dur, e)); }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      if (v * this.dimT.value(t) <= 0.001) return;
      const T = window.THREE;
      const cam = this.cameraAt(t);
      const d = this.dir, g = this.gridT.value(t);
      const fx = sm((d[0] + 0.12) / 0.24), fz = sm((d[2] + 0.12) / 0.24), fy = sm((d[1] + 0.1) / 0.2);
      const setW = (w, a) => { w.grid.opacity = a * g; w.edge.opacity = a * g; w.grid.visible = w.edge.visible = a * g > 0.002; };
      setW(this.walls.floor, fy); setW(this.walls.xn, fx); setW(this.walls.xp, 1 - fx); setW(this.walls.zn, fz); setW(this.walls.zp, 1 - fz);
      for (const s of this.series) {
        let p = 0;
        for (const w of s.drawWins) if (t >= w.at) p = Math.max(p, ease.inOut(clamp((t - w.at) / w.dur)));
        const segs = Math.round(p * s.tub);
        const dm = s.dimT.value(t);
        s.tubes.forEach((tb, k) => {
          tb.g.setDrawRange(0, segs * s.rad * 6);
          tb.mesh.visible = segs > 0;
          tb.m.opacity = [1, 0.32, 0.09][k] * dm; tb.m.transparent = k > 0 || dm < 1;
        });
        for (const m of s.markers) {
          const q = clamp((p - m.f) * 14 + (p >= 0.999 ? 1 : 0));
          m.grp.scale.setScalar(Math.max(0.0001, ease.outBack(q)));
          m.grp.children.forEach((c) => { if (c.material) { c.material.transparent = true; c.material.opacity = (c.material.blending === T.AdditiveBlending ? 0.16 : 1) * dm; } });
        }
        s.p = p; s.dm = dm;
      }
      this.renderer.render(this.s3, cam);
      // labels
      const sx = d[0] >= 0 ? 1 : -1, sz = d[2] >= 0 ? 1 : -1;
      const vis = (axis) => 1 - sm((Math.abs(axis) - 0.86) / 0.1);
      const placed = [];
      const put = (elm, w3, a, avoid) => {
        const pp = this.project(w3, cam);
        if (avoid) for (const q of placed) if (Math.abs(q[0] - pp[0]) < 52 && Math.abs(q[1] - pp[1]) < 26) a *= clamp((Math.max(Math.abs(q[0] - pp[0]) - 40, (Math.abs(q[1] - pp[1]) - 18) * 1.5)) / 12);
        if (a > 0.05) placed.push(pp);
        css(elm, 'transform', `translate(${f1(pp[0])}px, ${f1(pp[1])}px) translate(-50%, -50%)`);
        css(elm, 'opacity', clamp(a).toFixed(3));
      };
      const V = (x, y, z) => new T.Vector3(x, y, z);
      const ax = vis(d[0]) * g, az = vis(d[2]) * g, ay = vis(d[1]) * g;
      this.ticks.x.forEach((tk) => put(tk.el, V(tk.u, -5.55, sz * 5.75), ax));
      this.ticks.z.forEach((tk) => put(tk.el, V(sx * 5.75, -5.55, tk.u), az, true));
      this.ticks.y.forEach((tk, i) => put(tk.el, V(sx * 5.8, tk.u, -sz * 5), ay * (i === 0 ? 1 - az : 1)));
      put(this.titles.x, V(0, -6.5, sz * 6.9), ax);
      put(this.titles.z, V(sx * 6.9, -6.5, 0), az);
      put(this.titles.y, V(sx * 5.3, 6.5, -sz * 5), ay);
      this.series.forEach((s, i) => {
        const lb = this.seriesLabels[i];
        if (!lb) return;
        const last = s.pts[s.pts.length - 1];
        const pp = this.project(last, cam);
        css(lb, 'transform', `translate(${f1(pp[0] + 26)}px, ${f1(pp[1] - 30)}px) translate(0, -50%)`);
        css(lb, 'opacity', (clamp((s.p - 0.92) * 12) * s.dm).toFixed(3));
      });
    }
  }

  register('InkStroke', InkStroke);
  register('Sketch', class Sketch extends InkStroke {});
  register('InkText', InkText);
  register('Title', Title);
  register('Icon', Icon);
  register('Loop', Loop);
  register('Underline', Underline);
  register('Bracket', Bracket);
  register('CrossOut', CrossOut);
  register('HatchZone', HatchZone);
  register('Arrow', Arrow);
  register('Panel', Panel);
  register('RedPointer', RedPointer);
  register('Metric', Metric);
  register('BarChart', BarChart);
  register('LineChart', LineChart);
  register('Screenshot', Screenshot);
  register('CodeSnippet', CodeSnippet);
  register('Chart3D', Chart3D);

  // ------------------------------------------------------------------ layout: explicit positions (canvas fractions)
  registerLayout('neon-telestrator', (S) => {
    for (const e of S.list) {
      if (e.layoutSelf) e.layoutSelf();
      else e.place(S.W / 2, S.H / 2);
    }
  });

  window.NT = { Stroke, HandText, resolveRef, mediaUrl, INK };
})();
