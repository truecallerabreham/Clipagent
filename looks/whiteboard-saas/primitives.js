/* whiteboard-saas Look: Primitives. Scene vocabulary is documented in PRIMITIVES.md.
 *
 * Everything is compiled from Beats into tracks/schedules at build time; render(t) is pure.
 * The drawing hand is one shared layer (HandLayer, spawned by the layout): every drawing
 * operation (an SVG stroke, a handwritten word, a color-fill wipe) registers a "pen session"
 * {t0, t1, penAt(t)}; the hand's tip is locked to the active session's pen position, travels
 * between close sessions, and slides off-screen (down-right) when nothing is being drawn.
 */
(function () {
  'use strict';
  const CA = window.CA;
  const {
    Primitive, Track, Events, PathLUT, register, registerLayout, el, svgEl, css, attr,
    clamp, lerp, prog, bump, getEase, ease, mixColor, drawOn, splitWords, rng, box, formatNumber, parseNumber,
  } = CA;

  const INK = '#111111', ACCENT = '#5E17EB', PILL = '#1E1E1E', MUTED = '#9CA3AF';
  const SLOTS = {
    INK: '#111111', A: '#5E17EB', A2: '#E4D6FF', Y: '#FACC15', Y2: '#FEF3C7', G: '#22C55E', G2: '#DCFCE7',
    R: '#EF4444', R2: '#FEE2E2', B: '#60A5FA', B2: '#DBEAFE', GR: '#E5E7EB', W: '#FFFFFF',
  };
  const SKINS = {
    light: { SKIN: '#F4C6A3', SHADE: '#E3A27C', LINE: '#B4744F', NAIL: '#FBE3D2' },
    medium: { SKIN: '#DDA47C', SHADE: '#C68760', LINE: '#93593A', NAIL: '#EEC7AA' },
    tan: { SKIN: '#B97D57', SHADE: '#9E6544', LINE: '#6E4128', NAIL: '#D8A88A' },
    deep: { SKIN: '#7B4B32', SHADE: '#643B26', LINE: '#3F2214', NAIL: '#A97A62' },
  };
  const ENTRY = new Set(['enter', 'draw', 'write', 'place', 'reveal']);

  // ------------------------------------------------------------------ helpers
  const tint = (c, a = 0.84) => mixColor(c, '#FFFFFF', a);
  /** numbers in [-1, 1] are fractions of `total`, anything else is design px. */
  const frac = (v, total) => (v == null ? null : Math.abs(v) <= 1 ? v * total : v);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function color(scene, c, fb) { if (c == null || c === '' || c === false) return fb; return scene.resolveColor(c) || fb; }
  /** Deterministic soft shadow (no blur filter, so frames are identical however they are reached):
   *  stacked, offset, low-opacity silhouettes of the art, under the art itself. */
  function withShadow(markup, k = 1) {
    let out = '';
    for (let i = 1; i <= 9; i++) out += `<g class="wb-shadow" opacity="0.026" transform="translate(${(1.8 * i * k).toFixed(1)} ${(2.9 * i * k).toFixed(1)})">${markup}</g>`;
    return out + markup;
  }
  function relBox(node, root) {
    let x = 0, y = 0;
    for (let e = node; e && e !== root; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
    return { x, y, w: node.offsetWidth, h: node.offsetHeight };
  }
  function wb(scene) {
    if (!scene._wb) {
      const h = (scene.sceneDef && scene.sceneDef.hand) || {};
      scene._wb = { sessions: [], hand: h, handEnabled: h.enabled !== false };
    }
    return scene._wb;
  }
  /** Register a pen session for the shared drawing hand. */
  function addSession(scene, t0, t1, penAt, ink) {
    if (!(t1 - t0 > 1e-3)) return;
    wb(scene).sessions.push({ t0, t1, penAt, ink: ink || INK });
  }
  function flatBeats(scene) {
    const out = [];
    for (const b of scene.spec.beats || []) for (const tg of [].concat(b.target)) out.push(Object.assign({}, b, { target: tg }));
    return out;
  }
  /** Resolve a reference to a stage box: "id", "id.part", [x, y] (point), {x, y} (point) or {x, y, w, h} (region, x/y top-left). */
  function refBox(scene, ref) {
    const W = scene.W, H = scene.H;
    if (Array.isArray(ref)) return box(frac(ref[0], W), frac(ref[1], H), 0, 0);
    if (ref && typeof ref === 'object') {
      if (ref.w != null || ref.h != null) {
        const w = frac(ref.w || 0, W), h = frac(ref.h || 0, H);
        return box(frac(ref.x || 0, W) + w / 2, frac(ref.y || 0, H) + h / 2, w, h);
      }
      return box(frac(ref.x, W), frac(ref.y, H), 0, 0);
    }
    const s = String(ref), i = s.indexOf('.');
    const id = i > 0 ? s.slice(0, i) : s, part = i > 0 ? s.slice(i + 1) : null;
    const e = scene.get(id);
    if (part) {
      if (!e.partBox) throw new Error(`"${id}" (${e.constructor.primitiveName}) has no parts; cannot resolve "${s}"`);
      return e.partBox(part);
    }
    return e.visualBox ? e.visualBox() : e.box;
  }
  const refId = (r) => (typeof r === 'string' ? r.split('.')[0] : null);
  /** Point on the border of box b in the direction of (px, py), pushed out by gap. */
  function edgeToward(b, px, py, gap = 0) {
    let dx = px - b.cx, dy = py - b.cy;
    const L = Math.hypot(dx, dy) || 1; dx /= L; dy /= L;
    let k = 0;
    if (b.w > 0 || b.h > 0) {
      const kx = Math.abs(dx) > 1e-6 ? (b.w / 2) / Math.abs(dx) : Infinity;
      const ky = Math.abs(dy) > 1e-6 ? (b.h / 2) / Math.abs(dy) : Infinity;
      k = Math.min(kx, ky);
    }
    return [b.cx + dx * (k + gap), b.cy + dy * (k + gap)];
  }
  function roundRectD(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    return `M${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${y + h - r} Q${x + w},${y + h} ${x + w - r},${y + h} ` +
      `L${x + r},${y + h} Q${x},${y + h} ${x},${y + h - r} L${x},${y + r} Q${x},${y} ${x + r},${y}`;
  }
  /** A hand-drawn loop around a box: a little more than one turn, slightly spiralling. */
  function loopD(cx, cy, rx, ry, seed) {
    const r = rng(seed), a0 = -2.6 + r() * 0.3, turn = Math.PI * 2 * 1.08, n = 72;
    const pts = [];
    for (let i = 0; i <= n; i++) {
      const u = i / n, a = a0 + turn * u, k = 0.97 + 0.07 * u;
      pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
    }
    return 'M' + pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L');
  }
  function arrowHeadD(tip, angle, size) {
    const a1 = angle + Math.PI * 0.82, a2 = angle - Math.PI * 0.82;
    return `M${(tip[0] + Math.cos(a1) * size).toFixed(1)},${(tip[1] + Math.sin(a1) * size).toFixed(1)} L${tip[0].toFixed(1)},${tip[1].toFixed(1)} L${(tip[0] + Math.cos(a2) * size).toFixed(1)},${(tip[1] + Math.sin(a2) * size).toFixed(1)}`;
  }

  // ------------------------------------------------------------------ ink paths
  /** One stroke drawn on over time (solid via dashoffset, dashed via partial path). */
  class InkPath {
    constructor(host, parent, d, o = {}) {
      this.host = host; this.o = o; this.d = d;
      this.color = o.color || INK;
      this.el = svgEl('path', { d, fill: 'none', stroke: this.color, 'stroke-width': o.width || 6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', visibility: 'hidden' }, parent);
      if (o.dashed) attr(this.el, 'stroke-dasharray', o.dashed === true ? '15 13' : String(o.dashed));
      this.lut = PathLUT.fromPath(d, 2.5);
      this.len = this.lut.length;
      this.origin = o.origin || (() => host.origin());
      this.t0 = null;
    }
    schedule(t0, dur, hand, e = 'inOut') {
      if (this.t0 != null) return;
      this.t0 = t0; this.dur = Math.max(0.01, dur); this.ez = getEase(e);
      if (hand) addSession(this.host.scene, t0, t0 + this.dur, (t) => this.penAt(t), this.color);
    }
    p(t) { return this.t0 == null ? 0 : this.ez(clamp((t - this.t0) / this.dur)); }
    penAt(t) { const q = this.lut.at(this.p(t) * this.len); const [ox, oy] = this.origin(); return { x: ox + q.x, y: oy + q.y }; }
    render(t) {
      const p = this.p(t);
      if (this.o.dashed) {
        attr(this.el, 'visibility', p <= 0.001 ? 'hidden' : 'visible');
        attr(this.el, 'd', p >= 1 ? this.d : (this.lut.partialD(0, p * this.len) || 'M0,0'));
      } else drawOn(this.el, p);
    }
  }

  // ------------------------------------------------------------------ angled color-fill wipe
  class Wipe {
    /** region {x,y,w,h} in local coords; o.toStage(x, y) -> stage point for the hand; o.angle in degrees. */
    constructor(region, o = {}) {
      const a = ((o.angle ?? 24) * Math.PI) / 180;
      this.u = [Math.cos(a), Math.sin(a)]; this.v = [-Math.sin(a), Math.cos(a)];
      const { x, y, w, h } = region;
      this.c = [x + w / 2, y + h / 2];
      const cs = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]];
      const pu = cs.map((q) => (q[0] - this.c[0]) * this.u[0] + (q[1] - this.c[1]) * this.u[1]);
      const pv = cs.map((q) => (q[0] - this.c[0]) * this.v[0] + (q[1] - this.c[1]) * this.v[1]);
      this.pmin = Math.min(...pu) - 2; this.pmax = Math.max(...pu) + 2; this.vext = Math.max(...pv.map(Math.abs));
      this.o = o; this.t0 = null;
    }
    schedule(t0, dur, host, hand, ink) {
      if (this.t0 != null) return;
      this.t0 = t0; this.dur = Math.max(0.05, dur);
      if (hand) addSession(host.scene, t0, t0 + this.dur, (t) => this.pen(t), ink);
    }
    p(t) { return this.t0 == null ? 0 : ease.inOut(clamp((t - this.t0) / this.dur)); }
    poly(t) {
      const q = this.p(t);
      if (q <= 0) return null;
      if (q >= 1) return 'all';
      const f = this.pmin + (this.pmax - this.pmin) * q, B = 1e4;
      const [cx, cy] = this.c, [ux, uy] = this.u, [vx, vy] = this.v;
      return [[cx + ux * f + vx * B, cy + uy * f + vy * B], [cx + ux * f - vx * B, cy + uy * f - vy * B],
        [cx - ux * B - vx * B, cy - uy * B - vy * B], [cx - ux * B + vx * B, cy - uy * B + vy * B]];
    }
    svgPoints(t) {
      const P = this.poly(t);
      if (!P) return '0,0 0,0 0,0';
      if (P === 'all') return '-100000,-100000 100000,-100000 100000,100000 -100000,100000';
      return P.map((q) => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ');
    }
    cssClip(t) {
      const P = this.poly(t);
      if (!P) return 'polygon(0px 0px, 0px 0px, 0px 0px)';
      if (P === 'all') return 'none';
      return 'polygon(' + P.map((q) => `${q[0].toFixed(1)}px ${q[1].toFixed(1)}px`).join(', ') + ')';
    }
    pen(t) {
      const q = this.p(t), f = this.pmin + 6 + (this.pmax - this.pmin - 12) * q;
      const z = Math.sin(q * Math.PI * (this.o.zig ?? 7)) * this.vext * 0.42;
      const x = this.c[0] + this.u[0] * f + this.v[0] * z, y = this.c[1] + this.u[1] * f + this.v[1] * z;
      return this.o.toStage(x, y);
    }
  }

  // ------------------------------------------------------------------ SVG art drawing engine
  function localMatrix(g, svg) {
    let m = svg.createSVGMatrix();
    for (let n = g; n && n !== svg; n = n.parentNode) {
      const tl = n.transform && n.transform.baseVal;
      if (tl && tl.numberOfItems) { const c = tl.consolidate(); if (c) m = c.matrix.multiply(m); }
    }
    return m;
  }
  const isIdent = (m) => Math.abs(m.a - 1) < 1e-6 && Math.abs(m.d - 1) < 1e-6 && Math.abs(m.b) < 1e-6 && Math.abs(m.c) < 1e-6 && Math.abs(m.e) < 1e-6 && Math.abs(m.f) < 1e-6;

  /** Draws any SVG: every stroked shape is drawn on in document order (pen lifts between strokes),
   *  every filled shape is revealed afterwards by one angled wipe (fills keep their stacking order). */
  class Drawing {
    constructor(host, svg, o) {
      this.host = host; this.svg = svg; this.o = o;
      this.strokes = []; this.fills = []; this.polys = [];
      const vb = svg.viewBox.baseVal;
      this.vb = { x: vb.x, y: vb.y, w: vb.width || 200, h: vb.height || 200 };
      const defs = svgEl('defs', {}, svg);
      const mkClip = (m) => {
        const id = 'wbclip' + (++Drawing.N);
        const cp = svgEl('clipPath', { id, clipPathUnits: 'userSpaceOnUse' }, defs);
        const poly = svgEl('polygon', { points: '0,0 0,0 0,0' }, cp);
        if (m) attr(poly, 'transform', `matrix(${m.a} ${m.b} ${m.c} ${m.d} ${m.e} ${m.f})`);
        this.polys.push(poly);
        return id;
      };
      const main = mkClip(null), byKey = new Map();
      const geo = [...svg.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect')].filter((g) => !g.closest('defs'));
      for (const g of geo) {
        const cs = getComputedStyle(g);
        const sw = parseFloat(cs.strokeWidth) || 0;
        const hasFill = cs.fill && cs.fill !== 'none' && !/,\s*0\)$/.test(cs.fill);
        const hasStroke = cs.stroke && cs.stroke !== 'none' && sw > 0;
        const white = hasStroke && cs.stroke === 'rgb(255, 255, 255)'; // highlights: revealed with the fill
        const m = localMatrix(g, svg);
        const clipId = () => {
          if (isIdent(m)) return main;
          const k = [m.a, m.b, m.c, m.d, m.e, m.f].map((v) => v.toFixed(4)).join(',');
          if (!byKey.has(k)) byKey.set(k, mkClip(m.inverse()));
          return byKey.get(k);
        };
        if (hasFill && hasStroke && !white) {
          const c = g.cloneNode(false);
          c.setAttribute('stroke', 'none'); c.style.stroke = 'none';
          c.setAttribute('clip-path', `url(#${clipId()})`);
          g.parentNode.insertBefore(c, g);
          g.setAttribute('fill', 'none'); g.style.fill = 'none';
          this.fills.push(c);
        } else if (hasFill || white) {
          g.setAttribute('clip-path', `url(#${clipId()})`);
          this.fills.push(g);
        }
        if (hasStroke && !white) {
          const len = g.getTotalLength();
          if (!(len > 0.5)) continue;
          const n = Math.max(2, Math.ceil(len / 3)), pts = [];
          for (let i = 0; i <= n; i++) {
            const q = g.getPointAtLength((len * i) / n);
            pts.push([m.a * q.x + m.c * q.y + m.e, m.b * q.x + m.d * q.y + m.f]);
          }
          this.strokes.push({ el: g, len, lut: PathLUT.fromPoints(pts), color: cs.stroke, t0: null, t1: null });
          attr(g, 'visibility', 'hidden');
        }
      }
      this.fillInk = this.fills.length ? getComputedStyle(this.fills[0]).fill : INK;
      this.strokeLen = this.strokes.reduce((a, s) => a + s.lut.length, 0);
      // the wipe sweeps only the area covered by fills (so the coloring hand stays on the drawing)
      let fb = null;
      for (const f of this.fills) {
        let b; try { b = f.getBBox(); } catch (e) { continue; }
        const m = localMatrix(f, svg);
        for (const [x, y] of [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]]) {
          const X = m.a * x + m.c * y + m.e, Y = m.b * x + m.d * y + m.f;
          fb = fb ? { x0: Math.min(fb.x0, X), y0: Math.min(fb.y0, Y), x1: Math.max(fb.x1, X), y1: Math.max(fb.y1, Y) } : { x0: X, y0: Y, x1: X, y1: Y };
        }
      }
      const reg = fb ? { x: fb.x0 - 6, y: fb.y0 - 6, w: fb.x1 - fb.x0 + 12, h: fb.y1 - fb.y0 + 12 } : this.vb;
      this.wipe = new Wipe(reg, { angle: o.angle, toStage: (x, y) => this.toStage(x, y) });
      this.sched = false;
    }
    toStage(x, y) { const [ox, oy] = this.o.origin(); const s = this.o.scale(); return { x: ox + (x - this.vb.x) * s, y: oy + (y - this.vb.y) * s }; }
    estDur(fill = true) {
      const s = this.o.scale(), L = this.strokeLen * s, size = this.vb.w * s;
      return clamp(0.2 + L / 1350, 0.35, 5) + (fill && this.fills.length ? clamp(size / 520, 0.28, 0.6) : 0);
    }
    /** Draw all strokes in [t0, t0 + dur]; the last part of dur is the fill wipe (if any). */
    schedule(t0, dur, o = {}) {
      if (this.sched) return;
      this.sched = true;
      const fillOn = o.fill !== false && this.fills.length > 0;
      const fillDur = fillOn ? clamp(dur * 0.26, 0.25, 0.7) : 0;
      const sDur = Math.max(0.1, dur - fillDur);
      const lifts = [];
      let cost = 0;
      this.strokes.forEach((s, i) => {
        cost += s.lut.length;
        if (i) {
          const a = this.strokes[i - 1].lut.at(1e9), b = s.lut.at(0);
          lifts[i] = 8 + Math.hypot(b.x - a.x, b.y - a.y) * 0.35;
          cost += lifts[i];
        }
      });
      const k = sDur / Math.max(1, cost);
      let t = t0;
      this.strokes.forEach((s, i) => {
        if (i) t += lifts[i] * k;
        s.t0 = t; s.t1 = t + s.lut.length * k; t = s.t1;
        if (o.hand) addSession(this.host.scene, s.t0, s.t1, (tt) => this.penAt(s, tt), s.color);
      });
      if (fillOn) this.wipe.schedule(t0 + sDur + 0.02, fillDur, this.host, o.hand, this.fillInk);
      this.t1 = t0 + dur;
    }
    scheduleFill(t0, dur, hand) { this.wipe.schedule(t0, dur, this.host, hand, this.fillInk); }
    sp(s, t) { return s.t0 == null ? 0 : ease.inOut(clamp((t - s.t0) / Math.max(1e-3, s.t1 - s.t0))); }
    penAt(s, t) { const q = s.lut.at(this.sp(s, t) * s.lut.length); return this.toStage(q.x, q.y); }
    render(t) {
      for (const s of this.strokes) drawOn(s.el, this.sp(s, t), s.len);
      const pts = this.wipe.svgPoints(t);
      for (const p of this.polys) attr(p, 'points', pts);
    }
  }
  Drawing.N = 0;

  /** Build the art markup (kit name, raw svg, or a list of paths) and mount it as <svg class="wb-art">. */
  function mountArt(scene, parent, p, width) {
    const slots = Object.assign({}, SLOTS);
    if (p.accent) { const a = color(scene, p.accent, ACCENT); slots.A = a; slots.A2 = tint(a, 0.8); }
    if (p.colors) for (const k in p.colors) slots[k] = color(scene, p.colors[k], slots[k]);
    if (p.ink) slots.INK = color(scene, p.ink, INK);
    const fillSlots = (s) => String(s).replace(/\{\{(\w+)\}\}/g, (_, k) => slots[k] || '#000');
    let svg;
    if (p.svg) {
      const tmp = document.createElement('div');
      tmp.innerHTML = fillSlots(p.svg).trim();
      svg = tmp.querySelector('svg');
      if (!svg) throw new Error('HandDraw "svg" must contain an <svg> element');
      parent.appendChild(svg);
      if (!svg.getAttribute('viewBox')) svg.setAttribute('viewBox', `0 0 ${parseFloat(svg.getAttribute('width')) || 200} ${parseFloat(svg.getAttribute('height')) || 200}`);
    } else {
      let vbs = '0 0 200 200', inner;
      if (p.paths) {
        vbs = p.viewBox || vbs;
        inner = p.paths.map((q) => {
          const d = typeof q === 'string' ? { d: q } : q;
          const st = d.stroke === false ? '' : `stroke="${esc(d.stroke ? color(scene, d.stroke, slots.INK) : slots.INK)}"`;
          return `<path d="${esc(d.d)}" fill="${d.fill ? esc(color(scene, d.fill, d.fill)) : 'none'}" ${st} ${d.width ? `stroke-width="${+d.width}"` : ''}/>`;
        }).join('');
      } else {
        const src = (window.WB_ART || {})[p.art];
        if (!src) throw new Error(`Unknown art "${p.art}". Available: ${Object.keys(window.WB_ART || {}).join(', ')}`);
        inner = fillSlots(src);
      }
      svg = svgEl('svg', { viewBox: vbs }, parent);
      svg.innerHTML = inner;
    }
    const vb = svg.viewBox.baseVal;
    const h = (width * vb.height) / vb.width;
    svg.setAttribute('width', width); svg.setAttribute('height', h);
    svg.setAttribute('class', 'wb-art');
    if (!svg.getAttribute('stroke-width')) svg.setAttribute('stroke-width', p.strokeWidth ?? +((clamp(width * 0.034, 4.2, 10) * vb.width) / width).toFixed(2));
    return { svg, w: width, h, vbw: vb.width };
  }

  // ------------------------------------------------------------------ handwriting
  /** Handwritten text revealed word by word with a moving clip; the pen rides the reveal edge. */
  class Writer {
    constructor(host, parent, str, o = {}) {
      this.host = host; this.o = o; this.words = []; this.t0 = null;
      String(str).split('\n').forEach((ln) => {
        const d = el('div', { class: 'wb-line' }, parent);
        const spans = splitWords(d, ln, { colorFor: (w) => host.scene.colorFor(w), emphasisColor: o.emphasisColor });
        if (!spans.length) d.innerHTML = '&nbsp;';
        for (const s of spans) { this.words.push({ span: s, chars: Math.max(1, s.textContent.length) }); css(s, 'visibility', 'hidden'); }
      });
      this.chars = this.words.reduce((a, w) => a + w.chars, 0);
    }
    measure(root) { for (const w of this.words) w.b = relBox(w.span, root); }
    estDur() { return clamp(0.2 + this.chars * (this.o.charTime ?? 0.055), 0.4, 7); }
    schedule(t0, dur, hand) {
      if (this.t0 != null || !this.words.length) return;
      this.t0 = t0;
      const units = this.words.reduce((a, w, i) => a + w.chars + (i ? 1.1 : 0), 0);
      const k = dur / units;
      let t = t0;
      this.words.forEach((w, i) => {
        if (i) t += 1.1 * k;
        w.t0 = t; w.t1 = t + w.chars * k; t = w.t1;
        if (hand) addSession(this.host.scene, w.t0, w.t1, (tt) => this.penAt(w, tt), w.span.style.color || (w.span.firstChild && w.span.firstChild.style && w.span.firstChild.style.color) || this.o.ink || INK);
      });
      this.t1 = t;
    }
    penAt(w, t) {
      const p = clamp((t - w.t0) / Math.max(1e-3, w.t1 - w.t0));
      const [ox, oy] = this.o.origin ? this.o.origin() : this.host.origin();
      const b = w.b, ph = p * w.chars * 2.3 * Math.PI;
      return { x: ox + b.x + b.w * p, y: oy + b.y + b.h * (0.6 + 0.16 * Math.sin(ph)) };
    }
    render(t) {
      for (const w of this.words) {
        const p = this.t0 == null ? 0 : clamp((t - w.t0) / Math.max(1e-3, w.t1 - w.t0));
        css(w.span, 'visibility', p <= 0 ? 'hidden' : 'visible');
        css(w.span, 'clipPath', p >= 1 ? 'none' : `inset(-45% ${((1 - p) * 100).toFixed(2)}% -45% -15%)`);
      }
    }
    /** Union box (root-local) of all words, or of the words matching `match` (case/punctuation-insensitive). */
    box(match) {
      const norm = (s) => s.toLowerCase().replace(/[^a-z0-9$%]/g, '');
      let ws = this.words;
      if (match) {
        const want = String(match).split(/\s+/).map(norm);
        const toks = ws.map((w) => norm(w.span.textContent));
        let found = -1;
        for (let i = 0; i + want.length <= toks.length && found < 0; i++) if (want.every((x, j) => toks[i + j] === x)) found = i;
        if (found < 0) throw new Error(`"${match}" not found in text "${ws.map((w) => w.span.textContent).join(' ')}"`);
        ws = ws.slice(found, found + want.length);
      }
      const x0 = Math.min(...ws.map((w) => w.b.x)), y0 = Math.min(...ws.map((w) => w.b.y));
      const x1 = Math.max(...ws.map((w) => w.b.x + w.b.w)), y1 = Math.max(...ws.map((w) => w.b.y + w.b.h));
      return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
  }

  // ------------------------------------------------------------------ base for placed elements
  class WBNode extends Primitive {
    static isNode = true;
    static actions = { pop: { dur: 0.5 } };
    constructor(...a) { super(...a); this.pops = []; }
    get handOn() { return this.props.hand !== false && wb(this.scene).handEnabled; }
    origin() { return [this.cx - this.w / 2, this.cy - this.h / 2]; }
    autoDur() { return 0.6; }
    a_highlight(at, dur, e, args) {
      this.hlColor.add(at, { color: color(this.scene, args.color, ACCENT) });
      this.hlT.to(at, 1, dur, e);
      if (args.hold != null) this.hlT.to(at + dur + args.hold, 0, 0.3, e);
    }
    a_pop(at, dur) { this.pops.push({ at, dur }); }
    a_pulse(at, dur) { this.a_pop(at, dur); }
    popScale(t) { let k = 1; for (const p of this.pops) k += 0.08 * bump(t, p.at, p.dur); return k; }
    renderHighlight(t, v) {
      const h = this.hlT.value(t) * (v ?? 1);
      if (h <= 0.001 && !this._hl) return;
      if (!this._hl) this._hl = svgEl('rect', { fill: 'none', 'stroke-width': 4.5, 'stroke-dasharray': '16 11', 'stroke-linecap': 'round', rx: 18 }, this.scene.layers.fx);
      const b = this.visualBox ? this.visualBox() : this.box;
      const pad = 18 + (1 - h) * 14;
      const c = (this.hlColor.last(t) || { color: ACCENT }).color;
      attr(this._hl, 'x', (b.x - pad).toFixed(1)); attr(this._hl, 'y', (b.y - pad).toFixed(1));
      attr(this._hl, 'width', (b.w + pad * 2).toFixed(1)); attr(this._hl, 'height', (b.h + pad * 2).toFixed(1));
      attr(this._hl, 'stroke', c);
      attr(this._hl, 'opacity', (h * this.dimT.value(t)).toFixed(3));
      attr(this._hl, 'visibility', h <= 0.001 ? 'hidden' : 'visible');
      attr(this._hl, 'stroke-dashoffset', (-t * 36).toFixed(2));
    }
    render(t) {
      super.render(t);
      const k = this.popScale(t);
      css(this.root, 'transform', k === 1 ? 'none' : `scale(${k.toFixed(4)})`);
    }
  }

  // ------------------------------------------------------------------ HandLayer (the shared drawing hand)
  class HandLayer extends Primitive {
    static layer = 'text';
    static autoEnter = false;
    static focusExempt = true;
    build() {
      const o = wb(this.scene).hand;
      const skin = typeof o.skin === 'string' && SKINS[o.skin] ? SKINS[o.skin] : SKINS.light;
      const sleeve = color(this.scene, o.sleeve, '#2A2A31');
      css(this.root, 'zIndex', '40');
      css(this.root, 'transformOrigin', '0 0');
      this.svg = svgEl('svg', { width: 10, height: 10, style: { overflow: 'visible', position: 'absolute', left: '0px', top: '0px' } }, this.root);
      this.svg.innerHTML = withShadow(window.WB_HANDS.paint('marker', Object.assign({}, skin, { SLEEVE: sleeve, CUFF: color(this.scene, wb(this.scene).hand.cuff, ACCENT), INK: '#010203' })));
      this.inks = [...this.svg.querySelectorAll('[fill="#010203"]')];
      this.k = (o.scale ?? 1) * 1.12;
      this.sessions = null;
    }
    measure() { this.w = 0; this.h = 0; return { w: 0, h: 0 }; }
    /** Off-screen point for a pen position: pulled back down-right along the arm. */
    off(p) {
      const dx = 0.5, dy = 0.866, W = this.scene.W, H = this.scene.H;
      const k = Math.min((W + 90 - p.x) / dx, (H + 90 - p.y) / dy);
      const d = Math.max(60, Math.min(k, Math.max(W, H))) + 60;
      return { x: p.x + dx * d, y: p.y + dy * d };
    }
    pose(t) {
      const S = this.sessions;
      let act = null, prev = null, next = null;
      for (const s of S) {
        if (s.t0 <= t && t <= s.t1) act = s;
        if (s.t1 < t && (!prev || s.t1 > prev.t1)) prev = s;
        if (s.t0 > t && (!next || s.t0 < next.t0)) next = s;
      }
      if (act) { const p = act.penAt(t); return { x: p.x, y: p.y, ink: act.ink, lift: 0 }; }
      const TRAVEL = 1.15, OUT = 0.5;
      if (prev && next && next.t0 - prev.t1 <= TRAVEL) {
        const a = prev.penAt(prev.t1), b = next.penAt(next.t0);
        const u = (t - prev.t1) / (next.t0 - prev.t1), e = ease.inOut(u);
        const dist = Math.hypot(b.x - a.x, b.y - a.y);
        return { x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), ink: u < 0.5 ? prev.ink : next.ink, lift: Math.sin(Math.PI * u) * Math.min(1, dist / 160) };
      }
      if (prev && t - prev.t1 < OUT) {
        const a = prev.penAt(prev.t1), b = this.off(a), e = ease.in((t - prev.t1) / OUT);
        return { x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e), ink: prev.ink, lift: Math.min(1, e * 3) };
      }
      if (next && next.t0 - t < OUT) {
        const a = next.penAt(next.t0), b = this.off(a), e = ease.out(1 - (next.t0 - t) / OUT);
        return { x: lerp(b.x, a.x, e), y: lerp(b.y, a.y, e), ink: next.ink, lift: Math.min(1, (1 - e) * 3) };
      }
      return null;
    }
    render(t) {
      if (!this.sessions) this.sessions = wb(this.scene).sessions.slice().sort((a, b) => a.t0 - b.t0);
      const P = this.sessions.length ? this.pose(t) : null;
      css(this.root, 'visibility', P ? 'visible' : 'hidden');
      if (!P) return;
      const rot = (P.x / this.scene.W - 0.5) * 14 - 2;
      const s = this.k * (1 + 0.04 * P.lift);
      css(this.root, 'transform', `translate(${P.x.toFixed(2)}px, ${(P.y - P.lift * 12).toFixed(2)}px) rotate(${rot.toFixed(2)}deg) scale(${s.toFixed(4)})`);
      if (P.ink !== this._ink) { this._ink = P.ink; for (const e of this.inks) e.setAttribute('fill', P.ink); }
    }
  }

  // ------------------------------------------------------------------ HandDraw (+ Icon)
  class HandDraw extends WBNode {
    static defaults = { art: 'lightbulb', svg: null, paths: null, viewBox: null, size: 300, label: null, labelSize: 46, labelColor: null, colors: null, accent: null, ink: null, strokeWidth: null, fill: true, hand: true, angle: 24, drawn: false };
    static actions = { enter: {}, draw: {}, fill: { dur: 0.6 }, exit: { dur: 0.45 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props;
      this.root.classList.add('wb-handdraw');
      const size = frac(p.size, this.scene.unit);
      this.wrap = el('div', { style: { width: size + 'px', margin: '0 auto' } }, this.root);
      this.art = mountArt(this.scene, this.wrap, p, size);
      if (p.label) {
        this.lab = el('div', { class: 'wb-hand', style: { fontSize: p.labelSize + 'px', textAlign: 'center', marginTop: '14px', color: color(this.scene, p.labelColor, INK) } }, this.root);
        this.writer = new Writer(this, this.lab, p.label, { emphasisColor: ACCENT });
      }
      const sc = size / this.art.vbw;
      this.drawing = new Drawing(this, this.art.svg, {
        angle: p.angle, scale: () => sc,
        origin: () => { const [ox, oy] = this.origin(); return [ox + this.wrapOff.x, oy + this.wrapOff.y]; },
      });
    }
    measure() {
      const r = super.measure();
      this.wrapOff = relBox(this.wrap, this.root);
      if (this.writer) this.writer.measure(this.root);
      return r;
    }
    autoDur() { return this.props.drawn ? 0.5 : this.drawing.estDur(this.props.fill) + (this.writer ? this.writer.estDur() + 0.15 : 0); }
    a_enter(at, dur, e, args) {
      const p = this.props;
      if (this.enterAt != null) return;
      this.enterAt = at;
      if (p.drawn || args.instant) {
        this.vis.to(at, 1, args.dur ?? 0.5, 'out');
        this.drawing.schedule(at - 1, 0.01, { fill: p.fill, hand: false });
        if (this.writer) this.writer.schedule(at - 1, 0.01, false);
        return;
      }
      this.vis.to(at, 1, 0.01, 'linear');
      const D = args.dur ?? this.autoDur();
      const lw = this.writer ? Math.min(this.writer.estDur(), D * 0.4) : 0;
      const dd = Math.max(0.4, D - lw - (this.writer ? 0.15 : 0));
      this.drawing.schedule(at, dd, { fill: p.fill, hand: this.handOn });
      if (this.writer) this.writer.schedule(at + dd + 0.15, Math.max(0.3, lw), this.handOn);
    }
    a_draw(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_fill(at, dur) { this.drawing.scheduleFill(at, dur, this.handOn); }
    render(t) {
      super.render(t);
      this.drawing.render(t);
      if (this.writer) this.writer.render(t);
    }
  }
  class Icon extends HandDraw {
    static defaults = Object.assign({}, HandDraw.defaults, { art: 'check', size: 180, labelSize: 40 });
  }

  // ------------------------------------------------------------------ SketchText
  class SketchText extends WBNode {
    static defaults = { text: '', size: 64, color: null, weight: 700, align: 'center', width: null, emphasis: 'accent', underline: false, underlineColor: null, hand: true, charTime: 0.055 };
    static actions = { enter: {}, write: {}, underline: { dur: 0.5 }, circle: { dur: 0.75 }, strike: { dur: 0.45 }, exit: { dur: 0.4 }, pop: { dur: 0.5 } };
    constructor(scene, def, index) {
      super(scene, def, index);
      if (def.id === 'title') {
        const dp = def.props || {};
        if (dp.size == null) this.props.size = 76;
        if (dp.underline == null) this.props.underline = true;
      }
      this.marks = [];
    }
    build() {
      const p = this.props, S = this.scene;
      this.root.classList.add('wb-hand', 'wb-sketch');
      Object.assign(this.root.style, { fontSize: p.size + 'px', fontWeight: String(p.weight), color: color(S, p.color, INK), textAlign: p.align });
      if (p.width) Object.assign(this.root.style, { maxWidth: frac(p.width, S.W) + 'px', whiteSpace: 'normal' });
      this.emColor = color(S, p.emphasis, ACCENT);
      this.txt = el('div', {}, this.root);
      this.writer = new Writer(this, this.txt, p.text, { emphasisColor: this.emColor, ink: color(S, p.color, INK), charTime: p.charTime });
      this.svg = svgEl('svg', { width: 10, height: 10 }, this.root);
    }
    measure() {
      const r = super.measure();
      this.writer.measure(this.root);
      attr(this.svg, 'width', this.w); attr(this.svg, 'height', this.h);
      return r;
    }
    autoDur() { return this.writer.estDur() + (this.props.underline ? 0.5 : 0); }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const D = args.dur ?? this.autoDur();
      const ul = this.props.underline ? clamp(D * 0.22, 0.3, 0.5) : 0;
      this.writer.schedule(at, D - ul, this.handOn);
      if (ul) this.a_underline(at + D - ul + 0.04, ul, null, { color: this.props.underlineColor });
    }
    a_write(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_underline(at, dur, e, args) {
      const b = this.writer.box(args.word), s = this.props.size;
      const y = b.y + b.h * 0.9, x0 = b.x + 4, x1 = b.x + b.w - 2, w = x1 - x0;
      const d = `M${x0},${y + 4} C${x0 + w * 0.3},${y - 3} ${x0 + w * 0.62},${y + 6} ${x1},${y - 2}`;
      const ink = new InkPath(this, this.svg, d, { color: color(this.scene, args.color, ACCENT), width: Math.max(4, s * 0.085) });
      ink.schedule(at, dur, this.handOn);
      this.marks.push(ink);
    }
    a_circle(at, dur, e, args) {
      const b = this.writer.box(args.word);
      const d = loopD(b.x + b.w / 2, b.y + b.h * 0.54, b.w / 2 + 16, b.h / 2 + 8, this.id + at);
      const ink = new InkPath(this, this.svg, d, { color: color(this.scene, args.color, ACCENT), width: Math.max(4, this.props.size * 0.07) });
      ink.schedule(at, dur, this.handOn);
      this.marks.push(ink);
    }
    a_strike(at, dur, e, args) {
      const b = this.writer.box(args.word), y = b.y + b.h * 0.56;
      const d = `M${b.x - 6},${y + 4} L${b.x + b.w + 6},${y - 4}`;
      const ink = new InkPath(this, this.svg, d, { color: color(this.scene, args.color, 'red'), width: Math.max(4, this.props.size * 0.08) });
      ink.schedule(at, dur, this.handOn);
      this.marks.push(ink);
    }
    render(t) {
      super.render(t);
      this.writer.render(t);
      for (const m of this.marks) m.render(t);
    }
  }

  // ------------------------------------------------------------------ KineticText
  class KineticText extends WBNode {
    static defaults = { text: '', size: 92, color: '#111111', emphasis: 'accent', highlight: 'underline', width: null, align: 'center', stagger: 0.12, weight: 800, uppercase: false };
    static actions = { enter: {}, reveal: {}, emphasize: { dur: 0.6 }, exit: { dur: 0.45 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props, S = this.scene;
      this.root.classList.add('wb-kinetic');
      const maxW = p.width ? frac(p.width, S.W) : (S.portrait ? S.W - 140 : Math.min(1560, S.W - 240));
      Object.assign(this.root.style, { fontSize: p.size + 'px', fontWeight: String(p.weight), color: color(S, p.color, INK), textAlign: p.align, maxWidth: maxW + 'px' });
      this.emColor = color(S, p.emphasis, ACCENT);
      this.svg = svgEl('svg', { width: 10, height: 10 }, this.root);
      this.txt = el('div', { style: { position: 'relative' } }, this.root);
      const str = p.uppercase ? String(p.text).toUpperCase() : String(p.text);
      this.spans = [];
      for (const ln of str.split('\n')) {
        const d = el('div', { class: 'wb-line' }, this.txt);
        this.spans.push(...splitWords(d, ln, { colorFor: (w) => S.colorFor(w), emphasisColor: this.emColor }));
      }
      this.kw = new Set(this.spans.filter((s) => s.classList.contains('em')));
      this.inks = [];
      this.emph = [];
    }
    measure() {
      const r = super.measure();
      attr(this.svg, 'width', this.w); attr(this.svg, 'height', this.h);
      // keyword runs grouped per line
      const runs = [];
      for (const s of this.spans) {
        if (!this.kw.has(s)) { runs.push(null); continue; }
        const b = relBox(s.firstElementChild || s, this.root), last = runs[runs.length - 1];
        if (last && Math.abs(last.y - b.y) < 4) { const x1 = Math.max(last.x + last.w, b.x + b.w); last.w = x1 - last.x; }
        else runs.push(Object.assign({}, b));
      }
      const S = this.scene, s = this.props.size, mode = this.props.highlight;
      for (const b of runs.filter(Boolean)) {
        let ink;
        if (mode === 'marker') {
          const y = b.y + b.h * 0.6;
          ink = new InkPath(this, this.svg, `M${b.x - 2},${y + 3} L${b.x + b.w + 4},${y - 3}`, { color: tint(this.emColor, 0.74), width: s * 0.6 });
          attr(ink.el, 'stroke-linecap', 'butt');
          this.txt.style.zIndex = '1';
        } else if (mode === 'circle') {
          ink = new InkPath(this, this.svg, loopD(b.x + b.w / 2, b.y + b.h * 0.54, b.w / 2 + 30, b.h / 2 + 10, this.id), { color: this.emColor, width: s * 0.06 });
        } else if (mode === 'underline') {
          const y = b.y + b.h * 0.9, x0 = b.x + 2, x1 = b.x + b.w - 2, w = x1 - x0;
          ink = new InkPath(this, this.svg, `M${x0},${y + 3} C${x0 + w * 0.35},${y - 5} ${x0 + w * 0.7},${y + 5} ${x1},${y - 3}`, { color: this.emColor, width: Math.max(5, s * 0.085) });
        }
        if (ink) this.inks.push(ink);
      }
      if (mode !== 'marker') this.root.appendChild(this.svg);
      return r;
    }
    autoDur() { return (this.spans.length - 1) * this.props.stagger + 0.45 + (this.inks.length ? 0.5 : 0); }
    a_enter(at, dur, e, args) {
      if (this.revealAt != null) return;
      const n = this.spans.length;
      this.stag = args.dur != null ? clamp((args.dur - 0.9) / Math.max(1, n - 1), 0.04, 0.5) : this.props.stagger;
      this.revealAt = at; this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const tEnd = at + (n - 1) * this.stag + 0.38;
      for (const ink of this.inks) ink.schedule(tEnd, 0.45, false, 'out');
    }
    a_reveal(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_emphasize(at, dur) { this.emph.push({ at, dur }); }
    render(t) {
      super.render(t);
      if (this.revealAt == null) return;
      this.spans.forEach((s, i) => {
        const p = clamp((t - this.revealAt - i * this.stag) / 0.42);
        let k = 1;
        if (this.kw.has(s)) for (const m of this.emph) k += 0.12 * bump(t, m.at, m.dur);
        const sc = (p >= 1 ? 1 : 0.5 + 0.5 * ease.outBack(p)) * k;
        css(s, 'opacity', clamp(p * 3).toFixed(3));
        css(s, 'transform', p >= 1 && k === 1 ? 'none' : `translateY(${((1 - ease.out(p)) * 26).toFixed(2)}px) scale(${sc.toFixed(4)})`);
      });
      for (const ink of this.inks) ink.render(t);
    }
  }

  // ------------------------------------------------------------------ ChapterCard
  class ChapterCard extends Primitive {
    static layer = 'text';
    static focusExempt = true;
    static autoEnterAt = 0;
    static defaults = { text: '', kicker: null, duration: null, rule: true, ruleColor: 'accent', hold: null };
    static actions = { enter: { dur: 0.3 }, exit: { dur: 0.3 } };
    build() {
      const p = this.props, S = this.scene, cc = S.look.chapter_card || {};
      this.root.classList.add('wb-chapter');
      Object.assign(this.root.style, { width: S.W + 'px', height: S.H + 'px', zIndex: '60', background: cc.bg || '#000000', color: cc.fg || '#FFFFFF' });
      this.inner = el('div', { class: 'inner' }, this.root);
      if (p.kicker) el('div', { class: 'kicker', text: p.kicker }, this.inner);
      this.ttl = el('div', { class: 'ttl', text: p.text }, this.inner);
      const tr = cc.tracking ?? 0.3;
      Object.assign(this.ttl.style, { letterSpacing: tr + 'em', paddingLeft: tr + 'em', fontSize: (S.portrait ? 54 : 66) + 'px' });
      if (S.portrait) this.ttl.style.maxWidth = (S.W - 120) + 'px';
      if (p.rule) this.rule = el('div', { class: 'rule', style: { background: color(S, p.ruleColor, ACCENT) } }, this.inner);
      this.dur = p.duration ?? cc.duration ?? 2.0;
      this.scl = cc.scale || [1.0, 1.08];
    }
    measure() { this.w = this.scene.W; this.h = this.scene.H; return { w: this.w, h: this.h }; }
    afterLayout() { this.place(this.scene.W / 2, this.scene.H / 2); }
    autoDur() { return this.dur; }
    a_enter(at, dur, e) {
      this.enterAt = at;
      const whole = at <= 0.05 && at + this.dur >= (this.scene.spec.duration || 0) - 0.05;
      this.vis.to(at, 1, at <= 0.05 ? 0 : dur, 'out');
      const hold = this.props.hold ?? whole;
      if (!hold) this.vis.to(at + this.dur - 0.3, 0, 0.3, 'in');
    }
    render(t) {
      super.render(t);
      if (this.enterAt == null) return;
      const u = clamp((t - this.enterAt) / this.dur);
      const s = lerp(this.scl[0], this.scl[1], ease.inOut(u) * 0.35 + u * 0.65);
      css(this.inner, 'transform', `scale(${s.toFixed(4)})`);
      const a = prog(t, this.enterAt + 0.05, 0.5, 'out');
      css(this.inner, 'opacity', a.toFixed(3));
      if (this.rule) css(this.rule, 'width', (64 * prog(t, this.enterAt + 0.25, 0.6, 'out')).toFixed(1) + 'px');
    }
  }

  // ------------------------------------------------------------------ full-stage overlays (Arrow, Chevrons, MarchingBox)
  class Overlay extends Primitive {
    static layer = 'pills';
    build() {
      const { W, H } = this.scene;
      Object.assign(this.root.style, { width: W + 'px', height: H + 'px' });
      this.svg = svgEl('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, style: { position: 'absolute', left: '0px', top: '0px', overflow: 'visible' } }, this.root);
    }
    measure() { this.w = this.scene.W; this.h = this.scene.H; return { w: this.w, h: this.h }; }
    origin() { return [0, 0]; }
    get handOn() { return !!this.props.hand && wb(this.scene).handEnabled; }
    afterLayout() { if (this._geo) return; this._geo = true; this.place(this.scene.W / 2, this.scene.H / 2); this.geom(); }
    geom() {}
    annColor() { return color(this.scene, this.props.color, this.scene.spec.transparent ? ACCENT : ACCENT); }
  }

  class Arrow extends Overlay {
    static defaults = { from: null, to: null, bend: 0.22, dashed: false, color: null, width: 6, head: 'end', hand: false, gap: 18, label: null, labelSize: 40, labelSide: 1 };
    static actions = { enter: { dur: 0.7 }, draw: { dur: 0.7 }, exit: { dur: 0.35 }, pulse: { dur: 0.6 } };
    static deps(e) { return [refId(e.props.from), refId(e.props.to)].filter(Boolean); }
    geom() {
      const p = this.props, S = this.scene;
      if (p.from == null || p.to == null) throw new Error(`Arrow "${this.id}" needs "from" and "to"`);
      const A = refBox(S, p.from), B = refBox(S, p.to);
      const p0 = edgeToward(A, B.cx, B.cy, p.gap), p1 = edgeToward(B, A.cx, A.cy, p.gap);
      const dx = p1[0] - p0[0], dy = p1[1] - p0[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L;
      const r = rng('arrow' + this.id), bend = p.bend * L;
      const w1 = (r() - 0.5) * 0.05 * L, w2 = (r() - 0.5) * 0.05 * L;
      const c1 = [p0[0] + dx * 0.28 + nx * (bend + w1), p0[1] + dy * 0.28 + ny * (bend + w1)];
      const c2 = [p0[0] + dx * 0.72 + nx * (bend + w2), p0[1] + dy * 0.72 + ny * (bend + w2)];
      const d = `M${p0[0].toFixed(1)},${p0[1].toFixed(1)} C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p1[0].toFixed(1)},${p1[1].toFixed(1)}`;
      this.col = color(S, p.color, S.spec.transparent ? ACCENT : INK);
      this.shaft = new InkPath(this, this.svg, d, { color: this.col, width: p.width, dashed: p.dashed });
      const hs = 14 + p.width * 2.2;
      this.heads = [];
      const L2 = this.shaft.len;
      if (p.head === 'end' || p.head === 'both') {
        const a = this.shaft.lut.at(L2 - 1), b = this.shaft.lut.at(L2);
        this.heads.push(new InkPath(this, this.svg, arrowHeadD(p1, Math.atan2(b.y - a.y, b.x - a.x), hs), { color: this.col, width: p.width }));
      }
      if (p.head === 'start' || p.head === 'both') {
        const a = this.shaft.lut.at(1), b = this.shaft.lut.at(0);
        this.heads.push(new InkPath(this, this.svg, arrowHeadD(p0, Math.atan2(b.y - a.y, b.x - a.x), hs), { color: this.col, width: p.width }));
      }
      if (p.label) {
        const m = this.shaft.lut.at(L2 / 2), side = p.labelSide >= 0 ? 1 : -1;
        this.lab = el('div', { class: 'wb-hand', style: { position: 'absolute', fontSize: p.labelSize + 'px', color: this.col } }, this.root);
        this.writer = new Writer(this, this.lab, p.label, { emphasisColor: ACCENT });
        const lw = this.lab.offsetWidth, lh = this.lab.offsetHeight;
        const off = Math.abs(bend) * 0.75 + lh * 0.7 + 10;
        const sgn = Math.sign(bend || 1) * side;
        const cx = m.x + nx * off * sgn, cy = m.y + ny * off * sgn;
        Object.assign(this.lab.style, { left: (cx - lw / 2).toFixed(1) + 'px', top: (cy - lh / 2).toFixed(1) + 'px' });
        this.writer.measure(this.root);
      }
    }
    autoDur() { return 0.7 + (this.writer ? this.writer.estDur() : 0); }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const D = args.dur ?? 0.7, hd = this.heads.length ? Math.min(0.2, D * 0.25) : 0;
      this.shaft.schedule(at, D - hd, this.handOn);
      this.heads.forEach((h, i) => h.schedule(at + D - hd + (i * hd) / this.heads.length, hd / this.heads.length, this.handOn, 'out'));
      if (this.writer) this.writer.schedule(at + D + 0.05, this.writer.estDur(), this.handOn);
    }
    a_draw(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    render(t) {
      super.render(t);
      const f = this.flashAt(t).amt;
      this.shaft.render(t);
      for (const h of this.heads) h.render(t);
      if (this.writer) this.writer.render(t);
      css(this.svg, 'filter', f > 0.01 ? `drop-shadow(0 0 ${(10 * f).toFixed(1)}px ${CA.rgba(this.col, 0.6)})` : 'none');
    }
  }

  class Chevrons extends Overlay {
    static defaults = { x: null, y: null, target: null, side: 'left', dir: null, count: 3, size: 46, gap: 26, color: null, speed: 1.6 };
    static actions = { enter: { dur: 0.35 }, exit: { dur: 0.3 } };
    static deps(e) { return [refId(e.props.target)].filter(Boolean); }
    geom() {
      const p = this.props, S = this.scene, n = p.count, s = p.size, sp = s * 0.62;
      const DIRS = { right: 0, down: 90, left: 180, up: 270 };
      let ax, ay, ang;
      if (p.target != null) {
        const b = refBox(S, p.target);
        const side = p.side;
        const span = (n - 1) * sp + s * 0.5;
        if (side === 'left') { ax = b.x - p.gap; ay = b.cy; ang = 0; }
        else if (side === 'right') { ax = b.r + p.gap; ay = b.cy; ang = 180; }
        else if (side === 'top') { ax = b.cx; ay = b.y - p.gap; ang = 90; }
        else { ax = b.cx; ay = b.b + p.gap; ang = 270; }
        void span;
      } else {
        ax = frac(p.x ?? 0.5, S.W); ay = frac(p.y ?? 0.5, S.H); ang = 0;
      }
      if (p.dir != null) ang = typeof p.dir === 'number' ? p.dir : (DIRS[p.dir] ?? 0);
      this.ang = ang;
      this.g = svgEl('g', { transform: `translate(${ax.toFixed(1)},${ay.toFixed(1)}) rotate(${ang})` }, this.svg);
      this.inner = svgEl('g', {}, this.g);
      this.col = this.annColor();
      this.chev = [];
      for (let i = 0; i < n; i++) {
        const x = -i * sp - s * 0.15; // i = 0 is nearest the target (the tip sits at the anchor)
        this.chev.push(svgEl('path', { d: `M${x - s * 0.3},${-s * 0.5} L${x + s * 0.15},0 L${x - s * 0.3},${s * 0.5}`, fill: 'none', stroke: this.col, 'stroke-width': s * 0.2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.inner));
      }
    }
    autoDur() { return 0.35; }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      const sp = this.props.speed;
      this.chev.forEach((c, i) => {
        const ph = t * sp - (this.chev.length - 1 - i) * 0.2;
        const a = 0.28 + 0.72 * (0.5 + 0.5 * Math.cos(2 * Math.PI * ph));
        attr(c, 'opacity', a.toFixed(3));
      });
      const nud = Math.sin(2 * Math.PI * t * sp) * 5;
      const sc = 0.6 + 0.4 * ease.outBack(clamp(v));
      attr(this.inner, 'transform', `translate(${nud.toFixed(2)},0) scale(${sc.toFixed(4)})`);
    }
  }

  class MarchingBox extends Overlay {
    static defaults = { target: null, region: null, pad: 14, radius: 16, color: null, width: 4.5, dash: '16 11', speed: 38, label: null, labelSide: 'top', hand: false };
    static actions = { enter: { dur: 0.6 }, draw: { dur: 0.6 }, exit: { dur: 0.35 }, pulse: { dur: 0.6 } };
    static deps(e) { return [refId(e.props.target)].filter(Boolean); }
    geom() {
      const p = this.props, S = this.scene;
      const b = p.target != null ? refBox(S, p.target) : refBox(S, p.region || { x: 0.25, y: 0.25, w: 0.5, h: 0.5 });
      const pd = p.target != null ? p.pad : 0;
      this.b = { x: b.x - pd, y: b.y - pd, w: b.w + pd * 2, h: b.h + pd * 2 };
      this.col = this.annColor();
      this.ink = new InkPath(this, this.svg, roundRectD(this.b.x, this.b.y, this.b.w, this.b.h, p.radius), { color: this.col, width: p.width, dashed: p.dash });
      if (p.label) {
        this.pill = el('div', { class: 'wb-pill', style: { position: 'absolute', fontSize: '22px', padding: '11px 20px 10px', background: this.col } }, this.root);
        this.pill.textContent = p.label;
        const pw = this.pill.offsetWidth, ph = this.pill.offsetHeight;
        const ls = String(p.labelSide), below = ls.startsWith('bottom'), right = ls.endsWith('right');
        const y = below ? this.b.y + this.b.h + 12 : this.b.y - ph - 12;
        const x = right ? this.b.x + this.b.w - pw : this.b.x;
        Object.assign(this.pill.style, { left: x + 'px', top: y + 'px', transformOrigin: `${right ? pw : 0}px ${below ? 0 : ph}px` });
      }
    }
    visualBox() { return box(this.b.x + this.b.w / 2, this.b.y + this.b.h / 2, this.b.w, this.b.h); }
    autoDur() { return 0.6; }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      this.ink.schedule(at, args.dur ?? 0.6, this.handOn, 'inOut');
      this.drawEnd = at + (args.dur ?? 0.6);
    }
    a_draw(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    render(t) {
      super.render(t);
      this.ink.render(t);
      if (this.drawEnd != null && t >= this.drawEnd) attr(this.ink.el, 'stroke-dashoffset', (-(t - this.drawEnd) * this.props.speed).toFixed(2));
      else attr(this.ink.el, 'stroke-dashoffset', '0');
      const f = this.flashAt(t).amt;
      attr(this.ink.el, 'stroke-width', (this.props.width * (1 + 0.5 * f)).toFixed(2));
      if (this.pill) {
        const q = this.drawEnd == null ? 0 : prog(t, this.drawEnd - 0.15, 0.4, 'outBack');
        css(this.pill, 'opacity', clamp(q * 2).toFixed(3));
        css(this.pill, 'transform', q >= 1 ? 'none' : `scale(${(0.5 + 0.5 * q).toFixed(4)})`);
      }
    }
  }

  // ------------------------------------------------------------------ PillLabel
  class PillLabel extends Primitive {
    static layer = 'pills';
    static defaults = { text: '', x: null, y: null, target: null, side: 'top', gap: 22, arrows: 'none', span: null, color: '#1E1E1E', textColor: '#FFFFFF', size: 26, dot: null, ticks: true, dx: 0, dy: 0 };
    static actions = { enter: { dur: 0.6 }, exit: { dur: 0.3 }, pulse: { dur: 0.6 }, set: { dur: 0.4 } };
    static deps(e) { return [refId(e.props.target)].filter(Boolean); }
    build() {
      const p = this.props, S = this.scene;
      this.root.classList.add('wb-pill-wrap');
      this.svg = svgEl('svg', { width: 10, height: 10, style: { position: 'absolute', left: '0px', top: '0px', overflow: 'visible' } }, this.root);
      this.pill = el('div', { class: 'wb-pill' }, this.root);
      Object.assign(this.pill.style, { background: color(S, p.color, PILL), color: color(S, p.textColor, '#FFFFFF'), fontSize: p.size + 'px' });
      if (p.dot) el('span', { class: 'dot', style: { background: color(S, p.dot, ACCENT) } }, this.pill);
      this.label = el('span', {}, this.pill);
      this.label.textContent = p.text;
      this.sets = new Events();
    }
    get vertical() { return this.props.arrows === 'vertical' || this.props.arrows === 'up-down'; }
    measure() {
      const p = this.props, S = this.scene;
      this.pw = this.pill.offsetWidth; this.ph = this.pill.offsetHeight;
      let span = p.span != null ? frac(p.span, this.vertical ? S.H : S.W) : null;
      if (span == null && p.arrows !== 'none' && p.target != null) {
        try { const b = refBox(S, p.target); span = this.vertical ? b.h : b.w; } catch (e) { span = null; }
      }
      if (span == null) span = p.arrows === 'none' ? 0 : (this.vertical ? 260 : 420);
      this.span = span;
      this.w = this.vertical ? this.pw : Math.max(span, this.pw);
      this.h = this.vertical ? Math.max(span, this.ph) : this.ph;
      Object.assign(this.root.style, { width: this.w + 'px', height: this.h + 'px' });
      return { w: this.w, h: this.h };
    }
    afterLayout() {
      if (this._geo) return; this._geo = true;
      const p = this.props, S = this.scene;
      let cx, cy;
      if (p.target != null) {
        const b = refBox(S, p.target), g = p.gap;
        const centered = p.arrows !== 'none' && p.side === 'top' && false;
        void centered;
        if (p.side === 'top') { cx = b.cx; cy = b.y - g - this.h / 2; }
        else if (p.side === 'bottom') { cx = b.cx; cy = b.b + g + this.h / 2; }
        else if (p.side === 'left') { cx = b.x - g - this.w / 2; cy = b.cy; }
        else if (p.side === 'right') { cx = b.r + g + this.w / 2; cy = b.cy; }
        else { cx = b.cx; cy = b.cy; }
      } else { cx = frac(p.x ?? 0.5, S.W); cy = frac(p.y ?? 0.5, S.H); }
      this.place(cx + (p.dx || 0), cy + (p.dy || 0));
      // arrows (dimension-line style) from the pill edges outward
      const col = color(S, p.color, PILL), sw = 3.5, hs = 13;
      const mk = (d) => new InkPath(this, this.svg, d, { color: col, width: sw });
      this.arrows = [];
      const a = p.arrows;
      if (this.vertical) {
        const x = this.w / 2, y0 = this.h / 2 - this.ph / 2 - 10, y1 = this.h / 2 + this.ph / 2 + 10;
        this.arrows.push(mk(`M${x},${y0} L${x},3`), mk(`M${x},${y1} L${x},${this.h - 3}`));
        this.heads = [mk(arrowHeadD([x, 3], -Math.PI / 2, hs)), mk(arrowHeadD([x, this.h - 3], Math.PI / 2, hs))];
        if (p.ticks) this.heads.push(mk(`M${x - 14},1.5 L${x + 14},1.5`), mk(`M${x - 14},${this.h - 1.5} L${x + 14},${this.h - 1.5}`));
      } else if (a !== 'none') {
        const y = this.h / 2, x0 = this.w / 2 - this.pw / 2 - 10, x1 = this.w / 2 + this.pw / 2 + 10;
        this.heads = [];
        if (a === 'both' || a === 'left') { this.arrows.push(mk(`M${x0},${y} L3,${y}`)); this.heads.push(mk(arrowHeadD([3, y], Math.PI, hs))); if (p.ticks) this.heads.push(mk(`M1.5,${y - 14} L1.5,${y + 14}`)); }
        if (a === 'both' || a === 'right') { this.arrows.push(mk(`M${x1},${y} L${this.w - 3},${y}`)); this.heads.push(mk(arrowHeadD([this.w - 3, y], 0, hs))); if (p.ticks) this.heads.push(mk(`M${this.w - 1.5},${y - 14} L${this.w - 1.5},${y + 14}`)); }
      } else this.heads = [];
      attr(this.svg, 'width', this.w); attr(this.svg, 'height', this.h);
    }
    autoDur() { return 0.6; }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const D = args.dur ?? 0.6;
      for (const a of this.arrows) a.schedule(at + 0.15, D - 0.15, false, 'out');
      for (const h of this.heads) h.schedule(at + D - 0.05, 0.2, false, 'out');
    }
    a_set(at, dur, e, args) { this.sets.add(at, { text: args.text, dur }); }
    render(t) {
      super.render(t);
      if (this.enterAt == null) return;
      const q = prog(t, this.enterAt, 0.4, 'outBack');
      const f = this.flashAt(t).amt;
      css(this.pill, 'opacity', clamp(q * 2.5).toFixed(3));
      css(this.pill, 'transform', q >= 1 && f < 0.001 ? 'none' : `scale(${((0.55 + 0.45 * q) * (1 + 0.08 * f)).toFixed(4)})`);
      for (const a of this.arrows) a.render(t);
      for (const h of this.heads) h.render(t);
      const s = this.sets.last(t);
      if (s) {
        CA.text(this.label, s.text);
        const u = clamp((t - s.at) / s.dur);
        css(this.label, 'filter', u >= 1 ? 'none' : `blur(${((1 - u) * 6).toFixed(1)}px)`);
      }
    }
  }

  // ------------------------------------------------------------------ PointerHand
  class PointerHand extends Primitive {
    static layer = 'text';
    static focusExempt = true;
    static defaults = { x: null, y: null, target: null, angle: -24, size: 1.25, skin: null, sleeve: null, ripple: true, color: null };
    static actions = { enter: { dur: 0.6 }, move: { dur: 0.6 }, click: { dur: 0.36 }, tap: { dur: 0.36 }, exit: { dur: 0.5 } };
    static deps(e) { return [refId(e.props.target)].filter(Boolean); }
    build() {
      const p = this.props, S = this.scene, ho = wb(S).hand;
      const sk = SKINS[p.skin || ho.skin] || SKINS.light;
      const sleeve = color(S, p.sleeve || ho.sleeve, '#2A2A31');
      css(this.root, 'zIndex', '35');
      this.rip = svgEl('svg', { width: 10, height: 10, style: { overflow: 'visible', position: 'absolute', left: '0px', top: '0px' } }, this.root);
      this.ring = svgEl('circle', { cx: 0, cy: 0, r: 10, fill: 'none', stroke: color(S, p.color, ACCENT), 'stroke-width': 5, opacity: 0 }, this.rip);
      this.ring2 = svgEl('circle', { cx: 0, cy: 0, r: 10, fill: color(S, p.color, ACCENT), opacity: 0 }, this.rip);
      this.svg = svgEl('svg', { width: 10, height: 10, style: { overflow: 'visible', position: 'absolute', left: '0px', top: '0px' } }, this.root);
      this.g = svgEl('g', {}, this.svg);
      this.g.innerHTML = withShadow(window.WB_HANDS.paint('point', Object.assign({}, sk, { SLEEVE: sleeve, CUFF: color(this.scene, wb(this.scene).hand.cuff, ACCENT) })));
      this.clicks = [];
    }
    measure() { this.w = 0; this.h = 0; return { w: 0, h: 0 }; }
    tipFor(ref) {
      const b = refBox(this.scene, ref);
      return [b.cx, b.cy];
    }
    armDir() { const a = (this.props.angle * Math.PI) / 180; return [-Math.sin(a), Math.cos(a)]; }
    offFor(pt) { const [dx, dy] = this.armDir(), D = Math.max(this.scene.W, this.scene.H) * 0.85 + 400; return [pt[0] + dx * D, pt[1] + dy * D]; }
    afterLayout() {
      if (this.pos) return;
      const p = this.props, S = this.scene;
      this.home = p.target != null ? this.tipFor(p.target) : [frac(p.x ?? 0.5, S.W), frac(p.y ?? 0.5, S.H)];
      this.pos = new Track(this.offFor(this.home));
      this.cur = this.home;
      this.place(0, 0);
    }
    autoDur() { return 0.6; }
    a_enter(at, dur, e, args) { this.enterAt = at; this.vis.to(at, 1, 0.01, 'linear'); this.pos.to(at, this.home, dur, 'out'); this.cur = this.home; }
    a_move(at, dur, e, args) {
      const S = this.scene;
      const to = args.target != null ? this.tipFor(args.target) : [frac(args.x ?? 0.5, S.W), frac(args.y ?? 0.5, S.H)];
      this.pos.to(at, to, dur, 'smooth'); this.cur = to;
    }
    a_click(at, dur) { this.clicks.push({ at, dur }); }
    a_tap(at, dur) { this.a_click(at, dur); }
    a_exit(at, dur) { this.pos.to(at, this.offFor(this.cur), dur, 'in'); }
    render(t) {
      super.render(t);
      const [x, y] = this.pos.value(t);
      let k = 1, rp = -1;
      for (const c of this.clicks) {
        if (t >= c.at && t <= c.at + c.dur) { const u = (t - c.at) / c.dur; k = u < 0.4 ? 1 - 0.15 * ease.out(u / 0.4) : 0.85 + 0.15 * ease.outBack((u - 0.4) / 0.6); }
        if (t >= c.at + c.dur * 0.3 && t <= c.at + c.dur * 0.3 + 0.6) rp = (t - c.at - c.dur * 0.3) / 0.6;
      }
      const s = this.props.size * k;
      css(this.root, 'transform', `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px)`);
      attr(this.g, 'transform', `rotate(${this.props.angle}) scale(${s.toFixed(4)})`);
      if (this.props.ripple && rp >= 0) {
        attr(this.ring, 'r', (14 + 62 * ease.out(rp)).toFixed(1)); attr(this.ring, 'opacity', (0.85 * (1 - rp)).toFixed(3));
        attr(this.ring2, 'r', (10 + 30 * ease.out(rp)).toFixed(1)); attr(this.ring2, 'opacity', (0.25 * (1 - rp)).toFixed(3));
      } else { attr(this.ring, 'opacity', 0); attr(this.ring2, 'opacity', 0); }
    }
  }

  // ------------------------------------------------------------------ UIMock (shared builder; also used by HandPlace)
  function mockHTML(p, S) {
    const v = p.variant || 'card';
    const accent = color(S, p.accent, ACCENT);
    const tick = `<span class="tick"><svg width="15" height="15" viewBox="0 0 14 14"><path d="M2.5,7.5 L5.8,10.5 L11.5,3.8" fill="none" stroke="${accent}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span>`;
    const btn = (txt, ghost) => `<div class="spacer" style="flex:1 1 auto;min-height:22px"></div><div class="btn${ghost ? ' ghost' : ''}" data-part="button" style="${ghost ? '' : `background:${accent}`}">${esc(txt)}</div>`;
    const lines = (n) => (Array.isArray(n) ? n.map((s, i) => `<div class="subtitle" data-part="line${i}" style="margin-top:12px;color:#3F3F46">${esc(s)}</div>`).join('')
      : Array.from({ length: n ?? 3 }, (_, i) => `<div class="skel${i === 0 ? ' a' : ''}" data-part="line${i}" style="width:${[92, 76, 84, 60, 70][i % 5]}%"></div>`).join(''));
    if (v === 'pricing') {
      const feats = p.features || ['Unlimited projects', 'Priority support', 'Advanced analytics'];
      return `${p.badge ? `<span class="badge" data-part="badge" style="background:${accent}">${esc(p.badge)}</span>` : ''}
        <div class="plan" data-part="plan">${esc(p.plan ?? 'Pro')}</div>
        <div data-part="price"><span class="price">${esc(p.price ?? '$29')}</span><span class="period">${esc(p.period ?? '/month')}</span></div>
        <ul class="features" data-part="features">${feats.map((f, i) => `<li data-part="feature${i}">${tick}${esc(f)}</li>`).join('')}</ul>
        ${btn(p.button ?? 'Start free trial', p.ghost)}`;
    }
    if (v === 'slider') {
      return `<div class="row"><span class="slabel" data-part="label">${esc(p.label ?? 'Team seats')}</span><span class="svalue" data-part="value" style="color:${accent}"></span></div>
        <div class="track" data-part="slider"><div class="fillbar" style="background:${accent}"></div><div class="knob" data-part="knob"></div></div>
        <div class="minmax"><span>${esc(p.min ?? 1)}</span><span>${esc(p.max ?? 100)}</span></div>`;
    }
    if (v === 'button') return btn(p.button ?? p.title ?? 'Get started', p.ghost).replace(/<div class="spacer"[^>]*><\/div>/, '');
    if (v === 'browser') {
      const items = p.items || ['Dashboard', 'Projects', 'Billing', 'Settings'];
      const bars = p.bars || [0.35, 0.5, 0.42, 0.68, 0.6, 0.85];
      return `<div class="browserbar"><i style="background:#FF5F57"></i><i style="background:#FEBC2E"></i><i style="background:#28C840"></i><div class="url" data-part="url">${esc(p.url ?? 'app.acme.com')}</div></div>
        <div class="appbody"><div class="side" data-part="sidebar">${items.map((it, i) => `<div class="it${i === (p.active ?? 0) ? ' on' : ''}" data-part="item${i}">${esc(it)}</div>`).join('')}</div>
        <div class="main" data-part="main"><div class="subtitle" style="margin-top:0">${esc(p.title ?? 'Revenue')}</div><div class="stat" data-part="stat">${esc(p.stat ?? '$12,480')}</div>
        <div class="bars" data-part="chart">${bars.map((b, i) => `<b class="${i === bars.length - 1 ? 'hi' : ''}" style="height:${Math.round(b * 100)}%;${i === bars.length - 1 ? `background:${accent}` : ''}"></b>`).join('')}</div></div></div>`;
    }
    if (v === 'form') {
      const fields = p.fields || [{ label: 'Email', value: '' }, { label: 'Password', value: '' }];
      return `<div class="title" data-part="title">${esc(p.title ?? 'Create your account')}</div>
        ${fields.map((f, i) => `<div class="flabel">${esc(f.label ?? f)}</div><div class="field" data-part="field${i}">${esc(f.value ?? '')}</div>`).join('')}
        ${btn(p.button ?? 'Sign up')}`;
    }
    // card
    return `${p.badge ? `<span class="badge" data-part="badge" style="background:${accent};margin-bottom:14px">${esc(p.badge)}</span>` : ''}
      <div class="title" data-part="title">${esc(p.title ?? 'New project')}</div>
      ${p.subtitle ? `<div class="subtitle" data-part="subtitle">${esc(p.subtitle)}</div>` : ''}
      ${lines(p.lines)}${p.button ? btn(p.button, p.ghost) : ''}`;
  }
  /** Mount a UI mock: .body (shadow + face, revealed by the wipe) and an SVG frame drawn on top. */
  function mountMock(host, parent, p, width) {
    const S = host.scene;
    const wrap = el('div', { class: 'wb-ui', style: { width: width + 'px' } }, parent);
    const body = el('div', { style: { position: 'relative' } }, wrap);
    const shadow = el('div', { class: 'shadow' }, body);
    if (p.shadow === false) shadow.style.display = 'none';
    else if (p.shadowColor) shadow.style.background = color(S, p.shadowColor, INK);
    const face = el('div', { class: 'face' }, body);
    if ((p.variant || 'card') === 'button') face.style.padding = '22px';
    if (p.height) face.style.minHeight = frac(p.height, S.H) + 'px';
    face.innerHTML = mockHTML(p, S);
    const frame = svgEl('svg', { class: 'frame', width: 10, height: 10 }, wrap);
    return { wrap, body, face, shadow, frame };
  }

  class UIMock extends WBNode {
    static defaults = { variant: 'card', width: 440, entrance: 'draw', hand: true, accent: null, value: 0.4, min: 1, max: 100, format: '{v}', shadow: true };
    static actions = { enter: {}, draw: {}, click: { dur: 0.4 }, set: { dur: 0.8 }, type: {}, select: { dur: 0.45 }, deselect: { dur: 0.35 }, exit: { dur: 0.4 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props, S = this.scene;
      if (p.variant === 'slider' && this.def.props && this.def.props.width == null) p.width = 520;
      this.m = mountMock(this, this.root, p, frac(p.width, S.W));
      this.valueT = new Track(clamp(+p.value || 0));
      this.presses = [];
      this.selT = new Track(0);
      this.types = [];
      this.accent = color(S, p.accent, ACCENT);
      this.knob = this.m.face.querySelector('.knob');
      this.fillbar = this.m.face.querySelector('.fillbar');
      this.valEl = this.m.face.querySelector('.svalue');
      this.fields = [...this.m.face.querySelectorAll('.field')].map((f) => ({ el: f, base: f.textContent }));
    }
    measure() {
      const r = super.measure();
      const fw = this.m.body.offsetWidth, fh = this.m.body.offsetHeight;
      this.fw = fw; this.fh = fh;
      attr(this.m.frame, 'width', fw); attr(this.m.frame, 'height', fh);
      this.frame = new InkPath(this, this.m.frame, roundRectD(1.75, 1.75, fw - 3.5, fh - 3.5, 22), { color: INK, width: 3.5 });
      this.wipe = new Wipe({ x: 0, y: 0, w: fw + 12, h: fh + 12 }, { angle: 24, zig: 6, toStage: (x, y) => { const [ox, oy] = this.origin(); return { x: ox + x, y: oy + y }; } });
      return r;
    }
    visualBox() { const [ox, oy] = this.origin(); return box(ox + this.fw / 2, oy + this.fh / 2, this.fw, this.fh); }
    partBox(name) {
      const q = this.m.face.querySelector(`[data-part="${name}"]`);
      if (!q) throw new Error(`UIMock "${this.id}" (${this.props.variant}) has no part "${name}". Parts: ${[...this.m.face.querySelectorAll('[data-part]')].map((e) => e.dataset.part).join(', ')}`);
      const b = relBox(q, this.root), [ox, oy] = this.origin();
      return box(ox + b.x + b.w / 2, oy + b.y + b.h / 2, b.w, b.h);
    }
    autoDur() { return this.props.entrance === 'draw' ? 1.4 : 0.5; }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      const p = this.props;
      if (p.entrance === 'draw') {
        this.vis.to(at, 1, 0.01, 'linear');
        const D = args.dur ?? 1.4;
        this.frame.schedule(at, D * 0.55, this.handOn);
        this.wipe.schedule(at + D * 0.55 + 0.03, D * 0.45, this, this.handOn, this.accent);
      } else {
        this.vis.to(at, 1, args.dur ?? 0.5, 'out');
        this.popIn = { at, dur: args.dur ?? 0.5 };
        this.frame.schedule(at - 1, 0.01, false);
        this.wipe.schedule(at - 1, 0.01, this, false);
      }
    }
    a_draw(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_click(at, dur, e, args) {
      const part = args.part || 'button';
      const q = this.m.face.querySelector(`[data-part="${part}"]`);
      if (!q) throw new Error(`UIMock "${this.id}" has no part "${part}"`);
      this.presses.push({ at, dur, el: q });
    }
    a_set(at, dur, e, args) { this.valueT.to(at, clamp(+args.value), dur, 'smooth'); }
    a_select(at, dur) { this.selT.to(at, 1, dur, 'outBack'); }
    a_deselect(at, dur) { this.selT.to(at, 0, dur, 'smooth'); }
    a_type(at, dur, e, args) {
      const i = args.field ?? 0;
      const f = this.fields[typeof i === 'number' ? i : +String(i).replace(/\D/g, '')];
      if (!f) throw new Error(`UIMock "${this.id}" has no field ${i}`);
      const txt = String(args.text ?? '');
      this.types.push({ at, dur: args.dur ?? clamp(txt.length * 0.06, 0.3, 3), f, text: txt });
    }
    render(t) {
      super.render(t);
      const p = this.props;
      this.frame.render(t);
      css(this.m.body, 'clipPath', this.wipe.cssClip(t));
      css(this.m.body, 'visibility', this.wipe.p(t) <= 0 ? 'hidden' : 'visible');
      let tr = '';
      if (this.popIn) { const q = prog(t, this.popIn.at, this.popIn.dur, 'outBack'); if (q < 1) tr += ` scale(${(0.85 + 0.15 * q).toFixed(4)})`; }
      const sel = this.selT.value(t);
      if (sel > 0.001) tr += ` translateY(${(-16 * sel).toFixed(2)}px)`;
      const k = this.popScale(t);
      if (k !== 1) tr += ` scale(${k.toFixed(4)})`;
      css(this.root, 'transform', tr || 'none');
      attr(this.frame.el, 'stroke', sel > 0.001 ? mixColor(INK, this.accent, clamp(sel)) : INK);
      attr(this.frame.el, 'stroke-width', (3.5 + 1.5 * clamp(sel)).toFixed(2));
      for (const pr of this.presses) {
        const b = bump(t, pr.at, pr.dur);
        css(pr.el, 'transform', b > 0.001 ? `scale(${(1 - 0.07 * b).toFixed(4)})` : 'none');
        css(pr.el, 'filter', b > 0.001 ? `brightness(${(1 - 0.18 * b).toFixed(3)})` : 'none');
      }
      if (this.knob) {
        const v = this.valueT.value(t);
        css(this.knob, 'left', (v * 100).toFixed(2) + '%');
        css(this.fillbar, 'width', (v * 100).toFixed(2) + '%');
        const mn = parseNumber(p.min) || { num: 0 }, mx = parseNumber(p.max) || { num: 100 };
        const n = Math.round(lerp(mn.num, mx.num, v));
        CA.text(this.valEl, String(p.format).replace('{v}', formatNumber(n)));
      }
      for (const f of this.fields) {
        let s = f.base;
        for (const ty of this.types) if (ty.f === f && t >= ty.at) s = ty.text.slice(0, Math.round(ty.text.length * clamp((t - ty.at) / ty.dur)));
        CA.text(f.el, s);
      }
    }
  }

  // ------------------------------------------------------------------ HandPlace
  class HandPlace extends WBNode {
    static defaults = { art: null, svg: null, paths: null, viewBox: null, mock: null, note: null, size: 320, from: 'bottom', rotate: 0, colors: null, accent: null, noteColor: '#FDE68A', noteSize: 52, hand: true };
    static actions = { enter: {}, place: {}, take: { dur: 1.1 }, exit: { dur: 0.45 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props, S = this.scene, ho = wb(S).hand;
      const sk = SKINS[ho.skin] || SKINS.light, sleeve = color(S, ho.sleeve, '#2A2A31');
      const hp = Object.assign({}, sk, { SLEEVE: sleeve, CUFF: color(this.scene, wb(this.scene).hand.cuff, ACCENT) });
      const size = frac(p.size, S.unit);
      this.root.classList.add('wb-place');
      this.back = el('div', { class: 'ca-abs', style: { zIndex: '1' } }, this.root);
      this.asset = el('div', { style: { position: 'relative', zIndex: '2', transformOrigin: '50% 100%' } }, this.root);
      this.front = el('div', { class: 'ca-abs', style: { zIndex: '3' } }, this.root);
      if (p.mock) {
        const mp = Object.assign({ width: size }, p.mock);
        this.m = mountMock(this, this.asset, mp, frac(mp.width, S.W));
      } else if (p.note != null) {
        const n = el('div', { class: 'wb-note', style: { width: size + 'px', height: size + 'px', background: color(S, p.noteColor, '#FDE68A'), fontSize: p.noteSize + 'px' } }, this.asset);
        n.innerHTML = esc(p.note).replace(/\n/g, '<br>');
      } else {
        const a = mountArt(S, this.asset, Object.assign({}, p, { art: p.art || 'rocket' }), size);
        a.svg.style.display = 'block';
      }
      const mk = (parent, name) => { const s = svgEl('svg', { width: 10, height: 10, style: { overflow: 'visible', position: 'absolute', left: '0px', top: '0px' } }, parent); s.innerHTML = name === 'placeBack' ? withShadow(window.WB_HANDS.paint(name, hp)) : window.WB_HANDS.paint(name, hp); return s; };
      this.hb = mk(this.back, 'placeBack');
      this.hf = mk(this.front, 'placeFront');
      this.assetT = new Track(1);   // 1 = off-screen, 0 = placed
      this.handT = new Track(1);
      this.liftT = new Track(0);    // asset "held" scale/tilt
    }
    measure() {
      const r = super.measure();
      if (this.m && !this.m.framed) {
        this.m.framed = true;
        const fw = this.m.body.offsetWidth, fh = this.m.body.offsetHeight;
        attr(this.m.frame, 'width', fw); attr(this.m.frame, 'height', fh);
        svgEl('path', { d: roundRectD(1.75, 1.75, fw - 3.5, fh - 3.5, 22), fill: 'none', stroke: INK, 'stroke-width': 3.5 }, this.m.frame);
      }
      const { w, h } = this;
      const f = this.props.from;
      const G = { bottom: [w * 0.56, h, 0], top: [w * 0.5, 0, 180], left: [0, h * 0.58, 90], right: [w, h * 0.58, -90] };
      this.grip = G[f] || G.bottom;
      for (const d of [this.back, this.front]) css(d, 'transform', `translate(${this.grip[0]}px, ${this.grip[1]}px) rotate(${this.grip[2]}deg)`);
      return r;
    }
    offVec() {
      const f = this.props.from, S = this.scene, [ox, oy] = this.origin();
      if (f === 'top') return [0, -(oy + this.h + 80)];
      if (f === 'left') return [-(ox + this.w + 80), 0];
      if (f === 'right') return [S.W - ox + 80, 0];
      return [0, S.H - oy + 80];
    }
    autoDur() { return 1.4; }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      const D = args.dur ?? 1.4;
      this.vis.to(at, 1, 0.01, 'linear');
      const tIn = D * 0.5, tDrop = D * 0.14;
      this.assetT.to(at, 0, tIn, CA.cubicBezier(0.22, 0.9, 0.3, 1));
      this.handT.to(at, 0, tIn, CA.cubicBezier(0.22, 0.9, 0.3, 1));
      this.liftT.set(at, 1).to(at + tIn, 0, tDrop, 'smooth');
      this.handT.to(at + tIn + tDrop, 1, D - tIn - tDrop, 'in');
    }
    a_place(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_take(at, dur) {
      const tIn = dur * 0.45;
      this.handT.to(at, 0, tIn, 'out');
      this.liftT.to(at + tIn, 1, 0.12, 'smooth');
      this.assetT.to(at + tIn + 0.1, 1, dur - tIn - 0.1, 'in');
      this.handT.to(at + tIn + 0.1, 1, dur - tIn - 0.1, 'in');
    }
    render(t) {
      super.render(t);
      const [vx, vy] = this.offVec();
      const a = this.assetT.value(t), h = this.handT.value(t), l = this.liftT.value(t);
      const rot = (this.props.rotate || 0) + l * -3;
      css(this.asset, 'transform', `translate(${(vx * a).toFixed(2)}px, ${(vy * a).toFixed(2)}px) rotate(${rot.toFixed(2)}deg) scale(${(1 + 0.04 * l).toFixed(4)})`);
      const gt = `translate(${(this.grip[0] + vx * h).toFixed(2)}px, ${(this.grip[1] + vy * h).toFixed(2)}px) rotate(${this.grip[2]}deg)`;
      css(this.back, 'transform', gt);
      css(this.front, 'transform', gt);
      css(this.back, 'visibility', h >= 0.999 ? 'hidden' : 'visible');
      css(this.front, 'visibility', h >= 0.999 ? 'hidden' : 'visible');
    }
  }

  // ------------------------------------------------------------------ Checklist
  class Checklist extends WBNode {
    static defaults = { items: [], title: null, size: 50, gap: 24, checkColor: 'green', checked: [], hand: true, strike: false, dimDone: false, titleSize: null };
    static actions = { enter: {}, write: {}, check: { dur: 0.45 }, checkAll: { dur: 0.45 }, strike: { dur: 0.4 }, exit: { dur: 0.4 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props;
      this.root.classList.add('wb-hand');
      Object.assign(this.root.style, { fontSize: p.size + 'px' });
      const bs = Math.round(p.size * 0.74);
      if (p.title) {
        this.titleEl = el('div', { class: 'wb-check-title', style: { fontSize: (p.titleSize || p.size * 1.18) + 'px', marginBottom: p.gap + 6 + 'px' } }, this.root);
        this.titleW = new Writer(this, this.titleEl, p.title, { emphasisColor: ACCENT });
      }
      this.rows = p.items.map((it, i) => {
        const row = el('div', { class: 'wb-check-item', style: { display: 'flex', alignItems: 'center', marginTop: i ? p.gap + 'px' : '0px' } }, this.root);
        const bx = el('div', { style: { width: bs + 'px', height: bs + 'px', flex: 'none', marginRight: Math.round(p.size * 0.42) + 'px' } }, row);
        const tx = el('div', {}, row);
        return { row, bx, tx, text: String(it), w: new Writer(this, tx, String(it), { emphasisColor: ACCENT }), doneT: new Track(0) };
      });
      this.svg = svgEl('svg', { width: 10, height: 10, style: { position: 'absolute', left: '0px', top: '0px', overflow: 'visible' } }, this.root);
    }
    measure() {
      const r = super.measure();
      const s = this.props.size;
      if (this.titleW) this.titleW.measure(this.root);
      const cc = color(this.scene, this.props.checkColor, '#16A34A');
      this.rows.forEach((rw, i) => {
        rw.w.measure(this.root);
        const b = relBox(rw.bx, this.root), q = rng('chk' + this.id + i);
        const j = () => (q() - 0.5) * 3;
        const x0 = b.x, y0 = b.y, x1 = b.x + b.w, y1 = b.y + b.h, rr = b.w * 0.18;
        rw.box = new InkPath(this, this.svg, `M${x0 + rr},${y0 + j()} L${x1 - rr},${y0 + j()} Q${x1},${y0} ${x1 + j()},${y0 + rr} L${x1 + j()},${y1 - rr} Q${x1},${y1} ${x1 - rr},${y1 + j()} L${x0 + rr},${y1 + j()} Q${x0},${y1} ${x0 + j()},${y1 - rr} L${x0 + j()},${y0 + rr} Q${x0},${y0} ${x0 + rr + 2},${y0}`, { color: INK, width: Math.max(3.5, s * 0.075) });
        rw.check = new InkPath(this, this.svg, `M${x0 + b.w * 0.16},${y0 + b.h * 0.5} L${x0 + b.w * 0.42},${y0 + b.h * 0.8} L${x0 + b.w * 1.08},${y0 - b.h * 0.22}`, { color: cc, width: Math.max(5, s * 0.13) });
        const tb = rw.w.box();
        rw.strike = new InkPath(this, this.svg, `M${tb.x - 4},${tb.y + tb.h * 0.58} L${tb.x + tb.w + 6},${tb.y + tb.h * 0.5}`, { color: INK, width: Math.max(3, s * 0.07) });
      });
      attr(this.svg, 'width', this.w); attr(this.svg, 'height', this.h);
      return r;
    }
    partBox(name) {
      const m = /^item(\d+)$/.exec(name);
      const r = m && this.rows[+m[1]];
      if (!r) throw new Error(`Checklist "${this.id}" has no part "${name}". Parts: ${this.rows.map((_, i) => 'item' + i).join(', ')}`);
      const b = relBox(r.row, this.root), [ox, oy] = this.origin();
      return box(ox + b.x + b.w / 2, oy + b.y + b.h / 2, b.w, b.h);
    }
    itemIndex(item) {
      if (typeof item === 'number') return item;
      const s = String(item).toLowerCase();
      const i = this.rows.findIndex((r) => r.text.toLowerCase().includes(s));
      if (i < 0) throw new Error(`Checklist "${this.id}" has no item matching "${item}"`);
      return i;
    }
    autoDur() {
      return (this.titleW ? this.titleW.estDur() + 0.2 : 0) + this.rows.reduce((a, r) => a + 0.32 + r.w.estDur() + 0.15, 0) + (this.props.checked.length ? 0.5 : 0);
    }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const auto = this.autoDur(), k = args.dur != null ? args.dur / auto : 1;
      let t = at;
      const H = this.handOn;
      if (this.titleW) { const d = this.titleW.estDur() * k; this.titleW.schedule(t, d, H); t += d + 0.2 * k; }
      for (const r of this.rows) {
        r.box.schedule(t, 0.32 * k, H); t += 0.32 * k + 0.05 * k;
        const d = r.w.estDur() * k; r.w.schedule(t, d, H); t += d + 0.1 * k;
      }
      for (const c of this.props.checked) this.a_check(t + 0.1, 0.4 * k, null, { item: c });
    }
    a_write(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_check(at, dur, e, args) {
      const r = this.rows[this.itemIndex(args.item ?? 0)];
      if (!r) return;
      r.check.schedule(at, dur, this.handOn, 'inOut');
      if (this.props.dimDone) r.doneT.to(at + dur, 1, 0.4);
      if (this.props.strike) r.strike.schedule(at + dur + 0.05, 0.35, this.handOn);
    }
    a_checkAll(at, dur, e, args) {
      let t = at;
      this.rows.forEach((r, i) => { if (r.check.t0 == null) { this.a_check(t, dur, null, { item: i }); t += dur + (args.gap ?? 0.12); } });
    }
    a_strike(at, dur, e, args) { this.rows[this.itemIndex(args.item ?? 0)].strike.schedule(at, dur, this.handOn); }
    render(t) {
      super.render(t);
      if (this.titleW) this.titleW.render(t);
      for (const r of this.rows) {
        r.box.render(t); r.w.render(t); r.check.render(t); r.strike.render(t);
        const d = r.doneT.value(t);
        css(r.tx, 'color', d > 0.001 ? mixColor(INK, MUTED, d) : '');
      }
    }
  }

  // ------------------------------------------------------------------ Diagram (boxes + arrows, drawn on)
  class Diagram extends WBNode {
    static defaults = { nodes: [], edges: null, direction: null, boxW: 270, boxH: 196, gap: 140, labelSize: 42, iconSize: 100, hand: true, fill: true, color: null, dashed: false, bend: 0.12 };
    static actions = { enter: {}, draw: {}, step: { dur: 1.3 }, fill: { dur: 0.5 }, highlight: { dur: 0.35 }, unhighlight: { dur: 0.3 }, exit: { dur: 0.4 }, pop: { dur: 0.5 } };
    build() {
      const p = this.props, S = this.scene;
      const dir = p.direction || (S.portrait ? 'column' : 'row');
      const bw = p.boxW, bh = p.boxH, g = p.gap;
      this.nodes = p.nodes.map((n, i) => (typeof n === 'string' ? { id: 'n' + i, label: n } : Object.assign({ id: n.id || 'n' + i }, n)));
      const N = this.nodes.length;
      const cols = dir === 'row' ? N : dir === 'column' ? 1 : (p.cols || Math.ceil(Math.sqrt(N)));
      this.nodes.forEach((n, i) => {
        const c = i % cols, r = Math.floor(i / cols);
        n.x = c * (bw + g); n.y = r * (bh + g); n.w = bw; n.h = bh; n.i = i;
      });
      const rowsN = Math.ceil(N / cols);
      this.W = Math.min(N, cols) * bw + (Math.min(N, cols) - 1) * g;
      this.H = rowsN * bh + (rowsN - 1) * g;
      Object.assign(this.root.style, { width: this.W + 'px', height: this.H + 'px' });
      this.svg = svgEl('svg', { width: this.W, height: this.H, style: { position: 'absolute', left: '0px', top: '0px', overflow: 'visible' } }, this.root);
      const base = color(S, p.color, ACCENT);
      const byId = new Map(this.nodes.map((n) => [n.id, n]));
      for (const n of this.nodes) {
        const nc = color(S, n.color, base);
        n.fillEl = svgEl('path', { d: roundRectD(n.x, n.y, n.w, n.h, 20), fill: tint(nc, 0.87), 'clip-path': '' }, this.svg);
        n.hotEl = svgEl('path', { d: roundRectD(n.x, n.y, n.w, n.h, 20), fill: tint(nc, 0.62), opacity: 1 }, this.svg);
        n.outline = new InkPath(this, this.svg, roundRectD(n.x + 1, n.y + 1, n.w - 2, n.h - 2, 20), { color: INK, width: 5 });
        const cpId = 'wbdg' + (++Drawing.N);
        const cp = svgEl('clipPath', { id: cpId, clipPathUnits: 'userSpaceOnUse' }, this.svg);
        n.poly = svgEl('polygon', { points: '0,0 0,0 0,0' }, cp);
        attr(n.fillEl, 'clip-path', `url(#${cpId})`);
        const cp2 = 'wbdg' + (++Drawing.N);
        const cpe = svgEl('clipPath', { id: cp2, clipPathUnits: 'userSpaceOnUse' }, this.svg);
        n.hotPoly = svgEl('polygon', { points: '0,0 0,0 0,0' }, cpe);
        attr(n.hotEl, 'clip-path', `url(#${cp2})`);
        n.wipe = new Wipe({ x: n.x, y: n.y, w: n.w, h: n.h }, { angle: 24, zig: 5, toStage: (x, y) => { const [ox, oy] = this.origin(); return { x: ox + x, y: oy + y }; } });
        n.hot = null;
        const is = n.icon ? p.iconSize : 0;
        if (n.icon) {
          const holder = svgEl('g', {}, this.svg);
          const a = mountArt(S, holder, { art: n.icon, accent: n.color ? nc : null }, is);
          attr(a.svg, 'x', n.x + (n.w - is) / 2); attr(a.svg, 'y', n.y + 16);
          n.draw = new Drawing(this, a.svg, { scale: () => is / a.vbw, origin: () => { const [ox, oy] = this.origin(); return [ox + n.x + (n.w - is) / 2, oy + n.y + 16]; } });
        }
        n.lab = el('div', { class: 'wb-diag-label', style: { left: n.x + 'px', top: (n.icon ? n.y + 16 + is : n.y) + 'px', width: n.w + 'px', height: (n.icon ? n.h - 16 - is : n.h) + 'px', fontSize: p.labelSize + 'px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' } }, this.root);
        n.writer = new Writer(this, n.lab, n.label ?? '', { emphasisColor: ACCENT });
      }
      // edges: default = chain in node order
      let edges = p.edges;
      if (!edges) edges = this.nodes.slice(1).map((n, i) => ({ from: this.nodes[i].id, to: n.id }));
      this.edges = edges.map((e) => (Array.isArray(e) ? { from: e[0], to: e[1], label: e[2] } : e)).map((e) => {
        const A = byId.get(e.from), B = byId.get(e.to);
        if (!A || !B) throw new Error(`Diagram "${this.id}" edge ${e.from} -> ${e.to}: unknown node. Nodes: ${[...byId.keys()].join(', ')}`);
        const ba = box(A.x + A.w / 2, A.y + A.h / 2, A.w, A.h), bb = box(B.x + B.w / 2, B.y + B.h / 2, B.w, B.h);
        const p0 = edgeToward(ba, bb.cx, bb.cy, 16), p1 = edgeToward(bb, ba.cx, ba.cy, 18);
        const dx = p1[0] - p0[0], dy = p1[1] - p0[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L, bd = (e.bend ?? p.bend) * L;
        const d = `M${p0[0]},${p0[1]} C${p0[0] + dx * 0.3 + nx * bd},${p0[1] + dy * 0.3 + ny * bd} ${p0[0] + dx * 0.7 + nx * bd},${p0[1] + dy * 0.7 + ny * bd} ${p1[0]},${p1[1]}`;
        const ec = color(S, e.color, INK);
        const shaft = new InkPath(this, this.svg, d, { color: ec, width: 5, dashed: e.dashed ?? p.dashed });
        const a = shaft.lut.at(shaft.len - 1), b2 = shaft.lut.at(shaft.len);
        const head = new InkPath(this, this.svg, arrowHeadD(p1, Math.atan2(b2.y - a.y, b2.x - a.x), 22), { color: ec, width: 5 });
        let writer = null;
        if (e.label) {
          const m = shaft.lut.at(shaft.len / 2);
          const lab = el('div', { class: 'wb-diag-label', style: { fontSize: Math.round(p.labelSize * 0.78) + 'px', color: '#3F3F46' } }, this.root);
          writer = new Writer(this, lab, e.label, { emphasisColor: ACCENT });
          const lw = lab.offsetWidth, lh = lab.offsetHeight;
          const off = lh * 0.65 + Math.abs(bd) * 0.75 + 6;
          const horizontal = Math.abs(dx) >= Math.abs(dy);
          const lx = horizontal ? m.x - lw / 2 : m.x + 18, ly = horizontal ? m.y - off - lh / 2 : m.y - lh / 2;
          Object.assign(lab.style, { left: lx + 'px', top: ly + 'px' });
        }
        return { from: A, to: B, shaft, head, writer, done: false };
      });
    }
    measure() {
      this.w = this.W; this.h = this.H;
      for (const n of this.nodes) n.writer.measure(this.root);
      for (const e of this.edges) if (e.writer) e.writer.measure(this.root);
      return { w: this.w, h: this.h };
    }
    partBox(name) {
      const n = this.nodes.find((q) => q.id === name);
      if (!n) throw new Error(`Diagram "${this.id}" has no node "${name}". Nodes: ${this.nodes.map((q) => q.id).join(', ')}`);
      const [ox, oy] = this.origin();
      return box(ox + n.x + n.w / 2, oy + n.y + n.h / 2, n.w, n.h);
    }
    nodeDur(n) { return 0.42 + (this.props.fill ? 0.3 : 0) + (n.draw ? n.draw.estDur(true) + 0.04 : 0) + n.writer.estDur() + 0.08; }
    edgeDur(e) { return 0.5 + (e.writer ? e.writer.estDur() : 0) + 0.05; }
    /** Schedule node n (and its incoming edges from already drawn nodes) from t; returns end time. */
    drawNode(n, t, k) {
      const H = this.handOn;
      for (const e of this.edges) {
        if (e.done || e.to !== n || !e.from.done) continue;
        e.done = true;
        e.shaft.schedule(t, 0.38 * k, H); e.head.schedule(t + 0.38 * k, 0.12 * k, H, 'out'); t += 0.5 * k;
        if (e.writer) { const d = e.writer.estDur() * k; e.writer.schedule(t, d, H); t += d; }
        t += 0.05 * k;
      }
      n.done = true;
      n.outline.schedule(t, 0.42 * k, H); t += 0.42 * k;
      if (this.props.fill) { n.wipe.schedule(t + 0.02, 0.28 * k, this, H, tint(color(this.scene, n.color, color(this.scene, this.props.color, ACCENT)), 0.4)); t += 0.3 * k; }
      if (n.draw) { const d = n.draw.estDur(true) * k; n.draw.schedule(t, d, { hand: H }); t += d + 0.04 * k; }
      const d = n.writer.estDur() * k; n.writer.schedule(t, d, H); t += d + 0.08 * k;
      return t;
    }
    autoDur() {
      const stepped = this.steppedIds();
      return this.nodes.filter((n) => !stepped.has(n.id)).reduce((a, n) => a + this.nodeDur(n), 0) + this.edges.reduce((a, e) => a + (stepped.has(e.to.id) ? 0 : this.edgeDur(e)), 0);
    }
    steppedIds() {
      if (!this._stepped) this._stepped = new Set(flatBeats(this.scene).filter((b) => b.target === this.id && b.action === 'step').map((b) => (b.args || {}).node));
      return this._stepped;
    }
    a_enter(at, dur, e, args) {
      if (this.enterAt != null) return;
      this.enterAt = at;
      this.vis.to(at, 1, 0.01, 'linear');
      const stepped = this.steppedIds();
      const k = args.dur != null ? args.dur / Math.max(0.1, this.autoDur()) : 1;
      let t = at;
      for (const n of this.nodes) if (!stepped.has(n.id)) t = this.drawNode(n, t, k);
      this.endEdges(t, k);
    }
    endEdges(t, k) {
      const H = this.handOn;
      for (const e of this.edges) if (!e.done && e.from.done && e.to.done) { e.done = true; e.shaft.schedule(t, 0.42 * k, H); e.head.schedule(t + 0.42 * k, 0.13 * k, H, 'out'); t += 0.6 * k; if (e.writer) { const d = e.writer.estDur() * k; e.writer.schedule(t, d, H); t += d; } }
      return t;
    }
    a_draw(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_step(at, dur, e, args) {
      const n = this.nodes.find((q) => q.id === args.node);
      if (!n) throw new Error(`Diagram "${this.id}" step: unknown node "${args.node}"`);
      if (this.enterAt == null) { this.enterAt = at; this.vis.to(at, 1, 0.01, 'linear'); }
      const k = args.dur != null ? args.dur / this.nodeDur(n) : 1;
      this.endEdges(this.drawNode(n, at, k), k);
    }
    a_fill(at, dur, e, args) {
      const n = this.nodes.find((q) => q.id === args.node);
      if (!n) throw new Error(`Diagram "${this.id}" fill: unknown node "${args.node}"`);
      if (args.color) attr(n.hotEl, 'fill', tint(color(this.scene, args.color, ACCENT), 0.55));
      n.hot = new Wipe({ x: n.x, y: n.y, w: n.w, h: n.h }, { angle: 24, zig: 5, toStage: (x, y) => { const [ox, oy] = this.origin(); return { x: ox + x, y: oy + y }; } });
      n.hot.schedule(at, dur, this, this.handOn, ACCENT);
    }
    a_highlight(at, dur, e, args) {
      if (args.node == null) return super.a_highlight(at, dur, e, args);
      const n = this.nodes.find((q) => q.id === args.node);
      if (!n.hl) { n.hl = svgEl('path', { d: roundRectD(n.x - 14, n.y - 14, n.w + 28, n.h + 28, 26), fill: 'none', 'stroke-width': 4.5, 'stroke-dasharray': '16 11', 'stroke-linecap': 'round' }, this.svg); n.hlT = new Track(0); n.hlC = new Events(); }
      n.hlC.add(at, { color: color(this.scene, args.color, ACCENT) });
      n.hlT.to(at, 1, dur, 'out');
      if (args.hold != null) n.hlT.to(at + dur + args.hold, 0, 0.3);
    }
    a_unhighlight(at, dur, e, args) {
      if (args.node == null) return super.a_unhighlight(at, dur, e, args);
      const n = this.nodes.find((q) => q.id === args.node);
      if (n && n.hlT) n.hlT.to(at, 0, dur);
    }
    render(t) {
      super.render(t);
      for (const n of this.nodes) {
        n.outline.render(t);
        attr(n.poly, 'points', n.wipe.svgPoints(t));
        attr(n.hotPoly, 'points', n.hot ? n.hot.svgPoints(t) : '0,0 0,0 0,0');
        if (n.draw) n.draw.render(t);
        n.writer.render(t);
        if (n.hl) {
          const h = n.hlT.value(t);
          attr(n.hl, 'opacity', h.toFixed(3)); attr(n.hl, 'stroke', (n.hlC.last(t) || { color: ACCENT }).color);
          attr(n.hl, 'stroke-dashoffset', (-t * 36).toFixed(2));
        }
      }
      for (const e of this.edges) { e.shaft.render(t); e.head.render(t); if (e.writer) e.writer.render(t); }
    }
  }

  // ------------------------------------------------------------------ registration
  register('HandLayer', HandLayer);
  register('HandDraw', HandDraw);
  register('Icon', Icon);
  register('HandPlace', HandPlace);
  register('SketchText', SketchText);
  register('KineticText', KineticText);
  register('ChapterCard', ChapterCard);
  register('Arrow', Arrow);
  register('Chevrons', Chevrons);
  register('MarchingBox', MarchingBox);
  register('PillLabel', PillLabel);
  register('PointerHand', PointerHand);
  register('UIMock', UIMock);
  register('Checklist', Checklist);
  register('Diagram', Diagram);

  // ------------------------------------------------------------------ layout
  const PLACES_L = {
    center: [0.5, null], left: [0.27, null], right: [0.73, null], 'far-left': [0.16, null], 'far-right': [0.84, null],
    top: [0.5, 0.34], bottom: [0.5, 0.76], 'top-left': [0.27, 0.34], 'top-right': [0.73, 0.34], 'bottom-left': [0.27, 0.76], 'bottom-right': [0.73, 0.76],
  };
  const PLACES_P = {
    center: [0.5, null], left: [0.3, null], right: [0.7, null], 'far-left': [0.22, null], 'far-right': [0.78, null],
    top: [0.5, 0.3], bottom: [0.5, 0.75], 'top-left': [0.3, 0.3], 'top-right': [0.7, 0.3], 'bottom-left': [0.3, 0.75], 'bottom-right': [0.7, 0.75],
  };
  registerLayout('whiteboard-saas', (S) => {
    const W = S.W, H = S.H, P = S.portrait;
    let top = P ? 120 : 70;
    if (S.has('title')) {
      const tt = S.get('title'), tp = tt.props;
      if (tp.x != null || tp.y != null) tt.place(frac(tp.x ?? 0.5, W), frac(tp.y ?? 0.12, H));
      else tt.place(W / 2, (P ? 170 : 64) + tt.h / 2);
      top = tt.cy + tt.h / 2 + (P ? 70 : 46);
    }
    const bottom = H - (P ? 160 : 70);
    const mid = (top + bottom) / 2;
    const PL = P ? PLACES_P : PLACES_L;
    const flow = [];
    for (const e of S.list) {
      if (!e.constructor.isNode || e.id === 'title') continue;
      const p = e.props;
      if (p.x != null || p.y != null) e.place(p.x != null ? frac(p.x, W) : W / 2, p.y != null ? frac(p.y, H) : mid);
      else if (p.place && PL[p.place]) { const [fx, fy] = PL[p.place]; e.place(fx * W, fy == null ? mid : fy * H); }
      else if (p.place) throw new Error(`Unknown place "${p.place}" for "${e.id}". Use: ${Object.keys(PL).join(', ')} or x/y`);
      else flow.push(e);
    }
    if (flow.length) {
      if (!P) {
        const sumW = flow.reduce((a, e) => a + e.w, 0);
        const g = clamp((W - 200 - sumW) / Math.max(1, flow.length - 1), 60, 200);
        let x = W / 2 - (sumW + g * (flow.length - 1)) / 2;
        for (const e of flow) { e.place(x + e.w / 2, mid); x += e.w + g; }
      } else {
        const sumH = flow.reduce((a, e) => a + e.h, 0);
        const g = clamp((bottom - top - sumH) / (flow.length + 1), 40, 240);
        let y = mid - (sumH + g * (flow.length - 1)) / 2;
        for (const e of flow) { e.place(W / 2, y + e.h / 2); y += e.h + g; }
      }
    }
    for (const e of S.list) if (e.constructor.isNode && (e.props.dx || e.props.dy)) e.place(e.cx + (e.props.dx || 0), e.cy + (e.props.dy || 0));

    // the shared drawing hand (top-most layer)
    if (!S.has('__hand')) S.spawn({ id: '__hand', primitive: 'HandLayer' });

    // Auto-entrance queue: elements without an entrance beat enter one after another, in element order.
    const explicit = new Map();
    for (const b of flatBeats(S)) if (ENTRY.has(b.action)) { const id = b.target; if (!explicit.has(id) || b.at < explicit.get(id)) explicit.set(id, b.at); }
    let cursor = 0.25;
    const ready = new Map();
    for (const e of S.list) {
      if (e.id === '__hand') continue;
      const C = e.constructor, est = e.autoDur ? e.autoDur() : 0.6;
      if (explicit.has(e.id)) { e.props.auto = false; ready.set(e.id, explicit.get(e.id) + est); cursor = Math.max(cursor, explicit.get(e.id) + est + 0.2); continue; }
      if (C.autoEnter === false || e.props.auto === false) continue;
      let at = e.props.enterAt;
      if (at == null && C.autoEnterAt != null) at = C.autoEnterAt;
      if (at == null) {
        at = cursor;
        for (const d of (C.deps ? C.deps(e) : [])) if (ready.has(d)) at = Math.max(at, ready.get(d) + 0.1);
      }
      e.props.enterAt = at;
      ready.set(e.id, at + est);
      if (!(e instanceof ChapterCard)) cursor = Math.max(cursor, at + est + 0.2);
    }
  });
})();
