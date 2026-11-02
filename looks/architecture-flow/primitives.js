/* architecture-flow Look: Primitives. Scene vocabulary is documented in PRIMITIVES.md.
 * All animation state is compiled from Beats into tracks at build time; render(t) is pure. */
(function () {
  'use strict';
  const {
    Primitive, Track, Events, SpeedProfile, PathLUT, register, registerLayout,
    el, svgEl, css, attr, text, clamp, lerp, prog, bump, getEase, ease, rgba, mixColor,
    drawOn, marchingAnts, morph, route, box, splitWords, revealWords, revealDuration,
    formatNumber, parseNumber, noise,
  } = window.CA;

  const C = {
    link: '#4B5563', alert: '#F43F5E', ok: '#22C55E', white: '#FFFFFF', text: '#F4F4F5',
    cardBorder: '#2A2A2E', dim: '#A1A1AA', neutralPill: '#E4E4E7', expired: '#3F3F46',
  };

  // ------------------------------------------------------------------ helpers
  function icon(name, color = '#E4E4E7', size = 24, sw = 2) {
    const inner = (window.CLIPAGENT_ICONS || {})[name] || (window.CLIPAGENT_ICONS || {}).box || '';
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
  }
  function relBox(node, root) {
    let x = 0, y = 0;
    for (let e = node; e && e !== root; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
    return { x, y, w: node.offsetWidth, h: node.offsetHeight };
  }
  /** Entrance style: fade (via opacity in base), rise and de-blur. */
  function enterFx(root, v, rise = 18) {
    css(root, 'transform', v >= 0.999 ? 'none' : `translateY(${((1 - v) * rise).toFixed(2)}px) scale(${(0.965 + 0.035 * v).toFixed(4)})`);
    css(root, 'filter', v >= 0.999 ? 'none' : `blur(${((1 - v) * 8).toFixed(2)}px)`);
  }
  function spinnerSvg(color, size = 30) {
    return `<svg viewBox="0 0 30 30" width="${size}" height="${size}"><circle cx="15" cy="15" r="11" fill="none" stroke="${rgba(color, 0.22)}" stroke-width="3"/><path d="M15 4 A11 11 0 0 1 26 15" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round"/></svg>`;
  }
  const blankDots = (s) => String(s);

  // ------------------------------------------------------------------ row mixin (ServiceCard rows, Database rows)
  /** Per-row state: dashed box, background tint flashes, value changes, validate glyphs. */
  class Rows {
    constructor(host) { this.host = host; this.rows = []; }
    add(rowEl, cells) { this.rows.push({ el: rowEl, cells, bg: rowEl.querySelector('.bg'), hl: new Track(0), hlColor: new Events(), tints: [], values: [] }); }
    index(r) {
      if (r == null) return 0;
      if (typeof r === 'number') return clamp(r, 0, this.rows.length - 1);
      const s = String(r).toLowerCase();
      const i = this.rows.findIndex((row) => row.cells.some((c) => c.textContent.toLowerCase() === s || c.textContent.toLowerCase().includes(s)));
      if (i < 0) throw new Error(`${this.host.id}: no row matching "${r}"`);
      return i;
    }
    box(i) {
      const r = this.rows[i];
      const b = relBox(r.el, this.host.root);
      const hb = this.host.box;
      return box(hb.x + b.x + b.w / 2, hb.y + b.y + b.h / 2, b.w, b.h);
    }
    highlight(i, at, dur, color, hold) {
      const r = this.rows[i];
      r.hlColor.add(at, { color });
      r.hl.to(at, 1, dur, 'out');
      if (hold != null) r.hl.to(at + dur + hold, 0, 0.35, 'smooth');
    }
    tint(i, at, dur, color) { this.rows[i].tints.push({ at, dur, color }); }
    render(t, opacity) {
      const H = this.host;
      this.rows.forEach((r, i) => {
        // tint
        let amt = 0, col = C.white;
        for (const f of r.tints) { const a = bump(t, f.at, f.dur); if (a > amt) { amt = a; col = f.color; } }
        if (r.bg) { css(r.bg, 'opacity', (amt * 0.9).toFixed(3)); css(r.bg, 'background', rgba(col, 0.22)); }
        // value changes
        for (const v of r.values) v.render(t);
        // dashed box
        const h = r.hl.value(t) * opacity;
        if (h <= 0.001 && !r.box) return;
        if (!r.box) r.box = svgEl('rect', { fill: 'none', 'stroke-width': 2.2, 'stroke-dasharray': '8 6', rx: 9 }, H.scene.layers.fx);
        const b = this.box(i);
        const pad = 4 + (1 - h) * 6;
        const c = (r.hlColor.last(t) || { color: C.white }).color;
        attr(r.box, 'x', (b.x - pad).toFixed(1)); attr(r.box, 'y', (b.y - pad).toFixed(1));
        attr(r.box, 'width', (b.w + 2 * pad).toFixed(1)); attr(r.box, 'height', (b.h + 2 * pad).toFixed(1));
        attr(r.box, 'stroke', c); attr(r.box, 'opacity', h.toFixed(3));
        css(r.box, 'filter', `drop-shadow(0 0 5px ${rgba(c, 0.6)})`);
        marchingAnts(r.box, t, 24);
      });
    }
  }

  /** Value-change animation for one cell (numbers count, text blur-swaps). */
  class CellValue {
    constructor(cell) { this.cell = cell; this.baseColor = cell.style.color || ''; this.events = [{ at: -1, value: cell.textContent, dur: 0, color: null }]; }
    set(at, value, dur, color) { this.events.push({ at, value: String(value), dur, color }); }
    render(t) {
      let i = 0;
      for (let k = 0; k < this.events.length; k++) if (this.events[k].at <= t) i = k;
      const e = this.events[i], prev = this.events[Math.max(0, i - 1)];
      const p = e.dur > 0 ? clamp((t - e.at) / e.dur) : 1;
      const a = parseNumber(prev.value), b = parseNumber(e.value);
      if (i > 0 && p < 1 && a && b && a.suffix === b.suffix) {
        text(this.cell, formatNumber(lerp(a.num, b.num, ease.smooth(p)), { decimals: b.decimals, prefix: b.prefix, suffix: b.suffix, sep: b.sep || a.sep }));
        css(this.cell, 'filter', 'none'); css(this.cell, 'opacity', '1');
      } else if (i > 0 && p < 1) {
        const half = p < 0.5;
        text(this.cell, half ? prev.value : e.value);
        const q = half ? p * 2 : (1 - p) * 2;
        css(this.cell, 'filter', `blur(${(q * 6).toFixed(2)}px)`); css(this.cell, 'opacity', (1 - q * 0.8).toFixed(3));
      } else { text(this.cell, e.value); css(this.cell, 'filter', 'none'); css(this.cell, 'opacity', '1'); }
      css(this.cell, 'color', e.color || this.baseColor);
    }
  }

  // validate glyph shapes (single polygons so flubber can morph them)
  const EQ_TOP = 'M-10,-7 L10,-7 L10,-2.5 L-10,-2.5 Z';
  const EQ_BOT = 'M-10,2.5 L10,2.5 L10,7 L-10,7 Z';
  const CHECK = 'M-11,0.5 L-7.8,-2.7 L-3.2,1.9 L7.8,-9.1 L11,-5.9 L-3.2,8.3 Z';
  const CROSS = 'M-8.5,-11.7 L0,-3.2 L8.5,-11.7 L11.7,-8.5 L3.2,0 L11.7,8.5 L8.5,11.7 L0,3.2 L-8.5,11.7 L-11.7,8.5 L-3.2,0 L-11.7,-8.5 Z';

  /** Lookup & validation, shared by Database and ServiceCard. */
  function compileValidate(host, at, dur, e, args) {
    const S = host.scene;
    const pill = S.get(args.pill);
    const i = host.rows.index(args.row);
    const rb = host.rows.box(i);
    const hb = host.box;
    const match = args.result !== 'mismatch' && args.match !== false;
    const side = args.side || (hb.x > S.W - hb.r ? 'left' : 'right'); // side with more room
    const gap = S.portrait ? 56 : 70;
    const px = side === 'left' ? hb.x - gap - pill.w / 2 : hb.r + gap + pill.w / 2;
    const gx = side === 'left' ? hb.x - gap / 2 : hb.r + gap / 2;
    const travel = args.travel ?? 0.8;
    pill.travelTo(at, travel, [px, rb.cy], { toNode: host, ease: 'smooth' });
    const tEq = at + travel;
    const tRes = tEq + (args.compare ?? 0.45);
    const hold = args.hold ?? 1.6;
    const good = match ? S.token('ok', C.ok) : S.token('alert', C.alert);
    host.rows.highlight(i, tEq - 0.1, 0.3, C.white, null);
    host.rows.rows[i].hlColor.add(tRes, { color: good });
    host.rows.tint(i, tRes, 0.9, good);
    const tEnd = tRes + 0.45 + hold;
    host.rows.rows[i].hl.to(tEnd, 0, 0.35, 'smooth');
    pill.flash(tRes, 0.8, good);
    if (!match) pill.shake(tRes, 0.5);
    host.glyphs.push({ x: gx, y: rb.cy, tEq, tRes, tEnd, match, color: good });
    const after = args.after || 'fade';
    if (after === 'fade') pill.hideAt(tEnd, 0.35, host);
  }

  function renderGlyphs(host, t, op) {
    for (const g of host.glyphs) {
      if (!g.el) {
        g.el = svgEl('g', {}, host.scene.layers.fx);
        g.circle = svgEl('circle', { r: 21, fill: 'none', 'stroke-width': 2.5 }, g.el);
        g.top = svgEl('path', { fill: C.white }, g.el);
        g.bot = svgEl('path', { fill: C.white, d: EQ_BOT }, g.el);
        g.morph = morph(EQ_TOP, g.match ? CHECK : CROSS);
      }
      const a = prog(t, g.tEq, 0.25, 'out') * (1 - prog(t, g.tEnd, 0.35, 'smooth')) * op;
      attr(g.el, 'opacity', a.toFixed(3));
      if (a <= 0.001) continue;
      const m = prog(t, g.tRes, 0.4, 'smooth');
      const s = 1 + 0.25 * bump(t, g.tRes, 0.5);
      attr(g.el, 'transform', `translate(${g.x.toFixed(1)},${g.y.toFixed(1)}) scale(${s.toFixed(3)})`);
      attr(g.top, 'd', g.morph(m));
      const col = m > 0 ? mixColor(C.white, g.color, clamp(m * 1.5)) : C.white;
      attr(g.top, 'fill', m > 0.6 ? '#0A0A0A' : col);
      attr(g.bot, 'opacity', (1 - clamp(m * 2)).toFixed(3));
      attr(g.circle, 'stroke', g.color);
      attr(g.circle, 'fill', m > 0.5 ? g.color : 'none');
      attr(g.circle, 'fill-opacity', clamp((m - 0.5) * 2).toFixed(3));
      drawOn(g.circle, prog(t, g.tRes, 0.45, 'smooth'), 2 * Math.PI * 21);
      attr(g.circle, 'transform', 'rotate(-90)');
      css(g.el, 'filter', m > 0 ? `drop-shadow(0 0 ${(10 * m).toFixed(1)}px ${rgba(g.color, 0.8)})` : 'none');
    }
  }

  // ------------------------------------------------------------------ SectionTitle
  class SectionTitle extends Primitive {
    static layer = 'text';
    static defaults = { text: '', underline: true, color: null };
    static actions = { enter: { dur: 0.9, ease: 'out' }, exit: { dur: 0.4 }, set: { dur: 0.8 } };
    static autoEnterAt = 0.05;
    build() {
      this.root.classList.add('af-title');
      this.variants = [];
      this.addVariant(-1, this.props.text);
      this.ul = svgEl('svg', { width: 10, height: 16 }, this.root);
      const conceptSpan = this.variants[0].spans.find((sp) => sp.style.color);
      const ulColor = this.scene.resolveColor(this.props.color) || (conceptSpan && conceptSpan.style.color) || this.scene.look.accent || '#38BDF8';
      this.ulPath = svgEl('path', { fill: 'none', stroke: ulColor, 'stroke-width': 4, 'stroke-linecap': 'round' }, this.ul);
    }
    addVariant(at, str) {
      const d = el('div', { class: 'txt' }, this.root);
      if (this.variants.length) Object.assign(d.style, { position: 'absolute', left: 0, right: 0, top: 0 });
      const spans = splitWords(d, String(str), { colorFor: (w) => this.scene.colorFor(w) });
      this.variants.push({ at, el: d, spans });
    }
    measure() {
      if (this.scene.portrait) { this.root.style.whiteSpace = 'normal'; this.root.style.width = '860px'; }
      const tw = this.variants[0].el.offsetWidth;
      const uw = Math.min(tw * 0.86, 980);
      attr(this.ul, 'width', uw); attr(this.ul, 'viewBox', `0 0 ${uw} 16`);
      attr(this.ulPath, 'd', `M4,10 C${uw * 0.3},4 ${uw * 0.6},13 ${uw - 4},6`);
      this.ulLen = uw * 1.02;
      return super.measure();
    }
    afterLayout() { this.place(this.scene.W / 2, this.scene.portrait ? 140 : 84); }
    a_enter(at, dur, e) { super.a_enter(at, 0.01, 'linear'); this.enterAt = at; this.revealDur = dur; }
    a_set(at, dur, e, args) { this.addVariant(at, args.text); this.variants[this.variants.length - 1].dur = dur; }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      if (v <= 0) return;
      const ea = this.enterAt ?? 0;
      this.variants.forEach((vr, i) => {
        const next = this.variants[i + 1];
        const start = i === 0 ? ea : vr.at;
        const outP = next ? prog(t, next.at, 0.3, 'in') : 0;
        css(vr.el, 'opacity', (1 - outP).toFixed(3));
        css(vr.el, 'filter', outP > 0 ? `blur(${(outP * 10).toFixed(1)}px)` : 'none');
        const local = t - (i === 0 ? start : start + 0.2);
        revealWords(vr.spans, local, { stagger: 0.08, wordDur: 0.5, blur: 12, rise: 10 });
      });
      drawOn(this.ulPath, prog(t, ea + 0.35, 0.6, 'smooth'), this.ulLen);
    }
  }

  // ------------------------------------------------------------------ HookQuestion
  class HookQuestion extends Primitive {
    static layer = 'text';
    static defaults = { text: '', stagger: 0.11 };
    static actions = { enter: { dur: null }, reveal: { dur: null }, exit: { dur: 0.45 }, set: { dur: null } };
    static autoEnterAt = 0.6;
    build() {
      this.root.classList.add('af-hook');
      this.variants = [];
      this.addVariant(-1, this.props.text);
    }
    addVariant(at, str) {
      const d = el('div', {}, this.root);
      if (this.variants.length) Object.assign(d.style, { position: 'absolute', left: 0, right: 0, top: 0 });
      const spans = splitWords(d, String(str), { colorFor: (w) => this.scene.colorFor(w), emphasisColor: this.scene.look.accent });
      this.variants.push({ at, el: d, spans, stagger: this.props.stagger });
    }
    measure() {
      this.root.style.width = (this.scene.portrait ? 860 : 1600) + 'px';
      return super.measure();
    }
    afterLayout() { this.place(this.scene.W / 2, this.scene.H - (this.scene.portrait ? 160 : 46) - this.h / 2); }
    stg(n, dur) { return dur && n > 1 ? Math.max(0.03, (dur - 0.5) / (n - 1)) : this.props.stagger; }
    a_enter(at, dur, e, args) { super.a_enter(at, 0.01, 'linear'); this.variants[0].at = at; this.variants[0].stagger = this.stg(this.variants[0].spans.length, args.dur); }
    a_reveal(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_set(at, dur, e, args) { this.addVariant(at + 0.25, args.text); const v = this.variants[this.variants.length - 1]; v.stagger = this.stg(v.spans.length, args.dur); v.outAt = at; }
    render(t) {
      super.render(t);
      if (this.vis.value(t) <= 0) return;
      this.variants.forEach((vr, i) => {
        const next = this.variants[i + 1];
        const outP = next ? prog(t, next.outAt, 0.3, 'in') : 0;
        css(vr.el, 'opacity', (1 - outP).toFixed(3));
        css(vr.el, 'filter', outP > 0 ? `blur(${(outP * 10).toFixed(1)}px)` : 'none');
        revealWords(vr.spans, t - vr.at, { stagger: vr.stagger, wordDur: 0.5, blur: 14, rise: 12 });
      });
    }
  }

  // ------------------------------------------------------------------ cards
  function cardHeader(root, p, scene) {
    const accent = scene.resolveColor(p.accent) || '#E4E4E7';
    const hd = el('div', { class: 'hd' }, root);
    const ic = el('div', { class: 'ic' }, hd, icon(p.icon, accent, 24));
    if (p.accent) { ic.style.borderColor = rgba(accent, 0.35); ic.style.background = rgba(accent, 0.1); }
    const tt = el('div', { class: 'tt' }, hd);
    el('div', { class: 'title' }, tt).textContent = p.title;
    if (p.subtitle) el('div', { class: 'sub' }, tt).textContent = p.subtitle;
    const spin = el('div', { class: 'spin' }, hd, spinnerSvg(C.alert, 30));
    spin.style.opacity = '0';
    return { hd, ic, spin, arc: spin.querySelector('path') };
  }

  class CardBase extends Primitive {
    static isNode = true;
    static actions = {
      enter: { dur: 0.7, ease: 'out' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 },
      highlight: { dur: 0.35, ease: 'out' }, alert: { dur: 0.35, ease: 'out' }, unhighlight: { dur: 0.3 }, pulse: { dur: 0.6 },
      receive: { dur: 0.6 }, latency: { dur: 0.6 }, recover: { dur: 0.6 }, spinner: { dur: 0.3 },
      setRow: { dur: 0.6 }, highlightRow: { dur: 0.35, ease: 'out' }, unhighlightRow: { dur: 0.3 }, validate: { dur: 1.3 },
    };
    constructor(...a) { super(...a); this.lat = new Track(0); this.spin = new Track(0); this.rows = new Rows(this); this.glyphs = []; }
    a_receive(at, dur, e, args) { this.flash(at, dur, this.scene.resolveColor(args.color) || C.white); }
    a_latency(at, dur, e, args) {
      this.lat.to(at, 1, dur, e);
      if (args.spinner !== false) this.spin.to(at, 1, 0.3, 'out');
      const factor = args.factor ?? 0.3;
      if (args.streams !== false) for (const s of this.scene.list) if (s instanceof PacketStream && s.touches(this.id)) s.addSpeed(at, factor, 0.8);
      for (const id of args.dependents || []) this.scene.get(id).spin.to(at + 0.2, 1, 0.3, 'out');
    }
    a_recover(at, dur, e, args) {
      this.lat.to(at, 0, dur, e); this.spin.to(at, 0, 0.3, 'smooth');
      if (args.streams !== false) for (const s of this.scene.list) if (s instanceof PacketStream && s.touches(this.id)) s.addSpeed(at, 1, 0.8);
      for (const id of args.dependents || []) this.scene.get(id).spin.to(at, 0, 0.3, 'smooth');
    }
    a_spinner(at, dur, e, args) { this.spin.to(at, args.on === false ? 0 : 1, dur, e); }
    a_setRow(at, dur, e, args) {
      const i = this.rows.index(args.row);
      const r = this.rows.rows[i];
      const cell = r.valueCell;
      if (!r.cv) { r.cv = new CellValue(cell); r.values.push(r.cv); }
      r.cv.set(at, args.value, dur, this.scene.resolveColor(args.color));
      this.rows.tint(i, at, 0.8, this.scene.resolveColor(args.color) || C.white);
    }
    a_highlightRow(at, dur, e, args) {
      const c = args.color === 'red' ? this.scene.token('alert', C.alert) : (this.scene.resolveColor(args.color) || C.white);
      this.rows.highlight(this.rows.index(args.row), at, dur, c, args.hold);
    }
    a_unhighlightRow(at, dur, e, args) { this.rows.rows[this.rows.index(args.row)].hl.to(at, 0, dur, e); }
    a_validate(at, dur, e, args) { compileValidate(this, at, dur, e, args); }
    render(t) {
      super.render(t);
      const v = this.vis.value(t), d = this.dimT.value(t);
      enterFx(this.root, v);
      const lat = this.lat.value(t);
      const f = this.flashAt(t);
      const border = lat > 0 ? mixColor(C.cardBorder, C.alert, lat) : (f.amt > 0 ? mixColor(C.cardBorder, f.color, f.amt * 0.8) : C.cardBorder);
      css(this.root, 'borderColor', border);
      let sh = '0 18px 40px rgba(0,0,0,0.55)';
      if (lat > 0) sh += `, 0 0 0 1px ${rgba(C.alert, 0.6 * lat)}, 0 0 36px ${rgba(C.alert, 0.32 * lat)}`;
      if (f.amt > 0) sh += `, 0 0 ${(40 * f.amt).toFixed(1)}px ${rgba(f.color, 0.45 * f.amt)}`;
      css(this.root, 'boxShadow', sh);
      const sp = this.spin.value(t);
      css(this.head.spin, 'opacity', sp.toFixed(3));
      if (sp > 0) css(this.head.spin, 'transform', `rotate(${((t * 400) % 360).toFixed(1)}deg)`);
      if (this.rowsWrap) css(this.rowsWrap, 'opacity', (1 - 0.35 * sp).toFixed(3));
      this.rows.render(t, v * d);
      renderGlyphs(this, t, d);
    }
  }

  class ServiceCard extends CardBase {
    static defaults = { title: 'Service', subtitle: null, icon: 'server', rows: null, blades: 0, width: 360, accent: null, place: 'server' };
    build() {
      const p = this.props;
      this.root.classList.add('af-card');
      this.root.style.width = p.width + 'px';
      this.head = cardHeader(this.root, p, this.scene);
      if (p.rows && p.rows.length) {
        this.rowsWrap = el('div', { class: 'rows' }, this.root);
        for (const r of p.rows) {
          let k, v;
          if (Array.isArray(r)) [k, v] = r; else if (typeof r === 'object') ({ k, v } = r); else { const m = String(r).split(/:\s*/); k = m[0]; v = m.slice(1).join(': '); }
          const row = el('div', { class: 'af-row' }, this.rowsWrap);
          el('div', { class: 'bg' }, row);
          const kc = el('div', { class: 'k' }, row); kc.textContent = k;
          const vc = el('div', { class: 'v' }, row); vc.textContent = v ?? '';
          const col = (typeof r === 'object' && !Array.isArray(r) && r.color) ? this.scene.resolveColor(r.color) : this.scene.colorFor(v);
          if (col) vc.style.color = col;
          this.rows.add(row, [kc, vc]);
          this.rows.rows[this.rows.rows.length - 1].valueCell = vc;
        }
      }
      this.blades = [];
      for (let i = 0; i < (p.blades || 0); i++) {
        const b = el('div', { class: 'af-blade' }, this.root);
        const leds = [el('div', { class: 'led' }, b), el('div', { class: 'led' }, b)];
        el('div', { class: 'vent' }, b);
        el('div', { class: 'bl' }, b).textContent = (p.bladeLabel || 'node') + '-' + String(i + 1).padStart(2, '0');
        this.blades.push({ el: b, leds });
      }
      if (!this.rowsWrap && !this.blades.length) this.root.style.paddingBottom = '6px';
      else if (this.blades.length) this.root.style.paddingBottom = '14px';
    }
    render(t) {
      super.render(t);
      const lat = this.lat.value(t);
      this.blades.forEach((b, i) => b.leds.forEach((led, j) => {
        const on = noise(this.id + i + '-' + j, Math.floor(t * (6 + j * 3))) > (lat > 0.5 ? 0.55 : 0.25);
        css(led, 'background', lat > 0.5 && j === 1 ? C.alert : C.ok);
        css(led, 'opacity', on ? '1' : '0.25');
        css(led, 'boxShadow', on ? `0 0 8px ${rgba(lat > 0.5 && j === 1 ? C.alert : C.ok, 0.9)}` : 'none');
      }));
    }
  }

  class Database extends CardBase {
    static defaults = { title: 'Database', subtitle: null, icon: 'database', columns: null, rows: [], width: null, accent: null, place: 'store' };
    static actions = { lookup: { dur: 1.0 }, insertRow: { dur: 0.6 } };
    build() {
      const p = this.props;
      this.root.classList.add('af-card');
      const ncols = p.columns ? p.columns.length : (p.rows[0] || []).length;
      const auto = this.scene.portrait ? Math.max(360, Math.min(480, 180 * ncols + 20)) : Math.max(400, Math.min(560, 210 * ncols + 30));
      this.root.style.width = (p.width || auto) + 'px';
      this.head = cardHeader(this.root, p, this.scene);
      const table = (this.rowsWrap = el('div', { class: 'af-table' }, this.root));
      const ncol = p.columns ? p.columns.length : (p.rows[0] || []).length;
      if (p.columns) {
        const th = el('div', { class: 'af-thead' }, table);
        p.columns.forEach((c, i) => { const d = el('div', {}, th); d.textContent = c; if (p.flex) d.style.flex = p.flex[i]; });
      }
      this.tbody = el('div', {}, table);
      this.scan = el('div', {}, table);
      Object.assign(this.scan.style, { position: 'absolute', left: '14px', right: '14px', height: '40px', borderRadius: '8px', background: rgba('#FFFFFF', 0.08), opacity: 0 });
      table.style.position = 'relative';
      this.pending = [];
      for (const r of p.rows) this.addRow(r, ncol);
    }
    addRow(r, ncol) {
      const row = el('div', { class: 'af-trow' }, this.tbody);
      el('div', { class: 'bg' }, row);
      const cells = [];
      for (let i = 0; i < (ncol || r.length); i++) {
        const c = el('div', { class: 'c' + (i > 0 ? ' dim' : '') }, row);
        c.textContent = r[i] ?? '';
        if (this.props.flex) c.style.flex = this.props.flex[i];
        const col = this.scene.colorFor(r[i]);
        if (col) c.style.color = col;
        cells.push(c);
      }
      this.rows.add(row, cells);
      this.rows.rows[this.rows.rows.length - 1].valueCell = cells[cells.length - 1];
      return row;
    }
    a_lookup(at, dur, e, args) {
      const i = this.rows.index(args.row);
      this.lookups = this.lookups || [];
      this.lookups.push({ at, dur, i });
      const c = args.color === 'red' ? C.alert : (this.scene.resolveColor(args.color) || C.white);
      this.rows.highlight(i, at + dur * 0.85, 0.3, c, args.hold ?? 1.4);
    }
    a_insertRow(at, dur, e, args) {
      const ncol = this.props.columns ? this.props.columns.length : args.values.length;
      // rows are pre-built at build time only; inserted rows are added hidden and revealed (height animates from 0)
      const row = this.addRow(args.values, ncol);
      row._insert = { at, dur };
      this.inserted = this.inserted || [];
      this.inserted.push(row);
      this.flash(at, 0.6, C.ok);
    }
    afterLayout() {
      // inserted rows were added during compile (after layout) in older flows; nothing to do here
    }
    render(t) {
      super.render(t);
      for (const row of this.inserted || []) {
        const p = prog(t, row._insert.at, row._insert.dur, 'out');
        css(row, 'opacity', p.toFixed(3));
        css(row, 'transform', p >= 1 ? 'none' : `translateX(${((1 - p) * -16).toFixed(1)}px)`);
      }
      let sv = 0, top = 0;
      for (const L of this.lookups || []) {
        if (t < L.at || t > L.at + L.dur + 0.3) continue;
        const p = clamp((t - L.at) / L.dur);
        const rowsTop = this.rows.rows[0].el.offsetTop;
        const tgt = this.rows.rows[L.i].el.offsetTop;
        top = lerp(rowsTop, tgt, ease.smooth(clamp(p / 0.85)));
        sv = Math.min(1, p * 5) * (1 - prog(t, L.at + L.dur, 0.3, 'smooth'));
      }
      css(this.scan, 'opacity', sv.toFixed(3));
      css(this.scan, 'top', top.toFixed(1) + 'px');
    }
  }
  // Database inserts rows at compile time, which changes its height. Re-measure lazily is not possible after layout,
  // so we pre-reserve: insertRow beats are scanned before build.
  const origBuild = Database.prototype.build;
  Database.prototype.build = function () {
    origBuild.call(this);
    const ins = (this.scene.spec.beats || []).filter((b) => b.target === this.id && b.action === 'insertRow');
    this._reserved = ins.length;
    if (ins.length) this.tbody.style.minHeight = (this.props.rows.length + ins.length) * 40 + 'px';
  };

  // ------------------------------------------------------------------ Device (smartphone wireframe)
  class Device extends Primitive {
    static isNode = true;
    static defaults = { label: 'Client', screen: 'login', app: 'Acme', user: 'alice@acme.io', accent: null, place: 'client' };
    static actions = {
      enter: { dur: 0.8, ease: 'out' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 },
      highlight: { dur: 0.35, ease: 'out' }, alert: { dur: 0.35, ease: 'out' }, unhighlight: { dur: 0.3 }, pulse: { dur: 0.6 }, receive: { dur: 0.6 },
      screen: { dur: 0.45 }, tap: { dur: 0.55 },
    };
    build() {
      const p = this.props;
      this.accent = this.scene.resolveColor(p.accent) || this.scene.look.accent || '#38BDF8';
      this.root.classList.add('af-device');
      this.phone = el('div', { class: 'af-phone' }, this.root);
      el('div', { class: 'btn' }, this.phone); el('div', { class: 'btn l' }, this.phone);
      this.screenEl = el('div', { class: 'af-screen' }, this.phone);
      el('div', { class: 'af-notch' }, this.screenEl);
      el('div', { class: 'af-status' }, this.screenEl, '<span>9:41</span><span class="bat"></span>');
      el('div', { class: 'af-homebar' }, this.screenEl);
      this.tray = el('div', { class: 'af-tray' }, this.screenEl);
      el('div', { class: 'cap' }, this.tray).textContent = p.storageLabel || 'Secure storage';
      this.trayT = new Track(0);
      this.ripple = el('div', {}, this.screenEl);
      Object.assign(this.ripple.style, { position: 'absolute', width: '80px', height: '80px', borderRadius: '50%', border: '2px solid #fff', opacity: 0, zIndex: 5 });
      if (p.label) el('div', { class: 'af-dlabel' }, this.root).textContent = p.label;
      this.screens = {};
      this.screenEv = new Events();
      this.addScreen(-1, p.screen);
      this.taps = [];
      this.slots = [];
    }
    screenKey(s) { return typeof s === 'string' ? s : JSON.stringify(s); }
    addScreen(at, s) {
      const key = this.screenKey(s);
      if (!this.screens[key]) this.screens[key] = this.makeScreen(s);
      const ev = { key };
      this.screenEv.add(at, ev);
      return this.screenEv.list.find((x) => x.key === key && x.at === at);
    }
    makeScreen(s) {
      const o = typeof s === 'string' ? { state: s } : s;
      const A = this.scene.resolveColor(o.color) || this.accent;
      const d = el('div', { class: 'af-scr' }, this.screenEl);
      d.style.opacity = 0;
      const P = this.props;
      const st = o.state || 'custom';
      if (st === 'login') {
        el('div', { class: 'logo', style: { background: rgba(A, 0.16), border: `1px solid ${rgba(A, 0.4)}` } }, d, icon('lock', A, 24));
        el('div', { class: 'apptitle' }, d).textContent = o.title || 'Welcome back';
        el('div', { class: 'appsub' }, d).textContent = o.subtitle || `Sign in to ${P.app}`;
        el('div', { class: 'field' }, d).textContent = P.user;
        el('div', { class: 'field', style: { letterSpacing: '0.2em' } }, d).textContent = '••••••••';
        this.button = el('div', { class: 'button', style: { background: A } }, d);
        this.button.textContent = o.button || 'Sign in';
      } else if (st === 'home' || st === 'app') {
        el('div', { class: 'apptitle', style: { marginTop: '10px' } }, d).textContent = o.title || 'Hi, Alice';
        el('div', { class: 'appsub' }, d).textContent = o.subtitle || 'Your dashboard';
        for (let i = 0; i < (o.cards ?? 3); i++) el('div', { class: 'feed' }, d, `<i style="width:${[70, 85, 55][i % 3]}%;background:${i === 0 ? rgba(A, 0.6) : ''}"></i><i style="width:${[90, 60, 75][i % 3]}%"></i><i style="width:${[40, 70, 50][i % 3]}%"></i>`);
      } else if (['loading', 'success', 'error', 'locked'].includes(st)) {
        const c = el('div', { class: 'center' }, d);
        const map = {
          loading: { html: spinnerSvg(A, 48), big: o.title || 'Loading…', small: o.subtitle || '' },
          success: { html: `<div style="width:64px;height:64px;border-radius:50%;background:${rgba(C.ok, 0.15)};border:2px solid ${C.ok};display:flex;align-items:center;justify-content:center">${icon('check', C.ok, 34, 3)}</div>`, big: o.title || 'Signed in', small: o.subtitle || '' },
          error: { html: `<div style="width:64px;height:64px;border-radius:50%;background:${rgba(C.alert, 0.15)};border:2px solid ${C.alert};display:flex;align-items:center;justify-content:center">${icon('x', C.alert, 34, 3)}</div>`, big: o.title || '401 Unauthorized', small: o.subtitle || 'Please sign in again' },
          locked: { html: `<div style="width:64px;height:64px;border-radius:50%;background:${rgba(C.alert, 0.12)};border:2px solid ${rgba(C.alert, 0.7)};display:flex;align-items:center;justify-content:center">${icon('lock', C.alert, 30, 2.4)}</div>`, big: o.title || 'Session expired', small: o.subtitle || '' },
        }[st];
        el('div', {}, c, map.html);
        el('div', { class: 'big' }, c).textContent = map.big;
        if (map.small) el('div', { class: 'small' }, c).textContent = map.small;
        if (st === 'loading') d._spinner = c.querySelector('svg');
      } else {
        if (o.icon) el('div', { class: 'logo', style: { background: rgba(A, 0.16), border: `1px solid ${rgba(A, 0.4)}` } }, d, icon(o.icon, A, 24));
        el('div', { class: 'apptitle', style: { marginTop: o.icon ? '0' : '10px' } }, d).textContent = o.title || '';
        if (o.subtitle) el('div', { class: 'appsub' }, d).textContent = o.subtitle;
        for (const l of o.lines || []) el('div', { class: 'line' }, d).textContent = l;
        if (o.button) { const b = el('div', { class: 'button', style: { background: A } }, d); b.textContent = o.button; }
      }
      return d;
    }
    measure() {
      super.measure();
      this.phoneW = this.phone.offsetWidth; this.phoneH = this.phone.offsetHeight;
      return { w: this.w, h: this.h };
    }
    /** The phone body (dock slots, highlight box). */
    get phoneBox() { const top = this.cy - this.h / 2; return box(this.cx, top + this.phoneH / 2, this.phoneW, this.phoneH); }
    /** Links attach to the phone, but leave from below the label when routed vertically. */
    get linkBox() { const top = this.cy - this.h / 2, bot = top + this.h + 6; return box(this.cx, (top + bot) / 2, this.phoneW, bot - top); }
    highlightBox() { return this.phoneBox; }
    // docked tokens sit in a "secure storage" tray that slides up from the bottom of the screen
    static SLOT = 44;
    dockPoint(slot, pill) {
      const b = this.phoneBox;
      return [b.cx, b.b - 9 - 24 - 18 - slot * Device.SLOT];
    }
    dockScale(pill) { return Math.min(0.88, (this.phoneW - 52) / pill.w); }
    claimSlot(id) { let i = this.slots.indexOf(null); if (i < 0) i = this.slots.length; this.slots[i] = id; return i; }
    releaseSlot(id) { const i = this.slots.indexOf(id); if (i >= 0) this.slots[i] = null; }
    slotsChanged(at) {
      let top = -1;
      this.slots.forEach((v, i) => { if (v != null) top = i; });
      this.trayT.to(at, top < 0 ? 0 : 24 + 30 + (top + 1) * Device.SLOT - 8, 0.45, 'smooth');
    }
    a_receive(at, dur, e, args) { this.flash(at, dur, this.scene.resolveColor(args.color) || C.white); }
    a_screen(at, dur, e, args) {
      const custom = args.title || args.subtitle || args.lines || args.button || args.icon || args.color;
      const ev = this.addScreen(at, custom ? Object.assign({}, args, { dur: undefined }) : args.state);
      ev.dur = dur;
    }
    a_tap(at, dur, e, args) { this.taps.push({ at, dur, x: args.x, y: args.y }); }
    render(t) {
      super.render(t);
      const v = this.vis.value(t);
      enterFx(this.root, v, 26);
      const f = this.flashAt(t);
      css(this.phone, 'borderColor', f.amt > 0 ? mixColor('#3F3F46', f.color, f.amt) : '#3F3F46');
      css(this.phone, 'boxShadow', `0 0 0 1px #18181B, 0 24px 60px rgba(0,0,0,0.6)` + (f.amt > 0 ? `, 0 0 ${(44 * f.amt).toFixed(1)}px ${rgba(f.color, 0.5 * f.amt)}` : ''));
      // screens crossfade
      const evs = this.screenEv.list;
      let cur = 0;
      for (let i = 0; i < evs.length; i++) if (evs[i].at <= t) cur = i;
      const shown = {};
      const ce = evs[cur], pe = evs[Math.max(0, cur - 1)];
      const p = cur > 0 ? prog(t, ce.at, ce.dur || 0.45, 'smooth') : 1;
      shown[ce.key] = Math.max(shown[ce.key] || 0, p);
      if (cur > 0 && p < 1 && pe.key !== ce.key) shown[pe.key] = 1 - p;
      for (const k in this.screens) {
        const d = this.screens[k];
        const o = shown[k] || 0;
        css(d, 'opacity', o.toFixed(3));
        css(d, 'transform', k === ce.key && o < 1 ? `translateY(${((1 - o) * 14).toFixed(1)}px)` : 'none');
        if (d._spinner && o > 0) css(d._spinner, 'transform', `rotate(${((t * 360) % 360).toFixed(1)}deg)`);
      }
      // tap ripple
      let rp = 0, tp = null;
      for (const tap of this.taps) if (t >= tap.at && t <= tap.at + tap.dur) { rp = (t - tap.at) / tap.dur; tp = tap; }
      if (tp) {
        let x = tp.x, y = tp.y;
        if (x == null && this.button) { x = (this.button.offsetLeft + this.button.offsetWidth / 2) / this.screenEl.offsetWidth; y = (this.button.offsetTop + this.button.offsetHeight / 2) / this.screenEl.offsetHeight; }
        x = x ?? 0.5; y = y ?? 0.75;
        const s = 0.2 + 0.8 * ease.out(rp);
        css(this.ripple, 'left', (x * this.screenEl.offsetWidth - 40).toFixed(1) + 'px');
        css(this.ripple, 'top', (y * this.screenEl.offsetHeight - 40).toFixed(1) + 'px');
        css(this.ripple, 'transform', `scale(${s.toFixed(3)})`);
        css(this.ripple, 'opacity', (0.9 * (1 - rp)).toFixed(3));
        css(this.ripple, 'background', rgba('#FFFFFF', 0.18 * (1 - rp)));
      } else css(this.ripple, 'opacity', '0');
      const th = this.trayT.value(t);
      css(this.tray, 'height', th.toFixed(1) + 'px');
      css(this.tray, 'opacity', clamp(th / 30).toFixed(3));
    }
  }

  // ------------------------------------------------------------------ Link
  class Link extends Primitive {
    static layer = 'links';
    static defaults = { from: null, to: null, route: 'elbow', fromSide: null, toSide: null, offset: 0, label: null, dashed: false, color: null, arrow: null, mid: null };
    static actions = { enter: { dur: 0.6, ease: 'smooth' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, highlight: { dur: 0.35 }, alert: { dur: 0.35 }, unhighlight: { dur: 0.35 }, pulse: { dur: 0.6 } };
    static enterAfter(e) { return [e.props.from, e.props.to]; }
    constructor(...a) { super(...a); this.colT = new Track(null); this.wT = new Track(0); }
    relatedIds() { return [this.props.from, this.props.to]; }
    build() {
      this.root.style.display = 'none';
      const L = this.scene.layers.links;
      this.g = svgEl('g', {}, L);
      this.glow = svgEl('path', { fill: 'none', 'stroke-width': 8, 'stroke-linecap': 'round', opacity: 0 }, this.g);
      this.path = svgEl('path', { fill: 'none', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.g);
      if (this.props.arrow) this.arrows = [svgEl('path', { fill: 'none', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.g), svgEl('path', { fill: 'none', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.g)];
      if (this.props.label) { this.lab = el('div', { class: 'ca-abs af-linklabel' }, this.scene.layers.nodes); this.lab.textContent = this.props.label; }
    }
    measure() { this.w = 0; this.h = 0; return { w: 0, h: 0 }; }
    afterLayout() {
      const S = this.scene, p = this.props;
      const A = S.get(p.from), B = S.get(p.to);
      const r = route(A.linkBox, B.linkBox, { route: p.route, fromSide: p.fromSide, toSide: p.toSide, offset: p.offset, mid: p.mid });
      this.geom = r;
      attr(this.path, 'd', r.d); attr(this.glow, 'd', r.d);
      this.lut = PathLUT.fromPath(r.d, 2);
      this.len = this.lut.length;
      this.base = S.resolveColor(p.color) || S.token('link', C.link);
      this.colT.initial = this.base;
      if (p.dashed) attr(this.path, 'stroke-dasharray', '7 7');
      if (this.lab) {
        let m = this.lut.atFrac(p.labelAt ?? 0.5);
        if (p.labelAt == null) for (const f of [0.5, 0.35, 0.65, 0.25, 0.75, 0.15, 0.85]) { const q = this.lut.atFrac(f); if (Math.abs(Math.cos(q.angle)) > 0.9) { m = q; break; } }
        const lw = this.lab.offsetWidth, lh = this.lab.offsetHeight;
        const horiz = Math.abs(Math.cos(m.angle)) > 0.5;
        const lx = horiz ? m.x - lw / 2 : m.x + 10, ly = horiz ? m.y - lh - 8 : m.y - lh / 2;
        this.lab.style.left = Math.round(lx) + 'px'; this.lab.style.top = Math.round(ly) + 'px';
      }
    }
    lutFrom(nodeId) { return nodeId === this.props.from ? this.lut : this.lut.reversed(); }
    a_highlight(at, dur, e, args) { const c = args.color === 'red' ? C.alert : (this.scene.resolveColor(args.color) || C.white); this.colT.to(at, c, dur, e); this.wT.to(at, 1, dur, e); }
    a_alert(at, dur, e, args) { this.a_highlight(at, dur, e, Object.assign({}, args, { color: 'red' })); }
    a_unhighlight(at, dur, e) { this.colT.to(at, this.base, dur, e); this.wT.to(at, 0, dur, e); }
    render(t) {
      const v = this.vis.value(t), d = this.dimT.value(t);
      const lastEnter = this.vis.lastKeyAt(t);
      const exiting = this.vis.keys.some((k) => k.value === 0 && k.at <= t);
      let col = this.colT.value(t) || this.base;
      const w = this.wT.value(t);
      const f = this.flashAt(t);
      if (f.amt > 0) col = mixColor(col, f.color, f.amt);
      attr(this.g, 'opacity', (exiting && v < 1 ? v : (v > 0 ? 1 : 0)) * d);
      if (this.props.dashed) attr(this.path, 'd', v >= 1 || exiting ? this.geom.d : this.lut.partialD(0, this.len * v));
      else drawOn(this.path, exiting ? 1 : v, this.len);
      attr(this.path, 'stroke', col);
      attr(this.path, 'stroke-width', (2 + w * 0.8).toFixed(2));
      attr(this.glow, 'stroke', col);
      attr(this.glow, 'opacity', (Math.max(w, f.amt) * 0.25).toFixed(3));
      if (!this.props.dashed) drawOn(this.glow, exiting ? 1 : v, this.len);
      if (this.lab) { css(this.lab, 'opacity', (clamp((v - 0.5) * 2) * d).toFixed(3)); }
      if (this.arrows) {
        const ends = [];
        if (this.props.arrow === 'end' || this.props.arrow === 'both' || this.props.arrow === true) ends.push([this.len, 1]);
        if (this.props.arrow === 'start' || this.props.arrow === 'both') ends.push([0, -1]);
        this.arrows.forEach((a, i) => {
          if (!ends[i]) { attr(a, 'opacity', 0); return; }
          const [s, dir] = ends[i];
          const pt = this.lut.at(s), ang = this.lut.at(dir > 0 ? s - 2 : s + 2).angle + (dir < 0 ? Math.PI : 0);
          const k = 9, x = pt.x, y = pt.y;
          const a1 = ang + Math.PI * 0.8, a2 = ang - Math.PI * 0.8;
          attr(a, 'd', `M${x + Math.cos(a1) * k},${y + Math.sin(a1) * k}L${x},${y}L${x + Math.cos(a2) * k},${y + Math.sin(a2) * k}`);
          attr(a, 'stroke', col);
          attr(a, 'opacity', (prog(v, 0.9, 0.1, 'linear')).toFixed(3));
        });
      }
    }
  }

  // ------------------------------------------------------------------ PacketStream
  class PacketStream extends Primitive {
    static layer = 'links';
    static autoEnter = false;
    static defaults = { link: null, color: null, concept: null, speed: 380, spacing: 34, size: 4, reverse: false };
    static actions = { start: { dur: 0 }, stop: { dur: 0 }, slow: { dur: 0.8 }, speed: { dur: 0.8 }, resume: { dur: 0.8 }, enter: { dur: 0 }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 } };
    relatedIds() { const l = this.scene.get(this.props.link); return [l.props.from, l.props.to]; }
    build() {
      this.root.style.display = 'none';
      this.g = svgEl('g', {}, this.scene.layers.fx);
      this.halo = svgEl('g', { style: { filter: 'blur(3px)' } }, this.g);
      this.core = svgEl('g', {}, this.g);
      this.dots = [];
      this.runs = [];
      this.profile = new SpeedProfile(this.props.speed);
      this.color = this.scene.resolveColor(this.props.color) || (this.props.concept && this.scene.conceptColor(this.props.concept)) || this.scene.token('packet', '#E0F2FE');
    }
    measure() { return { w: 0, h: 0 }; }
    afterLayout() {
      const l = this.scene.get(this.props.link);
      this.linkEl = l;
      this.lut = this.props.reverse ? l.lut.reversed() : l.lut;
    }
    touches(id) { const l = this.scene.get(this.props.link); return l.props.from === id || l.props.to === id; }
    addSpeed(at, factor, ramp) { this.profile.change(at, this.props.speed * factor, ramp); }
    a_start(at) { this.runs.push({ start: at, stop: Infinity }); this.vis.to(at, 1, 0); }
    a_enter(at) { this.a_start(at); }
    a_stop(at) { const r = this.runs[this.runs.length - 1]; if (r && r.stop === Infinity) r.stop = at; }
    a_slow(at, dur, e, args) { this.addSpeed(at, args.factor ?? 0.3, dur); }
    a_speed(at, dur, e, args) { this.addSpeed(at, args.factor ?? 1, dur); }
    a_resume(at, dur) { this.addSpeed(at, 1, dur); }
    render(t) {
      const d = this.dimT.value(t) * this.vis.value(t);
      attr(this.g, 'opacity', d.toFixed(3));
      const L = this.lut.length;
      const ps = [];
      for (const r of this.runs) {
        if (t < r.start) continue;
        const D = this.profile.distance(r.start, t);
        const Dstop = r.stop === Infinity ? Infinity : this.profile.distance(r.start, r.stop);
        for (const q of window.CA.streamPositions(D, Dstop, this.props.spacing, L)) ps.push(q);
      }
      while (this.dots.length < ps.length) {
        const h = svgEl('circle', { r: this.props.size * 1.6, fill: this.color, opacity: 0.55 }, this.halo);
        const c = svgEl('circle', { r: this.props.size / 2 + 0.4, fill: mixColor(this.color, '#FFFFFF', 0.6) }, this.core);
        this.dots.push([h, c]);
      }
      this.dots.forEach(([h, c], i) => {
        const q = ps[i];
        if (!q) { attr(h, 'visibility', 'hidden'); attr(c, 'visibility', 'hidden'); return; }
        const pt = this.lut.at(q.s);
        const edge = clamp(q.s / 18) * clamp((L - q.s) / 18);
        const jit = (noise(this.id, q.k) - 0.5) * 2.2;
        const nx = -Math.sin(pt.angle) * jit, ny = Math.cos(pt.angle) * jit;
        for (const e of [h, c]) { attr(e, 'visibility', 'visible'); attr(e, 'cx', (pt.x + nx).toFixed(1)); attr(e, 'cy', (pt.y + ny).toFixed(1)); }
        attr(c, 'opacity', edge.toFixed(3)); attr(h, 'opacity', (0.55 * edge).toFixed(3));
      });
    }
  }

  // ------------------------------------------------------------------ TokenPill
  class TokenPill extends Primitive {
    static layer = 'pills';
    static autoEnter = false;
    static focusExempt = true;
    static defaults = { label: 'token', concept: null, color: null, icon: null, from: null, ghost: false };
    static actions = { show: { dur: 0.45, ease: 'outBack' }, enter: { dur: 0.45, ease: 'outBack' }, send: { dur: null, ease: 'smooth' }, hide: { dur: 0.3 }, exit: { dur: 0.3 }, expire: { dur: 0.5 }, pulse: { dur: 0.6 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, highlight: { dur: 0.35 }, alert: { dur: 0.35 }, unhighlight: { dur: 0.3 } };
    constructor(...a) {
      super(...a);
      this.segs = [];
      this.scaleT = new Track(0);
      this.dockT = new Track(1);
      this.expT = new Track(0);
      this.shakes = [];
      this.cur = { node: this.props.from, hidden: true, slot: null };
    }
    build() {
      const p = this.props, S = this.scene;
      this.color = S.resolveColor(p.color) || S.colorFor(p.concept || p.label) || (p.concept ? S.conceptColor(p.concept) : C.neutralPill);
      const ic = p.icon === false ? null : (p.icon || (S.colorFor(p.concept || p.label) || p.concept ? 'key-round' : null));
      this.root.classList.add('af-pill');
      if (!ic) this.root.classList.add('noicon');
      this.root.innerHTML = (ic ? icon(ic, '#0A0A0B', 18, 2.4) : '') + `<span></span>`;
      this.root.querySelector('span').textContent = p.label;
      this.root.style.background = this.color;
      this.root.style.transformOrigin = '50% 50%';
      if (p.ghost) this.root.style.outline = `2px dashed ${C.alert}`, (this.root.style.outlineOffset = '4px');
    }
    afterLayout() {
      if (this.props.from) { const n = this.scene.get(this.props.from); this.start = [n.cx, n.cy]; } else if (this.props.x != null) this.start = [this.props.x * this.scene.W, this.props.y * this.scene.H]; else this.start = [this.scene.W / 2, this.scene.H / 2];
    }
    posAt(t) {
      let p = this.start;
      for (const s of this.segs) {
        if (s.t0 > t) break;
        if (t >= s.t1) { p = s.end; continue; }
        const q = s.lut.at(s.ease(clamp((t - s.t0) / (s.t1 - s.t0))) * s.lut.length);
        p = [q.x, q.y];
      }
      return p;
    }
    moving(t) { return this.segs.some((s) => t >= s.t0 && t < s.t1); }
    addSeg(t0, dur, pts, e) {
      this.scaleT.cancelAfter(t0);
      const lut = PathLUT.fromPoints(pts);
      this.segs.push({ t0, t1: t0 + Math.max(0.01, dur), lut, ease: getEase(e || 'smooth'), end: pts[pts.length - 1] });
      this.segs.sort((a, b) => a.t0 - b.t0);
    }
    releaseDock(at) {
      const n = this.cur.node && this.scene.has(this.cur.node) ? this.scene.get(this.cur.node) : null;
      if (n && n.releaseSlot && this.cur.slot != null) { n.releaseSlot(this.id); if (n.slotsChanged) n.slotsChanged(at); }
      if (this.cur.slot != null) this.dockT.to(at, 1, 0.3, 'smooth');
      this.cur.slot = null;
    }
    /** Appear (pop) at a node's dock or at a point. */
    a_show(at, dur, e, args) {
      const nodeId = args.at || this.props.from;
      let pt;
      if (args.x != null) pt = [args.x * this.scene.W, args.y * this.scene.H];
      else if (nodeId) {
        const n = this.scene.get(nodeId);
        this.cur.node = nodeId;
        if (n.dockPoint && args.dock !== false) {
          const slot = n.claimSlot(this.id);
          this.cur.slot = slot;
          if (n.slotsChanged) n.slotsChanged(at - 0.1);
          pt = n.dockPoint(slot, this);
          this.dockT.to(at, n.dockScale(this), 0);
        } else { const b = n.box; pt = [b.cx, b.y - this.h / 2 - 16]; }
      } else pt = this.start;
      this.addSeg(at, 0.001, [pt, pt]);
      this.scaleT.to(at, 1, dur, e);
      this.cur.hidden = false;
    }
    a_enter(at, dur, e, args) { this.a_show(at, dur, e, args); }
    a_hide(at, dur, e) { this.scaleT.to(at, 0, dur, 'in'); this.cur.hidden = true; this.releaseDock(at); }
    a_exit(at, dur, e) { this.a_hide(at, dur, e); }
    hideAt(at, dur, node) { this.scaleT.to(at, 0, dur, 'in'); this.cur.hidden = true; this.cur.node = node ? node.id : this.cur.node; this.releaseDock(at); }
    a_expire(at, dur, e) { this.expT.to(at, 1, dur, e); }
    shake(at, dur) { this.shakes.push({ at, dur }); }
    /** Path from the pill's current position to a node, preferring an existing Link. */
    pathTo(at, toId, endMode) {
      const S = this.scene;
      const from = this.cur.node;
      const dest = S.get(toId);
      let lut = null;
      const link = S.list.find((l) => l instanceof Link && ((l.props.from === from && l.props.to === toId) || (l.props.to === from && l.props.from === toId)));
      if (link) lut = link.lutFrom(from);
      else if (from && S.has(from)) lut = PathLUT.fromPath(route(S.get(from).linkBox, dest.linkBox, { route: 'curve' }).d, 3);
      const cur = this.posAt(at);
      let pts = lut ? lut.points() : [cur, [dest.cx, dest.cy]];
      if (!this.cur.hidden) {
        // move from the current spot to the start of the link
        pts = [cur].concat(pts);
      }
      return { pts, lut, dest };
    }
    a_send(at, dur, e, args) {
      const S = this.scene;
      if (!args.to) throw new Error(`TokenPill "${this.id}" send needs args.to`);
      const dest = S.get(args.to);
      const then = args.then || (dest.dockPoint ? 'dock' : 'absorb');
      const wasHidden = this.cur.hidden;
      const { pts } = args.via ? this.viaPts(at, args.via) : this.pathTo(at, args.to);
      this.releaseDock(at);
      let end = pts[pts.length - 1];
      if (then === 'dock' && dest.dockPoint) {
        const slot = dest.claimSlot(this.id);
        this.cur.slot = slot;
        end = dest.dockPoint(slot, this);
        pts.push(end);
      }
      let path = pts;
      if (then === 'stay') {
        // stop on the link just outside the destination edge
        const lut = PathLUT.fromPoints(pts);
        const s = lut.length - this.w / 2 - 14;
        const q = lut.at(s);
        path = pts.filter((_, i) => lut.cum[i] < s).concat([[q.x, q.y]]);
      }
      const len = PathLUT.fromPoints(path).length;
      if (args.dur == null) dur = clamp(len / 650, 0.7, 1.8);
      if (wasHidden) { this.scaleT.to(at, 1, 0.3, 'outBack'); }
      this.addSeg(at, dur, path, e);
      if (then === 'dock') { this.dockT.to(at + dur * 0.7, dest.dockScale(this), dur * 0.3, 'smooth'); if (dest.slotsChanged) dest.slotsChanged(at + dur * 0.55); }
      this.cur = { node: args.to, hidden: false, slot: this.cur.slot };
      if (then === 'absorb') {
        this.scaleT.to(at + dur - 0.05, 0, 0.28, 'in');
        this.cur.hidden = true;
        dest.flash(at + dur - 0.05, 0.7, this.color);
      } else if (dest.flash) dest.flash(at + dur - 0.1, 0.6, this.color);
    }
    viaPts(at, via) {
      const link = this.scene.get(via);
      const fromStart = this.cur.node === link.props.from || this.cur.node == null;
      const lut = fromStart ? link.lut : link.lut.reversed();
      const pts = lut.points();
      return { pts: this.cur.hidden ? pts : [this.posAt(at)].concat(pts) };
    }
    /** Move to an arbitrary point (used by validate). */
    travelTo(at, dur, pt, o = {}) {
      const S = this.scene;
      let pts;
      const from = this.cur.node;
      const link = o.toNode && S.list.find((l) => l instanceof Link && ((l.props.from === from && l.props.to === o.toNode.id) || (l.props.to === from && l.props.from === o.toNode.id)));
      const cur = this.posAt(at);
      if (link) pts = link.lutFrom(from).points().concat([pt]);
      else {
        const a = cur, b = pt;
        const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
        const d = `M${a}C${mx},${a[1]} ${mx},${b[1]} ${b}`;
        pts = PathLUT.fromPath(d, 3).points();
      }
      if (!this.cur.hidden) pts = [cur].concat(pts);
      if (this.cur.hidden) this.scaleT.to(at, 1, 0.3, 'outBack');
      this.releaseDock(at);
      this.addSeg(at, dur, pts, o.ease);
      this.cur = { node: o.toNode ? o.toNode.id : null, hidden: false, slot: null };
    }
    render(t) {
      const [x, y] = this.posAt(t);
      let s = this.scaleT.value(t) * this.dockT.value(t);
      const d = this.dimT.value(t);
      let sx = 0;
      for (const sh of this.shakes) if (t >= sh.at && t <= sh.at + sh.dur) sx = Math.sin((t - sh.at) * 60) * 7 * (1 - (t - sh.at) / sh.dur);
      css(this.root, 'transform', `translate(${(x - this.w / 2 + sx).toFixed(2)}px, ${(y - this.h / 2).toFixed(2)}px) scale(${Math.max(0, s).toFixed(4)})`);
      css(this.root, 'opacity', (clamp(this.scaleT.value(t) * 3) * d).toFixed(3));
      css(this.root, 'visibility', s <= 0.001 ? 'hidden' : 'visible');
      const ex = this.expT.value(t);
      const col = ex > 0 ? mixColor(this.color, C.expired, ex) : this.color;
      css(this.root, 'background', col);
      css(this.root, 'textDecoration', ex > 0.5 ? 'line-through' : 'none');
      css(this.root, 'color', ex > 0 ? mixColor('#0A0A0B', '#D4D4D8', ex) : '#0A0A0B');
      const f = this.flashAt(t);
      const glow = `0 0 ${(16 + 26 * f.amt).toFixed(1)}px ${rgba(f.amt > 0 ? mixColor(col, f.color, f.amt) : col, (0.55 + 0.4 * f.amt) * (1 - ex))}`;
      const ring = f.amt > 0 ? `, 0 0 0 ${(3 * f.amt).toFixed(1)}px ${rgba(f.color, f.amt)}` : '';
      css(this.root, 'boxShadow', glow + ring);
      css(this.root, 'left', '0px'); css(this.root, 'top', '0px');
      this._t = t;
      this.renderHighlight(t, this.scaleT.value(t));
    }
    get box() { const p = this.posAt(this._t || 0); return box(p[0], p[1], this.w, this.h); }
  }

  // ------------------------------------------------------------------ Hacker
  const HACKER_SVG = `
<svg viewBox="0 0 200 196" width="170" height="167">
  <g fill="none" stroke="currentColor" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round">
    <path d="M30 192 C30 150 48 128 70 119 C58 103 55 78 64 57 C76 28 124 28 136 57 C145 78 142 103 130 119 C152 128 170 150 170 192" fill="#0A0003"/>
    <path d="M100 32 C92 48 90 60 92 74" opacity="0.55"/>
    <path d="M77 70 C83 52 117 52 123 70 C127 88 118 108 100 112 C82 108 73 88 77 70 Z" fill="#000"/>
    <path d="M86 82 L95 85" stroke-width="3.6"/><path d="M114 82 L105 85" stroke-width="3.6"/>
    <path d="M70 119 C80 126 90 128 100 128 C110 128 120 126 130 119" opacity="0.7"/>
    <rect x="46" y="134" width="108" height="56" rx="7" fill="#0A0003"/>
    <path d="M30 192 L170 192" stroke-width="3.6"/>
    <path d="M90 154 L100 164 L110 154 M100 148 L100 164" opacity="0" />
    <circle cx="100" cy="161" r="9" opacity="0.9"/>
    <path d="M96 159 h0.1 M104 159 h0.1" stroke-width="3.4"/>
    <path d="M96 166 h8" stroke-width="2"/>
  </g>
</svg>`;
  class Hacker extends Primitive {
    static isNode = true;
    static defaults = { label: 'Attacker', place: 'attacker', color: null };
    static actions = { enter: { dur: 0.9 }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, highlight: { dur: 0.35 }, alert: { dur: 0.35 }, unhighlight: { dur: 0.3 }, pulse: { dur: 0.6 }, intercept: { dur: 1.2 }, replay: { dur: 1.3 } };
    build() {
      this.color = this.scene.resolveColor(this.props.color) || this.scene.token('alert', C.alert);
      this.root.classList.add('af-hacker');
      this.root.style.color = this.color;
      this.art = el('div', {}, this.root, HACKER_SVG);
      if (this.props.label) { const l = el('div', { class: 'lbl' }, this.root); l.textContent = this.props.label; l.style.color = this.color; }
      this.lines = [];
      this.slots = [];
      this.captured = [];
    }
    get linkBox() { const b = this.box; return box(b.cx, b.y + 167 / 2, 170, 167); }
    claimSlot(id) { let i = this.slots.indexOf(null); if (i < 0) i = this.slots.length; this.slots[i] = id; return i; }
    releaseSlot(id) { const i = this.slots.indexOf(id); if (i >= 0) this.slots[i] = null; }
    dockScale() { return 1; }
    /** Captured copies sit beside the hacker, on the side facing away from the nearest node. */
    dockPoint(slot, pill) {
      const b = this.linkBox;
      if (this._dockRight == null) {
        let dl = Infinity, dr = Infinity;
        for (const e of this.scene.list) {
          if (e === this || !e.constructor.isNode) continue;
          const o = e.box;
          if (o.b < b.y - 40 || o.y > b.b + 40) continue;
          if (o.cx < b.cx) dl = Math.min(dl, b.x - o.r); else dr = Math.min(dr, o.x - b.r);
        }
        this._dockRight = dr > dl;
      }
      const right = this._dockRight;
      return [right ? b.r + 26 + pill.w / 2 : b.x - 26 - pill.w / 2, b.cy - 10 - slot * (pill.h + 10)];
    }
    edgeToward(pt) {
      const b = this.linkBox;
      const dx = pt[0] - b.cx, dy = pt[1] - b.cy;
      if (Math.abs(dy) * b.w > Math.abs(dx) * b.h) return [b.cx, dy < 0 ? b.y + 6 : b.b];
      return [dx < 0 ? b.x + 20 : b.r - 20, b.cy];
    }
    addLine(a, b, t0, drawDur, hold) {
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
      const d = `M${a}Q${mx + (b[1] - a[1]) * 0.12},${my - (b[0] - a[0]) * 0.12} ${b}`;
      const lut = PathLUT.fromPath(d, 3);
      const p = svgEl('path', { fill: 'none', stroke: this.color, 'stroke-width': 2.4, 'stroke-dasharray': '9 7', 'stroke-linecap': 'round' }, this.scene.layers.fx);
      const line = { lut, el: p, t0, drawDur, tEnd: hold == null ? Infinity : t0 + drawDur + hold };
      this.lines.push(line);
      return line;
    }
    a_intercept(at, dur, e, args) {
      const S = this.scene;
      const src = S.get(args.pill);
      let ip;
      if (args.link && !src.moving(at)) ip = (() => { const q = S.get(args.link).lut.atFrac(args.point ?? 0.5); return [q.x, q.y]; })();
      else ip = src.posAt(at);
      const a = this.edgeToward(ip);
      const draw = Math.min(0.4, dur * 0.35);
      const line = this.addLine(a, ip, at, draw, args.hold ?? 2.4);
      const id = args.as || src.id + '-copy';
      const clone = S.spawn({ id, primitive: 'TokenPill', props: { label: src.props.label, concept: src.props.concept, color: src.color, icon: src.props.icon, ghost: true } });
      clone.start = ip;
      clone.addSeg(at + draw, 0.001, [ip, ip]);
      clone.scaleT.to(at + draw, 1, 0.35, 'outBack');
      clone.cur = { node: null, hidden: false, slot: null };
      const slot = this.claimSlot(id);
      const end = this.dockPoint(slot, clone);
      const back = line.lut.reversed().points();
      clone.addSeg(at + draw + 0.3, dur - draw - 0.3, [ip].concat(back).concat([end]), 'smooth');
      clone.cur = { node: this.id, hidden: false, slot };
      src.flash(at + draw, 0.7, this.color);
      if (args.link) S.get(args.link).flash(at, draw + 0.5, this.color);
      this.flash(at + dur - 0.2, 0.6, this.color);
      this.captured.push(id);
    }
    a_replay(at, dur, e, args) {
      const S = this.scene;
      const id = args.pill || this.captured[this.captured.length - 1];
      const clone = S.get(id);
      const dest = S.get(args.to);
      const db = dest.linkBox;
      const from = clone.posAt(at);
      const tgt = route(box(from[0], from[1], clone.w, clone.h), db, { route: 'straight' }).p1;
      const draw = Math.min(0.4, dur * 0.3);
      const line = this.addLine(this.edgeToward(tgt), tgt, at, draw, args.hold ?? 2.0);
      this.releaseSlot(id);
      clone.addSeg(at + draw * 0.5, dur - draw * 0.5, [from].concat(line.lut.points()), 'smooth');
      clone.cur = { node: args.to, hidden: false, slot: null };
      const then = args.then || 'absorb';
      if (then === 'absorb') { clone.scaleT.to(at + dur - 0.05, 0, 0.28, 'in'); clone.cur.hidden = true; }
      dest.flash(at + dur - 0.05, 0.8, this.color);
    }
    render(t) {
      super.render(t);
      const v = this.vis.value(t), d = this.dimT.value(t);
      // glitchy neon entrance: deterministic flicker from seeded noise per frame bucket
      let flick = 1;
      if (v > 0 && v < 1) flick = noise(this.id, Math.floor(t * 30)) > 0.35 ? 1 : 0.25;
      css(this.root, 'opacity', (v * d * flick).toFixed(3));
      const pulse = 0.75 + 0.25 * Math.sin(t * 3.2);
      const f = this.flashAt(t);
      css(this.art, 'filter', `drop-shadow(0 0 ${(6 + 4 * pulse + 14 * f.amt).toFixed(1)}px ${rgba(this.color, 0.85)}) drop-shadow(0 0 ${(22 + 20 * f.amt).toFixed(1)}px ${rgba(this.color, 0.4)})`);
      css(this.art, 'transform', v < 1 ? `translateX(${((noise(this.id + 'x', Math.floor(t * 30)) - 0.5) * 10 * (1 - v)).toFixed(1)}px)` : 'none');
      for (const L of this.lines) {
        const p = clamp((t - L.t0) / L.drawDur);
        const fade = 1 - prog(t, L.tEnd, 0.4, 'smooth');
        attr(L.el, 'd', p > 0 ? L.lut.partialD(0, L.lut.length * ease.smooth(p)) : '');
        attr(L.el, 'opacity', (fade * d).toFixed(3));
        marchingAnts(L.el, t, -40);
        css(L.el, 'filter', `drop-shadow(0 0 4px ${rgba(this.color, 0.8)})`);
      }
    }
  }

  // ------------------------------------------------------------------ Callout / Label
  class Callout extends Primitive {
    static layer = 'text';
    static dimmable = true;
    static defaults = { text: '', target: null, row: null, side: 'top', gap: 34, color: null, variant: 'callout', x: null, y: null, connector: true };
    static actions = { enter: { dur: 0.5, ease: 'out' }, exit: { dur: 0.35 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, set: { dur: 0.5 }, pulse: { dur: 0.6 } };
    static autoEnter = true;
    static enterAfter(e) { return e.props.target ? [e.props.target] : []; }
    relatedIds() { return this.props.target ? [this.props.target] : []; }
    build() {
      const p = this.props;
      this.color = this.scene.resolveColor(p.color) || this.scene.colorFor(p.text) || this.scene.look.accent;
      if (p.variant === 'label' || p.variant === 'marker') {
        this.root.classList.add('af-label');
        if (p.variant === 'marker') this.root.classList.add('marker');
        this.txt = el('span', {}, this.root);
        if (p.color) this.root.style.color = this.color;
      } else {
        this.root.classList.add('af-callout');
        const dot = el('div', { class: 'dot' }, this.root);
        dot.style.background = this.color; dot.style.boxShadow = `0 0 10px ${rgba(this.color, 0.8)}`;
        this.txt = el('span', {}, this.root);
      }
      this.txt.textContent = p.text;
      this.texts = new Events();
      this.texts.add(-1, { value: p.text });
      if (p.connector && p.variant !== 'label' && p.variant !== 'marker' && p.target) {
        this.conn = svgEl('path', { fill: 'none', stroke: rgba('#FFFFFF', 0.35), 'stroke-width': 1.5, 'stroke-dasharray': '3 4' }, this.scene.layers.fx);
        this.connDot = svgEl('circle', { r: 3.5, fill: this.color }, this.scene.layers.fx);
      }
    }
    afterLayout() {
      const p = this.props, S = this.scene;
      if (p.x != null && p.y != null && !p.target) { this.place(p.x * S.W, p.y * S.H); return; }
      const T = S.get(p.target);
      const tb = p.row != null && T.rows ? T.rows.box(T.rows.index(p.row)) : (T.highlightBox ? T.highlightBox() : T.linkBox);
      const g = p.gap;
      let cx, cy, a;
      if (p.side === 'top') { cx = tb.cx; cy = tb.y - g - this.h / 2; a = [[cx, cy + this.h / 2], [tb.cx, tb.y]]; }
      else if (p.side === 'bottom') { cx = tb.cx; cy = tb.b + g + this.h / 2; a = [[cx, cy - this.h / 2], [tb.cx, tb.b]]; }
      else if (p.side === 'left') { cx = tb.x - g - this.w / 2; cy = tb.cy; a = [[cx + this.w / 2, cy], [tb.x, tb.cy]]; }
      else { cx = tb.r + g + this.w / 2; cy = tb.cy; a = [[cx - this.w / 2, cy], [tb.r, tb.cy]]; }
      cx += p.dx || 0; cy += p.dy || 0;
      this.place(cx, cy);
      if (this.conn) { attr(this.conn, 'd', `M${a[0]}L${a[1]}`); attr(this.connDot, 'cx', a[1][0]); attr(this.connDot, 'cy', a[1][1]); }
      this.side = p.side;
    }
    a_set(at, dur, e, args) { this.texts.add(at, { value: args.text, dur }); }
    render(t) {
      super.render(t);
      const v = this.vis.value(t), d = this.dimT.value(t);
      const off = (1 - v) * 12;
      const dir = { top: [0, off], bottom: [0, -off], left: [off, 0], right: [-off, 0] }[this.side || 'top'] || [0, off];
      css(this.root, 'transform', v >= 1 ? 'none' : `translate(${dir[0].toFixed(1)}px, ${dir[1].toFixed(1)}px)`);
      css(this.root, 'filter', v >= 1 ? 'none' : `blur(${((1 - v) * 6).toFixed(1)}px)`);
      const ev = this.texts.last(t);
      if (ev.dur) {
        const p = clamp((t - ev.at) / ev.dur);
        const prev = this.texts.list[this.texts.list.indexOf(ev) - 1];
        text(this.txt, p < 0.5 ? prev.value : ev.value);
        const q = p < 0.5 ? p * 2 : (1 - p) * 2;
        css(this.txt, 'filter', q > 0 ? `blur(${(q * 6).toFixed(1)}px)` : 'none');
        css(this.txt, 'opacity', (1 - q * 0.7).toFixed(3));
      } else text(this.txt, ev.value);
      if (this.conn) { attr(this.conn, 'opacity', (v * d).toFixed(3)); attr(this.connDot, 'opacity', (v * d).toFixed(3)); }
    }
  }

  // ------------------------------------------------------------------ Metric (big number with counter)
  class Metric extends Primitive {
    static isNode = true;
    static defaults = { label: '', value: '0', color: null, place: 'center' };
    static actions = { enter: { dur: 0.6, ease: 'out' }, exit: { dur: 0.4 }, dim: { dur: 0.5 }, undim: { dur: 0.5 }, set: { dur: 1.0 }, pulse: { dur: 0.6 }, highlight: { dur: 0.35 }, alert: { dur: 0.35 }, unhighlight: { dur: 0.3 } };
    build() {
      this.root.classList.add('af-metric');
      this.val = el('div', { class: 'val' }, this.root);
      this.val.textContent = String(this.props.value);
      if (this.props.label) el('div', { class: 'lab' }, this.root).textContent = this.props.label;
      this.cv = new CellValue(this.val);
      this.colT = new Track(this.scene.resolveColor(this.props.color) || '#FFFFFF');
      // reserve width for the widest value to keep the layout stable
      const vals = [this.props.value].concat((this.scene.spec.beats || []).filter((b) => b.target === this.id && b.action === 'set').map((b) => b.args.value));
      let mw = 0;
      for (const v of vals) { this.val.textContent = String(v); mw = Math.max(mw, this.val.offsetWidth); }
      this.val.textContent = String(this.props.value);
      this.root.style.minWidth = mw + 8 + 'px';
    }
    a_set(at, dur, e, args) { this.cv.set(at, args.value, dur, null); if (args.color) this.colT.to(at, this.scene.resolveColor(args.color === 'red' ? 'alert' : args.color), dur, e); }
    render(t) {
      super.render(t);
      enterFx(this.root, this.vis.value(t));
      this.cv.render(t);
      const c = this.colT.value(t);
      css(this.val, 'color', c);
      const f = this.flashAt(t);
      css(this.val, 'textShadow', `0 0 ${(24 + 20 * f.amt).toFixed(0)}px ${rgba(c, 0.35 + 0.4 * f.amt)}`);
    }
  }

  register('SectionTitle', SectionTitle);
  register('HookQuestion', HookQuestion);
  register('ServiceCard', ServiceCard);
  register('Database', Database);
  register('Device', Device);
  register('Link', Link);
  register('PacketStream', PacketStream);
  register('TokenPill', TokenPill);
  register('Hacker', Hacker);
  register('Callout', Callout);
  register('Label', class Label extends Callout { static defaults = Object.assign({}, Callout.defaults, { variant: 'label', side: 'bottom', gap: 16 }); });
  register('Metric', Metric);

  // ------------------------------------------------------------------ layout by role
  const ROLES = {
    client: ['L', 0], 'client-top': ['L', -1], 'client-bottom': ['L', 1], left: ['L', 0],
    center: ['C', 0], gateway: ['C', 0], middle: ['C', 0], 'center-top': ['C', -1], 'center-bottom': ['C', 1],
    server: ['R', 0], service: ['R', 0], right: ['R', 0], 'server-top': ['R', -1], 'server-bottom': ['R', 1],
    store: ['R', 's'], 'store-right': ['R', 's'], 'store-left': ['L', 's'], 'store-center': ['C', 's'], attacker: ['C', 's'],
  };
  registerLayout('architecture-flow', (S) => {
    const W = S.W, H = S.H, P = S.portrait;
    const top = S.has('title') ? (P ? 240 : 158) : 60;
    const bot = H - (S.has('hook') ? (P ? 300 : 132) : 60);
    const GAP = P ? 60 : 46;
    const bands = { L: { main: [], store: [] }, C: { main: [], store: [] }, R: { main: [], store: [] } };
    for (const e of S.list) {
      if (!e.constructor.isNode) continue;
      const p = e.props;
      if (p.x != null && p.y != null) { e.place(p.x * W + (p.dx || 0), p.y * H + (p.dy || 0)); continue; }
      const role = ROLES[p.place] || ROLES[e.constructor.defaults.place] || ['C', 0];
      const [band, ord] = role;
      if (ord === 's') bands[band].store.push(e); else bands[band].main.push({ e, ord });
    }
    for (const k in bands) bands[k].main.sort((a, b) => a.ord - b.ord || a.e.index - b.e.index), (bands[k].main = bands[k].main.map((m) => m.e));
    const stackH = (arr) => arr.reduce((s, e) => s + e.h, 0) + Math.max(0, arr.length - 1) * GAP;
    const nudge = (e) => { if (e.props.dx || e.props.dy) e.place(e.cx + (e.props.dx || 0), e.cy + (e.props.dy || 0)); };
    if (!P) {
      const X = { L: W * 0.2, C: W * 0.5, R: W * 0.79 };
      for (const k of ['L', 'C', 'R']) {
        const { main, store } = bands[k];
        const mh = stackH(main), sh = stackH(store);
        const avail = bot - top;
        const stackDown = (arr, y0, x) => { let y = y0; for (const e of arr) { e.place(x, y + e.h / 2); y += e.h + GAP; } };
        if (main.length && store.length && mh + sh + GAP <= avail) {
          const regionB = bot - sh - GAP;
          stackDown(main, top + Math.max(0, (regionB - top - mh) / 2), X[k]);
          stackDown(store, bot - sh, X[k]);
        } else if (main.length && store.length) {
          stackDown(main, top + (avail - mh) / 2, X[k]);
          const mw = Math.max(...main.map((e) => e.w));
          const sw = Math.max(...store.map((e) => e.w));
          const dir = k === 'R' ? -1 : 1;
          stackDown(store, bot - sh, X[k] + dir * (mw / 2 + sw / 2 + 48));
        } else if (main.length) stackDown(main, top + (avail - mh) / 2, X[k]);
        else if (store.length) stackDown(store, bot - sh, X[k]);
        for (const e of main.concat(store)) nudge(e);
      }
    } else {
      // portrait: bands become rows (client row, center row, server row, store row)
      const rows = [bands.L.main, bands.C.main, bands.R.main, [].concat(bands.L.store, bands.C.store, bands.R.store)].filter((r) => r.length);
      const hs = rows.map((r) => Math.max(...r.map((e) => e.h)));
      const total = hs.reduce((a, b) => a + b, 0);
      const g = Math.max(40, (bot - top - total) / (rows.length + 1));
      let y = top + g;
      rows.forEach((r, i) => {
        const tw = r.reduce((s, e) => s + e.w, 0) + (r.length - 1) * 48;
        let x = W / 2 - tw / 2;
        if (r.length === 1 && r[0] instanceof Hacker) x = W * 0.74 - r[0].w / 2;
        for (const e of r) { e.place(x + e.w / 2, y + hs[i] / 2); x += e.w + 48; nudge(e); }
        y += hs[i] + g;
      });
    }
  });
})();
