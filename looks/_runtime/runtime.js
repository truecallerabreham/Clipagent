/* ClipAgent HTML Insert runtime.
 *
 * Contract (docs/design.md, Contract 2):
 *   player.html?spec=<url>  ->  window.clipagent = { ready, duration, seek(t) }
 *
 * seek(t) is a PURE function of t. Everything time-dependent is compiled once at build time
 * into tracks/segments; seek(t) only evaluates them and writes styles. No CSS animations,
 * no requestAnimationFrame clocks, no unseeded randomness.
 *
 * Shared helpers for Looks live on window.CA (see looks/README.md for the API list).
 */
(function () {
  'use strict';
  const CA = (window.CA = {});
  const SVGNS = 'http://www.w3.org/2000/svg';

  // ------------------------------------------------------------------ math
  const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
  const lerp = (a, b, p) => a + (b - a) * p;

  function cubicBezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t;
    const sy = (t) => ((ay * t + by) * t + cy) * t;
    const dsx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) {
        const e = sx(t) - x;
        if (Math.abs(e) < 1e-6) return sy(t);
        const d = dsx(t);
        if (Math.abs(d) < 1e-6) break;
        t -= e / d;
      }
      let lo = 0, hi = 1;
      t = x;
      for (let i = 0; i < 40; i++) {
        const v = sx(t);
        if (Math.abs(v - x) < 1e-6) break;
        if (x > v) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return sy(t);
    };
  }

  const ease = {
    linear: (x) => x,
    smooth: cubicBezier(0.65, 0, 0.35, 1), // strong ease-in-out (Manim-style "smooth")
    inOut: cubicBezier(0.42, 0, 0.58, 1),
    out: cubicBezier(0.16, 1, 0.3, 1),
    in: cubicBezier(0.55, 0, 1, 0.45),
    outBack: (x) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    cubicBezier,
  };
  function getEase(e) {
    if (typeof e === 'function') return e;
    if (Array.isArray(e)) return cubicBezier(e[0], e[1], e[2], e[3]);
    return ease[e] || ease.smooth;
  }
  /** Eased 0..1 progress of a window [start, start+dur] at time t. */
  function prog(t, start, dur, e) {
    if (dur <= 0) return t >= start ? 1 : 0;
    return getEase(e)(clamp((t - start) / dur));
  }
  /** 0..1..0 bump over a window (sin), useful for pulses/flashes. */
  function bump(t, start, dur) {
    if (t < start || t > start + dur || dur <= 0) return 0;
    return Math.sin(Math.PI * (t - start) / dur);
  }

  // ------------------------------------------------------------------ colors
  function hexToRgb(hex) {
    let h = String(hex).trim().replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const n = parseInt(h.slice(0, 6), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('');
  }
  function mixColor(a, b, p) {
    const A = hexToRgb(a), B = hexToRgb(b);
    return rgbToHex(lerp(A[0], B[0], p), lerp(A[1], B[1], p), lerp(A[2], B[2], p));
  }
  function rgba(hex, a) {
    const [r, g, b] = hexToRgb(hex);
    return `rgba(${r},${g},${b},${+a.toFixed(4)})`;
  }
  const isHex = (v) => typeof v === 'string' && /^#[0-9a-f]{3,8}$/i.test(v);

  function lerpValue(a, b, p) {
    if (typeof a === 'number' && typeof b === 'number') return lerp(a, b, p);
    if (Array.isArray(a) && Array.isArray(b)) return a.map((v, i) => lerpValue(v, b[i], p));
    if (isHex(a) && isHex(b)) return mixColor(a, b, p);
    return p < 1 ? a : b; // discrete values switch at the end of the transition
  }

  // ------------------------------------------------------------------ Track
  /** A keyframe track. Each key is a transition that starts at `at`, lasts `dur`, and goes from
   *  whatever value the track had at `at` (even mid-transition) to `value`. value(t) is pure. */
  class Track {
    constructor(initial) { this.initial = initial; this.keys = []; this._ready = false; }
    to(at, value, dur = 0.5, e = 'smooth') {
      this.keys.push({ at, value, dur: Math.max(0, dur), ease: getEase(e), seq: this.keys.length });
      this._ready = false;
      return this;
    }
    set(at, value) { return this.to(at, value, 0); }
    /** Drop keys that start after t (used when a new action supersedes scheduled ones). */
    cancelAfter(t) { this.keys = this.keys.filter((k) => k.at <= t); this._ready = false; return this; }
    _finalize() {
      this.keys.sort((a, b) => a.at - b.at || a.seq - b.seq);
      for (let i = 0; i < this.keys.length; i++) {
        const k = this.keys[i];
        k.from = i === 0 ? this.initial : this._evalKey(this.keys[i - 1], k.at);
      }
      this._ready = true;
    }
    _evalKey(k, t) {
      if (k.dur <= 0 || t >= k.at + k.dur) return k.value;
      return lerpValue(k.from, k.value, k.ease(clamp((t - k.at) / k.dur)));
    }
    value(t) {
      if (!this._ready) this._finalize();
      const ks = this.keys;
      let lo = 0, hi = ks.length - 1, idx = -1;
      while (lo <= hi) { const m = (lo + hi) >> 1; if (ks[m].at <= t) { idx = m; lo = m + 1; } else hi = m - 1; }
      if (idx < 0) return this.initial;
      return this._evalKey(ks[idx], t);
    }
    /** Time of the last key starting at or before t (or -Infinity). */
    lastKeyAt(t) {
      if (!this._ready) this._finalize();
      let r = -Infinity;
      for (const k of this.keys) if (k.at <= t) r = k.at;
      return r;
    }
  }

  /** Discrete event list: active(t) returns the last event with at <= t. */
  class Events {
    constructor() { this.list = []; }
    add(at, data) { this.list.push(Object.assign({ at, seq: this.list.length }, data)); this.list.sort((a, b) => a.at - b.at || a.seq - b.seq); return this; }
    last(t) { let r = null; for (const e of this.list) { if (e.at <= t) r = e; else break; } return r; }
    all(t) { return this.list.filter((e) => e.at <= t); }
  }

  // ------------------------------------------------------------------ seeded randomness
  function hashStr(s) {
    let h = 2166136261 >>> 0;
    s = String(s);
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  /** mulberry32 seeded RNG: rng(seed) -> () => [0,1). seed may be a number or string. */
  function rng(seed) {
    let a = typeof seed === 'number' ? seed >>> 0 : hashStr(seed);
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  /** Stateless noise in [0,1) for integer-ish inputs: noise(seed, i). */
  const noise = (seed, i) => rng(hashStr(seed) ^ Math.imul((i | 0) + 1, 2654435761))();

  // ------------------------------------------------------------------ DOM helpers
  function el(tag, attrs, parent, html) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === 'class') e.className = attrs[k];
      else if (k === 'style' && typeof attrs[k] === 'object') Object.assign(e.style, attrs[k]);
      else if (k === 'text') e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    if (html != null) e.innerHTML = html;
    if (parent) parent.appendChild(e);
    return e;
  }
  function svgEl(tag, attrs, parent) {
    const e = document.createElementNS(SVGNS, tag);
    if (attrs) for (const k in attrs) {
      if (k === 'style' && typeof attrs[k] === 'object') Object.assign(e.style, attrs[k]);
      else if (k === 'text') e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    if (parent) parent.appendChild(e);
    return e;
  }
  /** Set a style property only if it changed (cheap per-frame writes). */
  function css(e, prop, value) {
    const key = '_ca_' + prop;
    if (e[key] === value) return;
    e[key] = value;
    e.style[prop] = value;
  }
  function attr(e, name, value) {
    const key = '_caa_' + name;
    if (e[key] === value) return;
    e[key] = value;
    e.setAttribute(name, value);
  }
  function text(e, value) { if (e._ca_text !== value) { e._ca_text = value; e.textContent = value; } }

  // ------------------------------------------------------------------ paths
  /** Arc-length lookup table over a polyline. at(s) -> {x, y, angle}. */
  class PathLUT {
    constructor(pts) {
      const n = pts.length;
      this.xs = new Float64Array(n); this.ys = new Float64Array(n); this.cum = new Float64Array(n);
      let L = 0;
      for (let i = 0; i < n; i++) {
        this.xs[i] = pts[i][0]; this.ys[i] = pts[i][1];
        if (i > 0) L += Math.hypot(this.xs[i] - this.xs[i - 1], this.ys[i] - this.ys[i - 1]);
        this.cum[i] = L;
      }
      this.length = L;
    }
    static fromPoints(pts) { return new PathLUT(pts.length > 1 ? pts : [pts[0], pts[0]]); }
    /** Sample an SVG path d-string (or <path>) into a LUT; step in px. */
    static fromPath(d, step = 3) {
      const p = typeof d === 'string' ? PathLUT._scratch(d) : d;
      const len = p.getTotalLength();
      const n = Math.max(2, Math.ceil(len / step));
      const pts = [];
      for (let i = 0; i <= n; i++) { const q = p.getPointAtLength((len * i) / n); pts.push([q.x, q.y]); }
      return new PathLUT(pts);
    }
    static _scratch(d) {
      if (!PathLUT._svg) {
        PathLUT._svg = svgEl('svg', { width: 0, height: 0, style: { position: 'absolute', visibility: 'hidden' } }, document.body);
        PathLUT._path = svgEl('path', {}, PathLUT._svg);
      }
      PathLUT._path.setAttribute('d', d);
      return PathLUT._path;
    }
    _idx(s) {
      const c = this.cum; let lo = 0, hi = c.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (c[m] <= s) lo = m; else hi = m; }
      return lo;
    }
    at(s) {
      const n = this.cum.length;
      s = clamp(s, 0, this.length);
      const i = Math.min(this._idx(s), n - 2);
      const seg = this.cum[i + 1] - this.cum[i] || 1e-9;
      const p = clamp((s - this.cum[i]) / seg);
      const dx = this.xs[i + 1] - this.xs[i], dy = this.ys[i + 1] - this.ys[i];
      return { x: this.xs[i] + dx * p, y: this.ys[i] + dy * p, angle: Math.atan2(dy, dx) };
    }
    atFrac(p) { return this.at(p * this.length); }
    points() { return Array.from(this.xs, (x, i) => [x, this.ys[i]]); }
    /** Polyline d-string of the sub-path [s0, s1] (used for draw-on of dashed lines). */
    partialD(s0, s1) {
      s0 = clamp(s0, 0, this.length); s1 = clamp(s1, 0, this.length);
      if (s1 <= s0) return '';
      const a = this.at(s0), b = this.at(s1);
      let d = `M${a.x.toFixed(1)},${a.y.toFixed(1)}`;
      for (let i = 0; i < this.cum.length; i++) if (this.cum[i] > s0 && this.cum[i] < s1) d += `L${this.xs[i].toFixed(1)},${this.ys[i].toFixed(1)}`;
      return d + `L${b.x.toFixed(1)},${b.y.toFixed(1)}`;
    }
    reversed() { return new PathLUT(this.points().reverse()); }
    concat(other) { const a = this.points(), b = other.points(); return new PathLUT(a.concat(b)); }
  }

  /** d-string for a polyline with rounded corners of radius r. */
  function roundedPolyline(pts, r = 16) {
    if (pts.length < 2) return '';
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const l1 = Math.hypot(x1 - x0, y1 - y0), l2 = Math.hypot(x2 - x1, y2 - y1);
      const rr = Math.min(r, l1 / 2, l2 / 2);
      if (rr < 0.5) { d += `L${x1},${y1}`; continue; }
      const ax = x1 - ((x1 - x0) / l1) * rr, ay = y1 - ((y1 - y0) / l1) * rr;
      const bx = x1 + ((x2 - x1) / l2) * rr, by = y1 + ((y2 - y1) / l2) * rr;
      d += `L${ax.toFixed(2)},${ay.toFixed(2)}Q${x1},${y1} ${bx.toFixed(2)},${by.toFixed(2)}`;
    }
    const last = pts[pts.length - 1];
    return d + `L${last[0]},${last[1]}`;
  }

  /** Stroke draw-on for a solid SVG path: p in 0..1. len = getTotalLength() (cached on the element). */
  function drawOn(pathEl, p, len) {
    if (len == null) { if (pathEl._caLen == null) pathEl._caLen = pathEl.getTotalLength(); len = pathEl._caLen; }
    attr(pathEl, 'visibility', p <= 0.0005 ? 'hidden' : 'visible'); // round caps would show a dot at p=0
    attr(pathEl, 'stroke-dasharray', `${len.toFixed(2)} ${(len + 1).toFixed(2)}`);
    attr(pathEl, 'stroke-dashoffset', (len * (1 - clamp(p))).toFixed(2));
  }
  /** Marching-ants dash offset for a dashed outline: pure in t. */
  function marchingAnts(e, t, speed = 30) { attr(e, 'stroke-dashoffset', (-t * speed).toFixed(2)); }

  /** Path morphing (vendored flubber, MIT). Returns (p) => d. Cached per (from, to). */
  const _morphCache = new Map();
  function morph(fromD, toD, opts) {
    const key = fromD + '|' + toD;
    if (!_morphCache.has(key)) {
      if (!window.flubber) throw new Error('flubber not loaded');
      _morphCache.set(key, window.flubber.interpolate(fromD, toD, Object.assign({ maxSegmentLength: 4 }, opts || {})));
    }
    const f = _morphCache.get(key);
    return (p) => (p <= 0 ? fromD : p >= 1 ? toD : f(p));
  }

  // ------------------------------------------------------------------ text
  /** Split text into word spans. `*emphasis*` marks words; concept phrases get their Concept Color.
   *  colorFor(phrase) -> color|null. Returns array of spans. */
  function splitWords(container, str, opts = {}) {
    container.textContent = '';
    const tokens = [];
    const re = /\*([^*]+)\*(\S*)|(\S+)/g;
    let m;
    while ((m = re.exec(str))) {
      if (m[1]) {
        const ws = m[1].split(/\s+/);
        ws.forEach((w, i) => tokens.push({ w, em: true, tail: i === ws.length - 1 ? m[2] : '' }));
      } else tokens.push({ w: m[3], em: false, tail: '' });
    }
    // concept phrase matching (longest first, case-insensitive, punctuation-tolerant)
    const colors = new Array(tokens.length).fill(null);
    if (opts.colorFor) {
      const norm = (w) => w.toLowerCase().replace(/[^a-z0-9\-_]/g, '');
      for (let i = 0; i < tokens.length; i++) {
        for (let n = Math.min(4, tokens.length - i); n >= 1; n--) {
          const phrase = tokens.slice(i, i + n).map((t) => norm(t.w)).join(' ');
          const c = opts.colorFor(phrase);
          if (c) { for (let j = i; j < i + n; j++) colors[j] = c; i += n - 1; break; }
        }
      }
    }
    const spans = [];
    tokens.forEach((tk, i) => {
      const s = el('span', { class: 'ca-word' + (tk.em ? ' em' : '') }, container);
      const c = colors[i] || (tk.em ? opts.emphasisColor : null);
      if (tk.tail) { // punctuation glued after *emphasis* stays uncolored but moves with the word
        const w = el('span', {}, s); w.textContent = tk.w;
        if (c) w.style.color = c;
        s.appendChild(document.createTextNode(tk.tail));
      } else {
        s.textContent = tk.w;
        if (c) s.style.color = c;
      }
      spans.push(s);
      if (i < tokens.length - 1) container.appendChild(document.createTextNode(' '));
    });
    return spans;
  }
  /** Word-by-word blur reveal. local = seconds since the reveal started.
   *  Each word fades from blur/rise to sharp over wordDur, starting stagger seconds apart. */
  function revealWords(spans, local, o = {}) {
    const stagger = o.stagger ?? 0.12, wordDur = o.wordDur ?? 0.5, blur = o.blur ?? 14, rise = o.rise ?? 14;
    const e = getEase(o.ease || 'out');
    spans.forEach((s, i) => {
      const p = e(clamp((local - i * stagger) / wordDur));
      css(s, 'opacity', p.toFixed(3));
      css(s, 'filter', p >= 1 ? 'none' : `blur(${((1 - p) * blur).toFixed(2)}px)`);
      css(s, 'transform', p >= 1 ? 'none' : `translateY(${((1 - p) * rise).toFixed(2)}px)`);
    });
  }
  const revealDuration = (n, o = {}) => (n - 1) * (o.stagger ?? 0.12) + (o.wordDur ?? 0.5);

  /** Number counter formatting. counter(from, to, p, {decimals, prefix, suffix, sep}). */
  function counter(from, to, p, o = {}) {
    const v = lerp(from, to, clamp(p));
    return formatNumber(v, o);
  }
  function formatNumber(v, o = {}) {
    const d = o.decimals ?? 0;
    let s = Math.abs(v).toFixed(d);
    if (o.sep !== '') { const [i, f] = s.split('.'); s = i.replace(/\B(?=(\d{3})+(?!\d))/g, o.sep ?? ',') + (f ? '.' + f : ''); }
    return (v < 0 ? '-' : '') + (o.prefix || '') + s + (o.suffix || '');
  }
  /** Parse "1,240 ms" -> {num: 1240, prefix:'', suffix:' ms', decimals:0} or null. */
  function parseNumber(str) {
    const m = String(str).match(/^([^\d\-]*)(-?[\d,]*\.?\d+)(.*)$/);
    if (!m) return null;
    const num = parseFloat(m[2].replace(/,/g, ''));
    if (!isFinite(num)) return null;
    const dec = (m[2].split('.')[1] || '').length;
    return { num, prefix: m[1], suffix: m[3], decimals: dec, sep: m[2].includes(',') ? ',' : '' };
  }

  // ------------------------------------------------------------------ speed profile / particles
  /** Piecewise-linear speed over time with analytic distance integral (pure in t).
   *  change(at, speed, ramp) ramps linearly to `speed` over `ramp` seconds. */
  class SpeedProfile {
    constructor(speed) { this.pts = [[-1e9, speed]]; this.changes = []; this._ready = false; }
    change(at, speed, ramp = 0.6) { this.changes.push({ at, speed, ramp }); this._ready = false; return this; }
    _finalize() {
      this.changes.sort((a, b) => a.at - b.at);
      const pts = [[-1e9, this.pts[0][1]]];
      for (const c of this.changes) {
        const v0 = this._speedAt(pts, c.at);
        while (pts.length && pts[pts.length - 1][0] > c.at) pts.pop(); // interrupt an unfinished ramp
        pts.push([c.at, v0], [c.at + Math.max(1e-3, c.ramp), c.speed]);
      }
      this.pts = pts;
      this._ready = true;
    }
    _speedAt(pts, t) {
      for (let i = pts.length - 1; i >= 0; i--) {
        if (pts[i][0] <= t) {
          const n = pts[i + 1];
          if (!n) return pts[i][1];
          return lerp(pts[i][1], n[1], (t - pts[i][0]) / (n[0] - pts[i][0]));
        }
      }
      return pts[0][1];
    }
    speed(t) { if (!this._ready) this._finalize(); return this._speedAt(this.pts, t); }
    /** Distance travelled between t0 and t1 (t1 >= t0). */
    distance(t0, t1) {
      if (!this._ready) this._finalize();
      if (t1 <= t0) return 0;
      const P = this.pts;
      let d = 0;
      const xs = [t0, t1];
      for (const p of P) if (p[0] > t0 && p[0] < t1) xs.push(p[0]);
      xs.sort((a, b) => a - b);
      for (let i = 0; i < xs.length - 1; i++) d += ((this._speedAt(P, xs[i]) + this._speedAt(P, xs[i + 1])) / 2) * (xs[i + 1] - xs[i]);
      return d;
    }
  }
  /** Positions (arc lengths) of particles in a stream emitted every `spacing` px of travel.
   *  D = distance travelled since emission started; Dstop = distance at which emission stopped
   *  (Infinity while running); L = path length. Returns [{s, k}] for particles on the path. */
  function streamPositions(D, Dstop, spacing, L) {
    const out = [];
    const kMax = Math.floor(Math.min(D, Dstop) / spacing);
    const kMin = Math.max(0, Math.ceil((D - L) / spacing));
    for (let k = kMin; k <= kMax; k++) { const s = D - k * spacing; if (s >= 0 && s <= L) out.push({ s, k }); }
    return out;
  }

  // ------------------------------------------------------------------ geometry
  const box = (cx, cy, w, h) => ({ cx, cy, w, h, x: cx - w / 2, y: cy - h / 2, r: cx + w / 2, b: cy + h / 2 });
  /** Point on the edge of a box on a side: 'left'|'right'|'top'|'bottom', with offset along that edge. */
  function edgePoint(b, side, off = 0) {
    if (side === 'left') return [b.x, b.cy + off];
    if (side === 'right') return [b.r, b.cy + off];
    if (side === 'top') return [b.cx + off, b.y];
    return [b.cx + off, b.b];
  }
  /** Auto-route between two boxes. Returns {d, pts, fromSide, toSide}.
   *  opts: route 'elbow'|'curve'|'straight', fromSide, toSide, offset (parallel lane), radius. */
  function route(A, B, o = {}) {
    const gapX = Math.abs(B.cx - A.cx) - (A.w + B.w) / 2;
    const gapY = Math.abs(B.cy - A.cy) - (A.h + B.h) / 2;
    const horiz = o.fromSide ? (o.fromSide === 'left' || o.fromSide === 'right') : gapX >= gapY;
    const fs = o.fromSide || (horiz ? (B.cx >= A.cx ? 'right' : 'left') : (B.cy >= A.cy ? 'bottom' : 'top'));
    const ts = o.toSide || (horiz ? (B.cx >= A.cx ? 'left' : 'right') : (B.cy >= A.cy ? 'top' : 'bottom'));
    const off = o.offset || 0;
    let p0 = edgePoint(A, fs, off), p1 = edgePoint(B, ts, off);
    const kind = o.route || 'elbow';
    // elbow between facing sides: if the boxes overlap across the travel axis, use one straight line
    // aligned to the smaller box (looks cleaner than an S-bend)
    const opp = (fs === 'right' && ts === 'left') || (fs === 'left' && ts === 'right') || (fs === 'top' && ts === 'bottom') || (fs === 'bottom' && ts === 'top');
    if (kind === 'elbow' && opp && o.align !== false) {
      const m = o.alignMargin ?? 28;
      const H_ = fs === 'left' || fs === 'right';
      const lo = H_ ? Math.max(A.y, B.y) + m : Math.max(A.x, B.x) + m;
      const hi = H_ ? Math.min(A.b, B.b) - m : Math.min(A.r, B.r) - m;
      if (lo <= hi) {
        const small = (H_ ? A.h <= B.h : A.w <= B.w) ? A : B;
        const c = clamp((H_ ? small.cy : small.cx) + off, lo, hi);
        if (H_) { p0 = [p0[0], c]; p1 = [p1[0], c]; } else { p0 = [c, p0[1]]; p1 = [c, p1[1]]; }
      }
    }
    let pts, d;
    if (kind === 'straight') { pts = [p0, p1]; d = `M${p0}L${p1}`; }
    else if (kind === 'curve') {
      const h = fs === 'left' || fs === 'right';
      const k = (h ? Math.abs(p1[0] - p0[0]) : Math.abs(p1[1] - p0[1])) * 0.5;
      const sgn0 = fs === 'right' || fs === 'bottom' ? 1 : -1, sgn1 = ts === 'right' || ts === 'bottom' ? 1 : -1;
      const c0 = h ? [p0[0] + sgn0 * k, p0[1]] : [p0[0], p0[1] + sgn0 * k];
      const tsH = ts === 'left' || ts === 'right';
      const c1 = tsH ? [p1[0] + sgn1 * k, p1[1]] : [p1[0], p1[1] + sgn1 * k];
      d = `M${p0}C${c0} ${c1} ${p1}`;
      pts = null;
    } else {
      const fsH = fs === 'left' || fs === 'right', tsH = ts === 'left' || ts === 'right';
      if (fsH && tsH) {
        if (Math.abs(p0[1] - p1[1]) < 1) pts = [p0, p1];
        else { const mx = o.mid != null ? o.mid : (p0[0] + p1[0]) / 2; pts = [p0, [mx, p0[1]], [mx, p1[1]], p1]; }
      } else if (!fsH && !tsH) {
        if (Math.abs(p0[0] - p1[0]) < 1) pts = [p0, p1];
        else { const my = o.mid != null ? o.mid : (p0[1] + p1[1]) / 2; pts = [p0, [p0[0], my], [p1[0], my], p1]; }
      } else if (fsH) pts = [p0, [p1[0], p0[1]], p1];
      else pts = [p0, [p0[0], p1[1]], p1];
      d = roundedPolyline(pts, o.radius ?? 22);
    }
    return { d, pts, fromSide: fs, toSide: ts, p0, p1 };
  }

  // ------------------------------------------------------------------ primitives
  const registry = {};
  const layouts = {};
  function register(name, cls) { registry[name] = cls; cls.primitiveName = name; }
  function registerLayout(name, fn) { layouts[name] = fn; }

  /** Base class for Primitives. Subclasses:
   *   static defaults = {...props}; static actions = {name: {dur, ease}}; static autoEnter = true|false;
   *   static layer = 'nodes'|'text'|'pills'|'links'; static isNode = true for layout-placed nodes
   *   build()            create DOM under this.root (this.root is created for you)
   *   afterLayout()      everything is placed (links/callouts compute geometry here)
   *   a_<action>(at, dur, ease, args, beat)   compile one Beat (called in time order)
   *   render(t)          write styles for time t (call super.render(t) for generic state)
   */
  class Primitive {
    static actions = {
      enter: { dur: 0.6, ease: 'out' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 },
      highlight: { dur: 0.35, ease: 'out' }, alert: { dur: 0.35, ease: 'out' }, unhighlight: { dur: 0.3 }, pulse: { dur: 0.6 },
    };
    constructor(scene, def, index) {
      this.scene = scene;
      this.id = def.id;
      this.def = def;
      this.index = index;
      this.props = Object.assign({}, this.constructor.defaults || {}, def.props || {});
      this.vis = new Track(0);       // enter/exit 0..1
      this.dimT = new Track(1);      // dim factor (opacity multiplier)
      this.hlT = new Track(0);       // dashed highlight box 0..1
      this.hlColor = new Events();   // color of highlight box
      this.flashes = [];             // {at, dur, color}
      this.enterAt = null;
      this.cx = 0; this.cy = 0; this.w = 0; this.h = 0;
      this.root = null;
    }
    static allActions() {
      const out = {};
      const chain = [];
      for (let c = this; c && c !== Object; c = Object.getPrototypeOf(c)) chain.unshift(c);
      for (const c of chain) if (Object.prototype.hasOwnProperty.call(c, 'actions')) Object.assign(out, c.actions);
      return out;
    }
    get layerName() { return this.constructor.layer || 'nodes'; }
    build() {}
    afterLayout() {}
    measure() { this.w = this.root.offsetWidth; this.h = this.root.offsetHeight; return { w: this.w, h: this.h }; }
    place(cx, cy) {
      this.cx = Math.round(cx); this.cy = Math.round(cy);
      this.root.style.left = Math.round(this.cx - this.w / 2) + 'px';
      this.root.style.top = Math.round(this.cy - this.h / 2) + 'px';
    }
    get box() { return box(this.cx, this.cy, this.w, this.h); }
    /** Box used for links/routing (may differ from the visual root, e.g. a device without its label). */
    get linkBox() { return this.box; }
    anchor(side, off) { return edgePoint(this.linkBox, side, off); }
    colorFor(name) { return this.scene.colorFor(name); }

    // ---- generic actions
    a_enter(at, dur, e) { this.vis.to(at, 1, dur, e); if (this.enterAt == null || at < this.enterAt) this.enterAt = at; }
    a_exit(at, dur, e) { this.vis.to(at, 0, dur, e); }
    a_dim(at, dur, e, args) { this.dimT.to(at, args.level ?? 0.25, dur, e); }
    a_undim(at, dur, e) { this.dimT.to(at, 1, dur, e); }
    a_highlight(at, dur, e, args) {
      this.hlColor.add(at, { color: args.color === 'red' || args.alert ? this.scene.token('alert', '#F43F5E') : (args.color && args.color !== 'white' ? this.scene.resolveColor(args.color) : '#FFFFFF') });
      this.hlT.to(at, 1, dur, e);
      if (args.hold != null) this.hlT.to(at + dur + args.hold, 0, 0.3, e);
    }
    a_alert(at, dur, e, args) { this.a_highlight(at, dur, e, Object.assign({}, args, { color: 'red' })); this.flash(at, 0.8, this.scene.token('alert', '#F43F5E')); }
    a_unhighlight(at, dur, e) { this.hlT.to(at, 0, dur, e); }
    a_pulse(at, dur, e, args) { this.flash(at, dur, args.color ? this.scene.resolveColor(args.color) : '#FFFFFF'); }
    flash(at, dur, color) { this.flashes.push({ at, dur, color }); }
    /** Strongest active flash at t -> {amt, color} */
    flashAt(t) {
      let best = { amt: 0, color: '#FFFFFF' };
      for (const f of this.flashes) { const a = bump(t, f.at, f.dur); if (a > best.amt) best = { amt: a, color: f.color }; }
      return best;
    }

    /** Generic render: visibility, dimming and highlight box. Subclasses call super.render(t). */
    render(t) {
      const v = this.vis.value(t), d = this.dimT.value(t);
      css(this.root, 'opacity', (v * d).toFixed(3));
      css(this.root, 'visibility', v * d <= 0.001 ? 'hidden' : 'visible');
      this.renderHighlight(t, v);
    }
    renderHighlight(t, v) {
      const h = this.hlT.value(t) * (v ?? 1);
      if (h <= 0.001 && !this._hl) return;
      if (!this._hl) {
        this._hl = svgEl('rect', { fill: 'none', 'stroke-width': 2.5, 'stroke-dasharray': '10 8', rx: 18 }, this.scene.layers.fx);
      }
      const b = this.highlightBox ? this.highlightBox() : this.box;
      const pad = 12 + (1 - h) * 10;
      const c = (this.hlColor.last(t) || { color: '#FFFFFF' }).color;
      attr(this._hl, 'x', (b.x - pad).toFixed(1)); attr(this._hl, 'y', (b.y - pad).toFixed(1));
      attr(this._hl, 'width', (b.w + pad * 2).toFixed(1)); attr(this._hl, 'height', (b.h + pad * 2).toFixed(1));
      attr(this._hl, 'stroke', c);
      attr(this._hl, 'opacity', (h * this.dimT.value(t)).toFixed(3));
      css(this._hl, 'filter', `drop-shadow(0 0 6px ${rgba(c, 0.55)})`);
      marchingAnts(this._hl, t, 28);
    }
  }

  // ------------------------------------------------------------------ scene
  class Scene {
    constructor(spec, look, stage) {
      this.spec = spec;
      this.look = look;
      this.stage = stage;
      const [pw, ph] = spec.size || [1920, 1080];
      const portrait0 = pw / ph < 1.2;
      this.unit = (portrait0 && look.design_short_side_portrait) || look.design_short_side || 1080; // design units: short side
      this.k = Math.min(pw, ph) / this.unit;
      this.W = Math.round(pw / this.k); this.H = Math.round(ph / this.k);
      this.portrait = this.W / this.H < 1.2;
      this.els = new Map();
      this.list = [];
      this.sceneDef = spec.scene || {};
      this._concepts = {};
      this._conceptOrder = 0;
      const sem = look.semantic || {};
      for (const k in sem) this._concepts[k.toLowerCase()] = sem[k];
      const sc = spec.concepts || {};
      for (const k in sc) this._concepts[k.toLowerCase()] = sc[k];
    }
    token(name, fallback) { return (this.look.tokens && this.look.tokens[name]) || fallback; }
    /** Concept Color for a phrase (case-insensitive), or null. */
    colorFor(name) {
      if (!name) return null;
      const k = String(name).toLowerCase().trim();
      if (this._concepts[k]) return this._concepts[k];
      const alt = k.replace(/s$/, '');
      return this._concepts[alt] || null;
    }
    /** Color for a concept, assigning the next concept_palette color if new (deterministic by order). */
    conceptColor(name) {
      const c = this.colorFor(name);
      if (c) return c;
      const pal = this.look.concept_palette || ['#38BDF8'];
      const col = pal[this._conceptOrder++ % pal.length];
      this._concepts[String(name).toLowerCase().trim()] = col;
      return col;
    }
    resolveColor(c) {
      if (!c) return null;
      if (isHex(c)) return c;
      const tok = this.look.tokens && this.look.tokens[c];
      return tok || this.colorFor(c) || c;
    }
    get(id) {
      const e = this.els.get(id);
      if (!e) throw new Error(`Unknown element id "${id}". Known: ${[...this.els.keys()].join(', ')}`);
      return e;
    }
    has(id) { return this.els.has(id); }
    /** Create an element at compile time (e.g. a duplicated token). */
    spawn(def) {
      const Cls = registry[def.primitive];
      if (!Cls) throw new Error(`Unknown primitive "${def.primitive}"`);
      const e = new Cls(this, def, this.list.length);
      this._mount(e);
      e.build();
      e.measure();
      e.afterLayout();
      return e;
    }
    _mount(e) {
      if (this.els.has(e.id)) throw new Error(`Duplicate element id "${e.id}"`);
      this.els.set(e.id, e);
      this.list.push(e);
      const layer = this.layers[e.layerName] || this.layers.nodes;
      e.root = el('div', { class: 'ca-abs ca-' + (e.constructor.primitiveName || 'el').toLowerCase(), 'data-id': e.id }, layer);
    }
    build() {
      const st = this.stage;
      st.style.width = this.W + 'px'; st.style.height = this.H + 'px';
      st.style.zoom = String(this.k);
      const bg = this.spec.transparent ? 'transparent' : ((this.look.canvas && this.look.canvas.background) || '#000');
      st.style.background = bg;
      this.layers = {
        bg: el('div', { class: 'ca-layer', id: 'ca-bg' }, st),
        links: svgEl('svg', { class: 'ca-layer', id: 'ca-links', width: this.W, height: this.H, viewBox: `0 0 ${this.W} ${this.H}` }, st),
        nodes: el('div', { class: 'ca-layer', id: 'ca-nodes' }, st),
        fx: svgEl('svg', { class: 'ca-layer', id: 'ca-fx', width: this.W, height: this.H, viewBox: `0 0 ${this.W} ${this.H}` }, st),
        pills: el('div', { class: 'ca-layer', id: 'ca-pills' }, st),
        text: el('div', { class: 'ca-layer', id: 'ca-text' }, st),
      };
      Object.values(this.layers).forEach((l, i) => { l.style.zIndex = String(i + 1); l.style.isolation = 'isolate'; });
      this.defs = svgEl('defs', {}, this.layers.fx);
      const defs = [];
      const shortcuts = this.look.scene_shortcuts || {};
      for (const key in shortcuts) {
        const v = this.sceneDef[key];
        if (v == null) continue;
        const props = typeof v === 'string' ? { text: v } : v;
        defs.push({ id: key, primitive: shortcuts[key], props });
      }
      for (const d of this.sceneDef.elements || []) defs.push(d);
      for (const d of defs) {
        if (!d.id) throw new Error(`Element without id: ${JSON.stringify(d)}`);
        const Cls = registry[d.primitive];
        if (!Cls) throw new Error(`Unknown primitive "${d.primitive}" (element "${d.id}"). Registered: ${Object.keys(registry).join(', ')}`);
        const e = new Cls(this, d, this.list.length);
        this._mount(e);
      }
      for (const e of this.list) e.build();
      for (const e of this.list) e.measure();
      const layoutName = this.look.layout || 'default';
      if (layouts[layoutName]) layouts[layoutName](this);
      for (const e of this.list) e.afterLayout();
      this.compile();
    }
    compile() {
      const beats = (this.spec.beats || []).map((b, i) => Object.assign({ seq: i }, b));
      // expand array targets
      const flat = [];
      for (const b of beats) {
        const targets = Array.isArray(b.target) ? b.target : [b.target];
        for (const tg of targets) flat.push(Object.assign({}, b, { target: tg }));
      }
      // auto-enter elements without an explicit enter beat
      const hasEnter = new Set(flat.filter((b) => b.action === 'enter').map((b) => b.target));
      const autoEnter = new Map();
      let order = 0;
      const enterOf = (id) => {
        const exp = flat.find((b) => b.action === 'enter' && b.target === id);
        if (exp) return exp.at;
        return autoEnter.get(id);
      };
      for (const e of this.list) {
        const C = e.constructor;
        if (hasEnter.has(e.id) || C.autoEnter === false || e.props.auto === false) continue;
        if (C.enterAfter) continue; // computed below (links wait for their endpoints)
        const at = e.props.enterAt ?? (C.autoEnterAt != null ? C.autoEnterAt : 0.15 + order++ * 0.14);
        autoEnter.set(e.id, at);
      }
      for (const e of this.list) {
        const C = e.constructor;
        if (!C.enterAfter || hasEnter.has(e.id) || e.props.auto === false) continue;
        const deps = C.enterAfter(e).map(enterOf).filter((x) => x != null);
        autoEnter.set(e.id, e.props.enterAt ?? (deps.length ? Math.max(...deps) + 0.25 : 0.2));
      }
      for (const [id, at] of autoEnter) flat.push({ at, action: 'enter', target: id, args: {}, seq: -1, auto: true });
      flat.sort((a, b) => a.at - b.at || (a.seq - b.seq));
      for (const b of flat) this.dispatch(b);
    }
    dispatch(b) {
      const args = b.args || {};
      if (b.target === 'scene') return this.sceneAction(b, args);
      const e = this.get(b.target);
      const acts = e.constructor.allActions();
      const spec = acts[b.action];
      if (!spec || typeof e['a_' + b.action] !== 'function') {
        throw new Error(`${e.constructor.primitiveName} "${e.id}" has no action "${b.action}". Supported: ${Object.keys(acts).join(', ')}`);
      }
      const dur = args.dur ?? spec.dur ?? 0.5;
      const ez = args.ease ?? spec.ease ?? 'smooth';
      e['a_' + b.action](b.at, dur, ez, args, b);
    }
    /** Scene-level actions: focus {ids, level}, unfocus. */
    sceneAction(b, args) {
      const dur = args.dur ?? 0.6;
      const keep = new Set(args.ids || []);
      for (const e of this.list) {
        if (e.constructor.focusExempt || (e.constructor.layer === 'text' && !e.constructor.dimmable)) continue;
        if (b.action === 'focus') {
          let k = keep.has(e.id);
          if (!k && e.relatedIds) k = e.relatedIds().every((id) => keep.has(id));
          e.dimT.to(b.at, k ? 1 : args.level ?? 0.25, dur, 'smooth');
        } else if (b.action === 'unfocus') e.dimT.to(b.at, 1, dur, 'smooth');
        else throw new Error(`Unknown scene action "${b.action}" (supported: focus, unfocus)`);
      }
    }
    seek(t) { for (const e of this.list) e.render(t); }
  }

  // ------------------------------------------------------------------ boot
  function loadScript(src) {
    return new Promise((res, rej) => { const s = el('script', { src }); s.onload = res; s.onerror = () => rej(new Error('Failed to load ' + src)); document.head.appendChild(s); });
  }
  function loadCss(href) {
    return new Promise((res, rej) => { const l = el('link', { rel: 'stylesheet', href }); l.onload = res; l.onerror = () => rej(new Error('Failed to load ' + href)); document.head.appendChild(l); });
  }
  async function fetchJson(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
    return r.json();
  }

  let scene = null;
  const api = { duration: 0, scene: null, errors: [] };
  api.seek = function (t) {
    if (!scene) throw new Error('clipagent: seek() before ready');
    scene.seek(+t);
  };
  api.ready = (async () => {
    const q = new URLSearchParams(location.search);
    const specUrl = q.get('spec');
    if (!specUrl) throw new Error('player.html needs ?spec=<url>');
    const spec = await fetchJson(specUrl);
    api.duration = +spec.duration || 0;
    api.spec = spec;
    const lookBase = q.get('looks') ? new URL(q.get('looks').replace(/\/?$/, '/') + spec.look + '/', location.href) : new URL(`../${spec.look}/`, location.href);
    const look = await fetchJson(new URL('look.json', lookBase));
    look.base = lookBase.href;
    if (spec.transparent) { document.documentElement.classList.add('ca-transparent'); document.body.classList.add('ca-transparent'); }
    await loadCss(new URL('look.css', lookBase).href);
    for (const s of (look.runtime && look.runtime.scripts) || []) await loadScript(new URL(s, lookBase).href);
    await loadScript(new URL('primitives.js', lookBase).href);
    const fams = (look.runtime && look.runtime.preload_fonts) || [];
    await Promise.all(fams.map((f) => document.fonts.load(f).catch(() => null)));
    await document.fonts.ready;
    const stage = document.getElementById('ca-stage');
    scene = new Scene(spec, look, stage);
    api.scene = scene;
    scene.build();
    scene.seek(0);
    const t0 = q.get('t');
    if (t0 != null) scene.seek(+t0);
    if (q.get('play')) { // preview only: never used by the frame renderer
      const start = performance.now();
      const loop = () => { const t = ((performance.now() - start) / 1000) % api.duration; scene.seek(t); requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
    }
  })();
  api.ready.catch((err) => {
    api.errors.push(String(err && err.stack || err));
    const box_ = document.getElementById('ca-error') || el('div', { id: 'ca-error' }, document.body);
    box_.textContent = 'ClipAgent runtime error:\n' + (err && err.stack || err);
    console.error(err);
  });
  window.clipagent = api;

  Object.assign(CA, {
    // easing & math
    ease, getEase, cubicBezier, clamp, lerp, prog, bump,
    // colors
    hexToRgb, rgbToHex, mixColor, rgba, isHex, lerpValue,
    // time
    Track, Events, SpeedProfile, streamPositions,
    // randomness
    rng, hashStr, noise,
    // dom
    el, svgEl, css, attr, text, SVGNS,
    // paths
    PathLUT, roundedPolyline, drawOn, marchingAnts, morph, route, edgePoint, box,
    // text & numbers
    splitWords, revealWords, revealDuration, counter, formatNumber, parseNumber,
    // primitives
    Primitive, register, registerLayout, registry, layouts, Scene,
  });
})();
