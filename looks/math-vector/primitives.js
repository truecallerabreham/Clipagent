/* math-vector Look: Primitives (3Blue1Brown style). Scene vocabulary: PRIMITIVES.md.
 *
 * TeX is laid out by KaTeX (off-stage), then every glyph is redrawn as an SVG path from the
 * Computer Modern outlines in assets/katex/glyphs/*.js. That makes equations behave like Manim
 * VMobjects: they are written on stroke-by-stroke (outline drawn, then filled), recolored by
 * substring, and morphed glyph-by-glyph (TransformMatchingTex) or path-to-path (flubber).
 *
 * All animation state is compiled from Beats into tracks at build time; render(t) is pure.
 */
(function () {
  'use strict';
  const CA = window.CA;
  const { Primitive, Track, Events, register, registerLayout, svgEl, css, attr, clamp, lerp, prog, bump, getEase, mixColor, drawOn } = CA;
  const SM = CA.ease.smooth;
  const C = {
    grid: '#29ABCA', white: '#FFFFFF', yellow: '#FFFF00', green: '#83C167', red: '#FC6255', orange: '#FF862F',
    ghost: '#8A8A8A', dim: '#BBBBBB',
  };
  const I3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];
  const f2 = (v) => (Math.round(v * 100) / 100).toString();

  // ================================================================== glyph outlines
  const G = (window.MV_GLYPHS = window.MV_GLYPHS || {});
  let LOOK_BASE = '';
  /** Glyph table for a KaTeX font file name (e.g. "Main-Regular"); rare fonts load on demand (sync). */
  function fontData(name) {
    if (G[name]) return G[name];
    if (G[name] === null) return null;
    try {
      const x = new XMLHttpRequest();
      x.open('GET', LOOK_BASE + 'assets/katex/glyphs/' + name + '.js', false);
      x.send();
      if (x.status === 200 || (x.status === 0 && x.responseText)) (0, eval)(x.responseText);
    } catch (e) { /* missing font: caller falls back */ }
    if (!G[name]) G[name] = null;
    return G[name];
  }

  const _parsed = new Map();
  /** Parse an absolute M/L/H/V/Q/C/Z path into [[cmd, nums]] with H/V turned into L. */
  function parseD(d) {
    let r = _parsed.get(d);
    if (r) return r;
    r = [];
    const re = /([MLHVQCZ])([^MLHVQCZ]*)/g;
    let m, cx = 0, cy = 0, sx = 0, sy = 0;
    while ((m = re.exec(d))) {
      const s = m[2].trim();
      const n = s ? s.split(/[\s,]+/).map(Number) : [];
      switch (m[1]) {
        case 'M': cx = n[0]; cy = n[1]; sx = cx; sy = cy; r.push(['M', [cx, cy]]);
          for (let i = 2; i + 1 < n.length; i += 2) { cx = n[i]; cy = n[i + 1]; r.push(['L', [cx, cy]]); } break;
        case 'L': for (let i = 0; i + 1 < n.length; i += 2) { cx = n[i]; cy = n[i + 1]; r.push(['L', [cx, cy]]); } break;
        case 'H': for (const v of n) { cx = v; r.push(['L', [cx, cy]]); } break;
        case 'V': for (const v of n) { cy = v; r.push(['L', [cx, cy]]); } break;
        case 'Q': for (let i = 0; i + 3 < n.length; i += 4) { r.push(['Q', n.slice(i, i + 4)]); cx = n[i + 2]; cy = n[i + 3]; } break;
        case 'C': for (let i = 0; i + 5 < n.length; i += 6) { r.push(['C', n.slice(i, i + 6)]); cx = n[i + 4]; cy = n[i + 5]; } break;
        case 'Z': r.push(['Z', []]); cx = sx; cy = sy; break;
      }
    }
    _parsed.set(d, r);
    return r;
  }
  /** Affine (scale + translate) transform of a parsed path -> d string. */
  function tfD(d, sx, sy, tx, ty) {
    const p = typeof d === 'string' ? parseD(d) : d;
    let out = '';
    for (const [c, n] of p) {
      out += c;
      for (let j = 0; j < n.length; j += 2) out += (j ? ' ' : '') + f2(tx + sx * n[j]) + ' ' + f2(ty + sy * n[j + 1]);
    }
    return out;
  }
  function bboxD(d, sx, sy, tx, ty) {
    const p = parseD(d);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [, n] of p) for (let j = 0; j < n.length; j += 2) {
      const x = tx + sx * n[j], y = ty + sy * n[j + 1];
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    return x0 === Infinity ? null : [x0, y0, x1, y1];
  }
  /** Flatten a parsed path to polygon rings (beziers sampled), with transform. */
  function ringsD(d, sx = 1, sy = 1, tx = 0, ty = 0) {
    const p = parseD(d);
    const rings = [];
    let cur = null, px = 0, py = 0;
    const push = (x, y) => { cur.push([tx + sx * x, ty + sy * y]); px = x; py = y; };
    for (const [c, n] of p) {
      if (c === 'M') { cur = []; rings.push(cur); push(n[0], n[1]); }
      else if (c === 'L') push(n[0], n[1]);
      else if (c === 'Q') { const x0 = px, y0 = py; for (let k = 1; k <= 6; k++) { const s = k / 6, u = 1 - s; push(u * u * x0 + 2 * u * s * n[0] + s * s * n[2], u * u * y0 + 2 * u * s * n[1] + s * s * n[3]); } }
      else if (c === 'C') { const x0 = px, y0 = py; for (let k = 1; k <= 8; k++) { const s = k / 8, u = 1 - s; push(u * u * u * x0 + 3 * u * u * s * n[0] + 3 * u * s * s * n[2] + s * s * s * n[4], u * u * u * y0 + 3 * u * u * s * n[1] + 3 * u * s * s * n[3] + s * s * s * n[5]); } }
    }
    return rings.filter((r) => r.length > 2);
  }
  const ringArea = (r) => { let a = 0; for (let i = 0; i < r.length; i++) { const p = r[i], q = r[(i + 1) % r.length]; a += p[0] * q[1] - q[0] * p[1]; } return Math.abs(a / 2); };
  const largestRing = (rings) => rings.reduce((b, r) => (!b || ringArea(r) > ringArea(b) ? r : b), null);
  const ringD = (r) => 'M' + r.map((p) => f2(p[0]) + ' ' + f2(p[1])).join('L') + 'Z';
  const polyD = (pts, closed) => (pts.length ? 'M' + pts.map((p) => f2(p[0]) + ' ' + f2(p[1])).join('L') + (closed ? 'Z' : '') : '');
  const polyLen = (pts, closed) => { let L = 0; for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); if (closed && pts.length > 1) L += Math.hypot(pts[0][0] - pts[pts.length - 1][0], pts[0][1] - pts[pts.length - 1][1]); return L; };
  /** Resample a polyline to n points evenly by arc length. */
  function resample(pts, n, closed) {
    const P = closed && pts.length > 1 ? pts.concat([pts[0]]) : pts;
    if (P.length < 2) return Array.from({ length: n }, () => (P[0] || [0, 0]).slice());
    const cum = [0];
    for (let i = 1; i < P.length; i++) cum.push(cum[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]));
    const L = cum[cum.length - 1] || 1e-9, out = [];
    let j = 1;
    for (let k = 0; k < n; k++) {
      const s = (L * k) / (n - (closed ? 0 : 1));
      while (j < cum.length - 1 && cum[j] < s) j++;
      const seg = cum[j] - cum[j - 1] || 1e-9, u = clamp((s - cum[j - 1]) / seg);
      out.push([lerp(P[j - 1][0], P[j][0], u), lerp(P[j - 1][1], P[j][1], u)]);
    }
    return out;
  }
  /** Polyline cut to arc length s (for dashed draw-on, where dashes must stay anchored). */
  function cutPoly(pts, s) {
    if (pts.length < 2 || s <= 0) return [];
    const out = [pts[0]];
    let acc = 0;
    for (let i = 1; i < pts.length; i++) {
      const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      if (acc + l >= s) { const u = (s - acc) / (l || 1e-9); out.push([lerp(pts[i - 1][0], pts[i][0], u), lerp(pts[i - 1][1], pts[i][1], u)]); return out; }
      acc += l; out.push(pts[i]);
    }
    return out;
  }
  const rgbToHex = (s) => {
    const m = String(s).match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    return m ? CA.rgbToHex(+m[1], +m[2], +m[3]) : (CA.isHex(s) ? s : '#FFFFFF');
  };

  // ================================================================== TeX layout (KaTeX -> glyph paths)
  let measureBox = null;
  const texCache = new Map();
  const MACROS = { '\\ihat': '\\hat{\\imath}', '\\jhat': '\\hat{\\jmath}', '\\R': '\\mathbb{R}', '\\N': '\\mathbb{N}' };

  /** {{...}} groups -> \htmlClass{mvp-N}{...}; keys[N] = {key: content}. */
  function prepParts(tex, keys) {
    let out = '', i = 0;
    while (i < tex.length) {
      if (tex[i] === '\\') { out += tex.slice(i, i + 2); i += 2; continue; }
      if (tex[i] === '{' && tex[i + 1] === '{') {
        let j = i + 2, depth = 0;
        for (; j < tex.length; j++) {
          const ch = tex[j];
          if (ch === '\\') { j++; continue; }
          if (ch === '{') depth++;
          else if (ch === '}') { if (depth === 0 && tex[j + 1] === '}') break; depth--; }
        }
        const inner = tex.slice(i + 2, j);
        const n = keys.length;
        keys.push({ key: inner.trim() });
        out += `\\htmlClass{mvp-${n}}{` + prepParts(inner, keys) + '}';
        i = j + 2;
        continue;
      }
      out += tex[i++];
    }
    return out;
  }
  /** Color substrings (Manim's tex_to_color_map). Control words are never split. */
  function applyColors(tex, colors, resolve) {
    if (!colors) return tex;
    const keys = Object.keys(colors).sort((a, b) => b.length - a.length);
    let out = '', i = 0;
    outer: while (i < tex.length) {
      for (const k of keys) {
        if (k && tex.startsWith(k, i)) {
          const next = tex[i + k.length];
          if (/^\\[a-zA-Z]+$/.test(k) && next && /[a-zA-Z]/.test(next)) continue; // \x must not match \xi
          out += `{\\color{${resolve(colors[k])}}${k}}`;
          i += k.length;
          continue outer;
        }
      }
      if (tex[i] === '\\') {
        const m = tex.slice(i).match(/^\\([a-zA-Z]+|.)/);
        out += m[0]; i += m[0].length;
        continue;
      }
      out += tex[i++];
    }
    return out;
  }
  function resolveNamedColors(tex, resolve) {
    return tex.replace(/\\(textcolor|color)\{([^}]+)\}/g, (all, cmd, name) => `\\${cmd}{${resolve(name.trim())}}`);
  }

  const FONT_FILES = (fam, bold, italic) => {
    fam = fam.replace(/^KaTeX_/, '');
    if (fam === 'Math') return [bold ? 'Math-BoldItalic' : 'Math-Italic', 'Math-Italic'];
    const style = bold && italic ? 'BoldItalic' : bold ? 'Bold' : italic ? 'Italic' : 'Regular';
    return [`${fam}-${style}`, `${fam}-Regular`, 'Main-Regular'];
  };

  /**
   * Lay out TeX at `size` (design px per em) and return glyph items in local coords:
   * {w, h, items: [{kind: 'g'|'rect'|'svg', d, color, key, part, meta, bb, bl}]}.
   */
  function layoutTex(scene, tex, size, opts = {}) {
    const resolve = (c) => scene.resolveColor(c) || c;
    const color = resolve(opts.color || C.white);
    const ck = [tex, size, color, JSON.stringify(opts.colors || null), JSON.stringify(opts.keys || null)].join('|');
    if (texCache.has(ck)) return texCache.get(ck);
    if (!measureBox) measureBox = CA.el('div', { id: 'mv-measure' }, document.body);
    const keys = (opts.keys || []).slice();
    let src = resolveNamedColors(applyColors(prepParts(String(tex), keys), opts.colors, resolve), resolve);
    const host = CA.el('div', {}, measureBox);
    host.style.fontSize = size / 1.21 + 'px';
    host.style.color = color;
    try {
      window.katex.render('\\displaystyle ' + src, host, { displayMode: false, throwOnError: true, trust: true, strict: 'ignore', output: 'html', macros: Object.assign({}, MACROS) });
    } catch (err) {
      console.error('math-vector: KaTeX error in', JSON.stringify(tex), err);
      throw new Error(`TeX error in "${tex}": ${err.message}`);
    }
    const hr = host.getBoundingClientRect();
    const raw = [];
    // --- glyphs: baseline markers, then per-character ranges
    const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
    const texts = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) if (n.data.trim()) texts.push(n);
    const markers = texts.map((n) => {
      const m = document.createElement('span');
      m.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline;';
      n.parentNode.insertBefore(m, n.nextSibling);
      return m;
    });
    const range = document.createRange();
    texts.forEach((node, ti) => {
      const par = node.parentElement;
      const cs = getComputedStyle(par);
      const fam = cs.fontFamily.split(',')[0].replace(/["']/g, '').trim();
      const bold = parseInt(cs.fontWeight, 10) >= 600, italic = cs.fontStyle === 'italic';
      let font = null, fname = null;
      for (const cand of FONT_FILES(fam.startsWith('KaTeX_') ? fam : 'KaTeX_Main', bold, italic)) { font = fontData(cand); if (font) { fname = cand; break; } }
      if (!font) return;
      const px = parseFloat(cs.fontSize);
      const col = rgbToHex(cs.color);
      const bl = markers[ti].getBoundingClientRect().top - hr.top;
      const partEl = par.closest('[class*="mvp-"]');
      let part = null, meta = null;
      if (partEl && host.contains(partEl)) {
        const k = keys[+partEl.className.match(/mvp-(\d+)/)[1]];
        part = k.key; meta = k.meta || null;
      }
      const s = node.data;
      for (let i = 0; i < s.length;) {
        const cp = s.codePointAt(i), len = cp > 0xffff ? 2 : 1;
        let gl = font.g[cp], f = font, fn = fname;
        if (!gl) { const m = fontData('Main-Regular'); if (m && m.g[cp]) { gl = m.g[cp]; f = m; fn = 'Main-Regular'; } }
        if (gl && gl[1]) {
          range.setStart(node, i); range.setEnd(node, i + len);
          const r = range.getBoundingClientRect();
          const sc = px / f.upm;
          raw.push({ kind: 'g', src: gl[1], sc, x: r.left - hr.left, y: bl, color: col, key: fn + ':' + cp, part, meta });
        }
        i += len;
      }
    });
    markers.forEach((m) => m.remove());
    // --- rules (fraction bars, over/underlines, \hline, \rule)
    host.querySelectorAll('.frac-line, .overline-line, .underline-line, .hline, .rule, .hdashline').forEach((e) => {
      const cs = getComputedStyle(e);
      const r = e.getBoundingClientRect();
      let x = r.left - hr.left, y = r.top - hr.top, w = r.width, h = r.height;
      if (!e.classList.contains('rule')) { const bw = parseFloat(cs.borderBottomWidth) || 0; if (bw <= 0) return; y = y + h - bw; h = bw; }
      if (w <= 0 || h <= 0) return;
      const partEl = e.closest('[class*="mvp-"]');
      const part = partEl && host.contains(partEl) ? keys[+partEl.className.match(/mvp-(\d+)/)[1]].key : null;
      raw.push({ kind: 'rect', x, y, w, h, color: rgbToHex(cs.borderBottomColor || cs.color), key: 'rect', part });
    });
    // --- inline SVG pieces (sqrt, \vec, stretchy arrows/braces, tall delimiters)
    host.querySelectorAll('svg').forEach((sv) => {
      const r = sv.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) return;
      const vb = (sv.getAttribute('viewBox') || `0 0 ${r.width} ${r.height}`).split(/[\s,]+/).map(Number);
      const par = (sv.getAttribute('preserveAspectRatio') || 'xMidYMid meet').split(/\s+/);
      let sx = r.width / vb[2], sy = r.height / vb[3], ax = 0, ay = 0;
      if (par[0] !== 'none') {
        const s = par[1] === 'slice' ? Math.max(sx, sy) : Math.min(sx, sy);
        const ex = r.width - vb[2] * s, ey = r.height - vb[3] * s;
        ax = /xMid/.test(par[0]) ? ex / 2 : /xMax/.test(par[0]) ? ex : 0;
        ay = /YMid/.test(par[0]) ? ey / 2 : /YMax/.test(par[0]) ? ey : 0;
        sx = sy = s;
      }
      let clip = [r.left, r.top, r.right, r.bottom];
      for (let e = sv.parentElement; e && e !== host; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (cs.overflow === 'hidden' || cs.overflowX === 'hidden') {
          const q = e.getBoundingClientRect();
          clip = [Math.max(clip[0], q.left), Math.max(clip[1], q.top), Math.min(clip[2], q.right), Math.min(clip[3], q.bottom)];
        }
      }
      if (clip[2] <= clip[0] || clip[3] <= clip[1]) return;
      const col = rgbToHex(getComputedStyle(sv).color || getComputedStyle(sv.parentElement).color);
      sv.querySelectorAll('path').forEach((p) => {
        raw.push({ kind: 'svg', d: p.getAttribute('d'), m: [sx, sy, r.left - hr.left + ax - vb[0] * sx, r.top - hr.top + ay - vb[1] * sy],
          clip: [clip[0] - hr.left, clip[1] - hr.top, clip[2] - clip[0], clip[3] - clip[1]], color: col, key: 'svg' });
      });
    });
    host.remove();
    // --- normalize to the ink bounding box
    let X0 = Infinity, Y0 = Infinity, X1 = -Infinity, Y1 = -Infinity;
    const bbs = raw.map((it) => {
      let b;
      if (it.kind === 'g') b = bboxD(it.src, it.sc, it.sc, it.x, it.y);
      else if (it.kind === 'rect') b = [it.x, it.y, it.x + it.w, it.y + it.h];
      else {
        // ink box of the svg path (not its viewport), clipped
        let ib = null;
        try { const bx = CA.PathLUT._scratch(it.d).getBBox(); ib = [it.m[2] + it.m[0] * bx.x, it.m[3] + it.m[1] * bx.y, it.m[2] + it.m[0] * (bx.x + bx.width), it.m[3] + it.m[1] * (bx.y + bx.height)]; } catch (e) { ib = null; }
        const c = [it.clip[0], it.clip[1], it.clip[0] + it.clip[2], it.clip[1] + it.clip[3]];
        b = ib ? [Math.max(c[0], ib[0]), Math.max(c[1], ib[1]), Math.min(c[2], ib[2]), Math.min(c[3], ib[3])] : c;
        if (b[2] <= b[0] || b[3] <= b[1]) b = null;
      }
      if (b) { X0 = Math.min(X0, b[0]); Y0 = Math.min(Y0, b[1]); X1 = Math.max(X1, b[2]); Y1 = Math.max(Y1, b[3]); }
      return b;
    });
    if (X0 === Infinity) { X0 = Y0 = 0; X1 = Y1 = 1; }
    const items = [];
    raw.forEach((it, i) => {
      const b = bbs[i];
      if (!b) return;
      const bb = [b[0] - X0, b[1] - Y0, b[2] - X0, b[3] - Y0];
      if (it.kind === 'g') items.push({ kind: 'g', d: tfD(it.src, it.sc, it.sc, it.x - X0, it.y - Y0), color: it.color, key: it.key, part: it.part, meta: it.meta, bb, bl: it.y - Y0 });
      else if (it.kind === 'rect') {
        const x = it.x - X0, y = it.y - Y0;
        items.push({ kind: 'rect', d: `M${f2(x)} ${f2(y)}L${f2(x + it.w)} ${f2(y)}L${f2(x + it.w)} ${f2(y + it.h)}L${f2(x)} ${f2(y + it.h)}Z`, color: it.color, key: 'rect', part: it.part, bb });
      } else items.push({ kind: 'svg', d: it.d, m: [it.m[0], it.m[1], it.m[2] - X0, it.m[3] - Y0], clip: [it.clip[0] - X0, it.clip[1] - Y0, it.clip[2], it.clip[3]], color: it.color, key: 'svg', bb });
    });
    // write in reading order (accents and rules interleave with their glyphs)
    items.sort((a, b) => (a.bb[0] + a.bb[2]) / 2 - (b.bb[0] + b.bb[2]) / 2 || a.bb[1] - b.bb[1]);
    const g0 = items.find((it) => it.kind === 'g');
    const L = { w: X1 - X0, h: Y1 - Y0, items, bl: g0 ? g0.bl : (Y1 - Y0) * 0.75, size };
    texCache.set(ck, L);
    return L;
  }

  /** Lag-ratio schedule (Manim Write): item i of n gets window [start, start + w] of the 0..1 progress. */
  function lagWindow(i, n) {
    if (n <= 1) return [0, 1];
    const w = Math.min(1, 3.4 / (n + 2.4));
    return [(i * (1 - w)) / (n - 1), w];
  }
  /** Draw-border-then-fill for one glyph path at local progress q. */
  function writeItem(en, q, color) {
    const p = en.el;
    if (color !== en._c) { attr(p, 'fill', color); if (en.it.kind !== 'svg') attr(p, 'stroke', color); en._c = color; }
    if (en.it.kind === 'svg') {
      const c = en.it.clip;
      attr(en.clipRect, 'width', f2(c[2] * SM(clamp(q))));
      attr(p, 'visibility', q <= 0 ? 'hidden' : 'visible');
      return;
    }
    if (q <= 0) { attr(p, 'visibility', 'hidden'); return; }
    if (q >= 1) {
      attr(p, 'visibility', 'visible'); attr(p, 'fill-opacity', '1'); attr(p, 'stroke-opacity', '0'); attr(p, 'stroke-dasharray', 'none');
      return;
    }
    drawOn(p, SM(clamp(q / 0.62)));
    const f = SM(clamp((q - 0.42) / 0.58));
    attr(p, 'fill-opacity', f.toFixed(3));
    attr(p, 'stroke-opacity', (1 - f * f).toFixed(3));
  }
  let clipSeq = 0;
  function mkItemPath(parent, defs, it, sw) {
    if (it.kind === 'svg') {
      const id = 'mvclip' + clipSeq++;
      const cp = svgEl('clipPath', { id, clipPathUnits: 'userSpaceOnUse' }, defs);
      const c = it.clip;
      const clipRect = svgEl('rect', { x: f2(c[0]), y: f2(c[1]), width: f2(c[2]), height: f2(c[3]) }, cp);
      const g = svgEl('g', { 'clip-path': `url(#${id})` }, parent);
      const el = svgEl('path', { d: it.d, transform: `matrix(${it.m[0]} 0 0 ${it.m[1]} ${f2(it.m[2])} ${f2(it.m[3])})`, fill: it.color, stroke: 'none' }, g);
      return { el, it, clipRect, wrap: g };
    }
    const el = svgEl('path', { d: it.d, fill: it.color, stroke: it.color, 'stroke-width': sw, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'fill-opacity': 0, visibility: 'hidden' }, parent);
    return { el, it, wrap: el };
  }

  /** A drawable TeX layout (one <g> of glyph paths) placed at a local origin. */
  class GlyphSet {
    constructor(parent, defs, L, opts = {}) {
      this.L = L;
      this.g = svgEl('g', {}, parent);
      this.sw = opts.sw ?? Math.max(1.1, L.size * 0.028);
      this.entries = L.items.map((it) => mkItemPath(this.g, defs, it, this.sw));
      this._vis = null;
    }
    place(ox, oy) { attr(this.g, 'transform', `translate(${f2(ox)} ${f2(oy)})`); }
    show(v) { if (v !== this._vis) { this._vis = v; attr(this.g, 'display', v ? 'inline' : 'none'); } }
    /** p = write progress 0..1; colorOf(item) -> color */
    write(p, colorOf) {
      const n = this.entries.length;
      this.entries.forEach((en, i) => {
        const [s, w] = lagWindow(i, n);
        writeItem(en, clamp((p - s) / w), colorOf ? colorOf(en.it) : en.it.color);
      });
    }
  }

  // ================================================================== base class
  const ANCH = { center: [0.5, 0.5], left: [0, 0.5], right: [1, 0.5], top: [0.5, 0], bottom: [0.5, 1], up: [0.5, 0], down: [0.5, 1], ul: [0, 0], ur: [1, 0], dl: [0, 1], dr: [1, 1] };
  const DIRS = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1], ur: [0.7071, -0.7071], ul: [-0.7071, -0.7071], dr: [0.7071, 0.7071], dl: [-0.7071, 0.7071] };

  class MV extends Primitive {
    static layer = 'nodes';
    static actions = {
      enter: { dur: 1.0, ease: 'linear' }, write: { dur: 1.0, ease: 'linear' }, create: { dur: 1.0, ease: 'linear' },
      exit: { dur: 0.7, ease: 'linear' }, fade_out: { dur: 0.6, ease: 'smooth' },
      move: { dur: 1.0, ease: 'smooth' }, scale: { dur: 0.8, ease: 'smooth' },
      indicate: { dur: 0.9, ease: 'smooth' }, pulse: { dur: 0.9, ease: 'smooth' },
      circumscribe: { dur: 1.5, ease: 'smooth' }, highlight: { dur: 0.8, ease: 'smooth' }, unhighlight: { dur: 0.6, ease: 'smooth' },
      morph: { dur: 1.4, ease: 'smooth' },
    };
    constructor(scene, def, index) {
      super(scene, def, index);
      this.cr = new Track(0);          // creation / write progress 0..1 (linear in time)
      this.fadeT = new Track(1);
      this.off = new Track([0, 0]);    // move offset (design px)
      this.sc = new Track(1);
      this.inds = [];                  // indicate pulses {at, dur, color}
      this.boxes = [];                 // surrounding rectangles {at, dur, end, endDur, color, part, passing}
      this.morphs = [];                // outgoing morphs {at, dur, ease, pairs, g}
      this.ax = scene.W / 2; this.ay = scene.H / 2;
    }
    get S() { return this.scene; }
    build() {
      const S = this.scene;
      this.root.classList.add('mv-root');
      this.root.style.width = S.W + 'px'; this.root.style.height = S.H + 'px';
      this.svg = svgEl('svg', { width: S.W, height: S.H, viewBox: `0 0 ${S.W} ${S.H}` }, this.root);
      this.defs = svgEl('defs', {}, this.svg);
      this.g = svgEl('g', {}, this.svg);
      this.fxg = svgEl('g', {}, this.svg);
      this.make();
    }
    make() {}
    measure() { this.w = this.scene.W; this.h = this.scene.H; return { w: this.w, h: this.h }; }
    place() {}
    col(c, fb) { return (c && this.scene.resolveColor(c)) || fb; }
    baseColor(fb = C.white) { const p = this.props; return p.concept ? this.scene.conceptColor(p.concept) : this.col(p.color, fb); }
    get plane() {
      const S = this.scene;
      const id = this.props.plane;
      const pl = id ? S.get(id) : S._mvPlane;
      if (pl && pl !== this) pl.layout();
      return pl && pl !== this ? pl : null;
    }
    layout() { if (this._laid) return; this._laid = true; this.doLayout(); }
    doLayout() {}
    /** Center point for a w x h box from props: pos | next_to | to_edge | x,y (+ dx, dy). */
    placeAnchor(w, h) {
      const p = this.props, S = this.scene;
      let cx = S.W / 2, cy = S.H / 2;
      if (p.pos) {
        const q = typeof p.pos === 'string' ? resolvePoint(S, p.pos, 0, this.plane) : this.plane ? this.plane.toScreen(p.pos, 0) : [p.pos[0] * S.W, p.pos[1] * S.H];
        cx = q[0]; cy = q[1];
      } else if (p.next_to) {
        const n = typeof p.next_to === 'string' ? { id: p.next_to } : p.next_to;
        const tg = S.get(n.id);
        tg.layout();
        const b = tg.bbox(n.t ?? 0, n.part);
        const side = n.side || 'right', buff = n.buff ?? 30;
        cx = (b[0] + b[2]) / 2; cy = (b[1] + b[3]) / 2;
        if (side === 'right') cx = b[2] + buff + w / 2;
        else if (side === 'left') cx = b[0] - buff - w / 2;
        else if (side === 'up' || side === 'top') cy = b[1] - buff - h / 2;
        else cy = b[3] + buff + h / 2;
        if (n.align === 'left') cx = b[0] + w / 2;
        if (n.align === 'right') cx = b[2] - w / 2;
      } else if (p.to_edge) {
        const e = p.to_edge, buff = p.buff ?? 64;
        cx = (p.x ?? 0.5) * S.W; cy = (p.y ?? 0.5) * S.H;
        if (/left|^ul$|^dl$/.test(e)) cx = buff + w / 2;
        if (/right|^ur$|^dr$/.test(e)) cx = S.W - buff - w / 2;
        if (/top|^ul$|^ur$|^up$/.test(e)) cy = buff + h / 2;
        if (/bottom|^dl$|^dr$|^down$/.test(e)) cy = S.H - buff - h / 2;
      } else {
        if (p.x != null) cx = p.x * S.W;
        if (p.y != null) cy = p.y * S.H;
      }
      return [cx + (p.dx || 0), cy + (p.dy || 0)];
    }
    /** Local bounding box [x0,y0,x1,y1] before move/scale; subclasses override. */
    localBBox() { return [this.ax - 10, this.ay - 10, this.ax + 10, this.ay + 10]; }
    xform(t) {
      const o = this.off.value(t);
      let s = this.sc.value(t);
      for (const d of this.inds) s *= 1 + 0.2 * bump(t, d.at, d.dur);
      return { dx: o[0], dy: o[1], s };
    }
    /** World bbox at t (optionally of a TeX part). */
    bbox(t, part) {
      const b = this.localBBox(t, part);
      const { dx, dy, s } = this.xform(t);
      const f = (x, y) => [this.ax + dx + (x - this.ax) * s, this.ay + dy + (y - this.ay) * s];
      const a = f(b[0], b[1]), c = f(b[2], b[3]);
      return [a[0], a[1], c[0], c[1]];
    }
    pointAt(anchor, t) {
      const b = this.bbox(t);
      const a = ANCH[anchor] || ANCH.center;
      return [lerp(b[0], b[2], a[0]), lerp(b[1], b[3], a[1])];
    }
    mathPoint() { return null; }
    tintAt(t) {
      let amt = 0, color = C.yellow;
      for (const d of this.inds) { const a = bump(t, d.at, d.dur); if (a > amt) { amt = a; color = d.color; } }
      return { amt, color };
    }

    // ---- actions
    a_enter(at, dur, e, args) {
      if (args.dur == null && this.autoDur) dur = this.autoDur();
      this.cr.to(at, 1, dur, 'linear');
      if (this.enterAt == null || at < this.enterAt) this.enterAt = at;
    }
    a_write(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_create(at, dur, e, args) { this.a_enter(at, dur, e, args); }
    a_exit(at, dur, e, args) {
      if (args.style === 'fade') return this.a_fade_out(at, args.dur ?? 0.6, 'smooth', args);
      this.cr.to(at, 0, dur, 'linear');
    }
    a_fade_out(at, dur, e) { this.fadeT.to(at, 0, dur, e); this.cr.set(at + dur, 0); this.fadeT.set(at + dur + 0.001, 1); }
    a_move(at, dur, e, args) {
      const cur = this.off.value(at);
      let d = [cur[0] + (args.dx || 0), cur[1] + (args.dy || 0)];
      if (args.to != null || args.x != null || args.y != null || args.pos != null) {
        const S = this.scene;
        let tgt;
        if (args.pos) tgt = this.plane ? this.plane.toScreen(args.pos, at) : [args.pos[0] * S.W, args.pos[1] * S.H];
        else if (args.to != null) tgt = resolvePoint(S, args.to, at, this.plane);
        else tgt = [args.x != null ? args.x * S.W : this.ax + cur[0], args.y != null ? args.y * S.H : this.ay + cur[1]];
        const b = this.localBBox(at);
        const a = ANCH[args.anchor || 'center'];
        const px = lerp(b[0], b[2], a[0]), py = lerp(b[1], b[3], a[1]);
        d = [tgt[0] - px + (args.dx || 0), tgt[1] - py + (args.dy || 0)];
      }
      this.off.to(at, d, dur, e);
    }
    a_scale(at, dur, e, args) { this.sc.to(at, args.to ?? (this.sc.value(at) * (args.by ?? 1.2)), dur, e); }
    a_indicate(at, dur, e, args) { this.inds.push({ at, dur, color: this.col(args.color, C.yellow) }); }
    a_pulse(at, dur, e, args) { this.a_indicate(at, dur, e, args); }
    a_circumscribe(at, dur, e, args) { this.boxes.push({ at, dur, color: this.col(args.color, C.yellow), part: args.part, col: args.col, passing: true, buff: args.buff ?? 14 }); }
    a_highlight(at, dur, e, args) {
      const b = { at, dur, color: this.col(args.color, C.yellow), part: args.part, col: args.col, passing: false, buff: args.buff ?? 14, end: Infinity, endDur: 0.5 };
      if (args.hold != null) b.end = at + dur + args.hold;
      this.boxes.push(b);
    }
    a_unhighlight(at, dur) { for (const b of this.boxes) if (!b.passing && b.at <= at && b.end > at) { b.end = at; b.endDur = dur; } }
    a_dim(at, dur, e, args) { this.dimT.to(at, args.level ?? 0.25, dur, e); }
    a_morph(at, dur, e, args) {
      const S = this.scene;
      const tgt = S.get(args.to);
      const src = this.worldPaths(at);
      const dst = tgt.worldPaths(at + dur);
      if (!src.length || !dst.length) throw new Error(`morph: "${this.id}" -> "${args.to}" has nothing to morph`);
      const byX = (a, b) => a.cx - b.cx;
      src.sort(byX); dst.sort(byX);
      const n = Math.max(src.length, dst.length), pairs = [];
      const g = svgEl('g', { display: 'none' }, this.fxg);
      for (let i = 0; i < n; i++) {
        const a = src[Math.floor((i * src.length) / n)], b = dst[Math.floor((i * dst.length) / n)];
        const el = svgEl('path', { 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, g);
        pairs.push({ a, b, f: CA.morph(ringD(a.ring), ringD(b.ring)), el });
      }
      this.morphs.push({ at, dur, ease: getEase(e), pairs, g });
      this.cr.set(at, 0);
      tgt.cr.set(at + dur, 1);
      if (tgt.enterAt == null || at < tgt.enterAt) tgt.enterAt = at;
    }
    /** World-space shapes for morphing: [{ring, color, fill, fillOp, sw, cx}] */
    worldPaths() { return []; }
    xfRing(r, t) {
      const { dx, dy, s } = this.xform(t);
      return r.map(([x, y]) => [this.ax + dx + (x - this.ax) * s, this.ay + dy + (y - this.ay) * s]);
    }

    // ---- render
    render(t) {
      const op = this.dimT.value(t) * this.fadeT.value(t);
      css(this.root, 'opacity', op.toFixed(3));
      css(this.root, 'visibility', op <= 0.001 ? 'hidden' : 'visible');
      if (op <= 0.001) return;
      const { dx, dy, s } = this.xform(t);
      attr(this.g, 'transform', s === 1 ? `translate(${f2(dx)} ${f2(dy)})` : `translate(${f2(this.ax + dx)} ${f2(this.ay + dy)}) scale(${s.toFixed(4)}) translate(${f2(-this.ax)} ${f2(-this.ay)})`);
      this.draw(t, this.cr.value(t));
      this.renderMorphs(t);
      this.renderBoxes(t);
    }
    draw() {}
    renderMorphs(t) {
      for (const m of this.morphs) {
        const on = t >= m.at && t < m.at + m.dur;
        attr(m.g, 'display', on ? 'inline' : 'none');
        if (!on) continue;
        const p = m.ease(clamp((t - m.at) / m.dur));
        for (const q of m.pairs) {
          attr(q.el, 'd', q.f(p));
          const c = mixColor(q.a.color, q.b.color, p);
          const fo = lerp(q.a.fill ? q.a.fillOp : 0, q.b.fill ? q.b.fillOp : 0, p);
          const sw = lerp(q.a.fill ? 0 : q.a.sw, q.b.fill ? 0 : q.b.sw, p);
          attr(q.el, 'fill', c); attr(q.el, 'fill-opacity', fo.toFixed(3));
          attr(q.el, 'stroke', c); attr(q.el, 'stroke-width', Math.max(sw, 0.8).toFixed(2));
          attr(q.el, 'stroke-opacity', fo > 0.95 && sw < 0.5 ? '0' : '1');
        }
      }
    }
    renderBoxes(t) {
      for (const b of this.boxes) {
        if (!b.el) b.el = svgEl('path', { fill: 'none', 'stroke-width': 4, 'stroke-linejoin': 'round' }, this.fxg);
        let a0 = 0, a1 = 0;
        if (b.passing) {
          const u = clamp((t - b.at) / b.dur);
          a1 = SM(clamp(u / 0.6)); a0 = SM(clamp((u - 0.4) / 0.6));
        } else {
          a1 = SM(clamp((t - b.at) / b.dur));
          if (t >= b.end) a1 = 1 - SM(clamp((t - b.end) / b.endDur));
        }
        if (t < b.at || a1 - a0 <= 0.001) { attr(b.el, 'visibility', 'hidden'); continue; }
        const bb = b.col != null && this.colBBox ? this.colBBox(t, b.col) : this.bbox(t, b.part);
        const x0 = bb[0] - b.buff, y0 = bb[1] - b.buff, x1 = bb[2] + b.buff, y1 = bb[3] + b.buff;
        const pts = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
        const L = polyLen(pts, false);
        attr(b.el, 'visibility', 'visible');
        attr(b.el, 'stroke', b.color);
        attr(b.el, 'd', polyD(pts, false));
        attr(b.el, 'stroke-dasharray', `0 ${f2(a0 * L)} ${f2((a1 - a0) * L)} ${f2(L + 1)}`);
      }
    }
  }

  // ================================================================== point resolution
  /** Screen point for a reference: [x,y(,z)] plane coords (or canvas fractions without a plane),
   *  {x, y} canvas fractions, "id" (vector tip, dot center, element center) or "id.anchor". */
  function resolvePoint(S, ref, t, plane) {
    if (Array.isArray(ref)) return plane ? plane.toScreen(ref, t) : [ref[0] * S.W, ref[1] * S.H];
    if (ref && typeof ref === 'object') return [ref.x * S.W, ref.y * S.H];
    const [id, anchor] = String(ref).split('.');
    const e = S.get(id);
    e.layout && e.layout();
    return e.pointAt(anchor || '', t);
  }
  /** Math (pre-transform) coordinates of a reference, or null if it is not on a plane. */
  function resolveMath(S, ref, t) {
    if (Array.isArray(ref)) return [ref[0], ref[1], ref[2] || 0];
    if (typeof ref !== 'string') return null;
    const [id, anchor] = ref.split('.');
    const e = S.get(id);
    e.layout && e.layout();
    return e.mathPoint ? e.mathPoint(anchor || '', t) : null;
  }

  // ================================================================== NumberPlane / Axes
  const mul3 = (a, b) => {
    const r = new Array(9);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) r[i * 3 + j] = a[i * 3] * b[j] + a[i * 3 + 1] * b[3 + j] + a[i * 3 + 2] * b[6 + j];
    return r;
  };
  const toM3 = (m) => {
    if (!m) return I3.slice();
    if (m.length === 2) return [m[0][0], m[0][1], 0, m[1][0], m[1][1], 0, 0, 0, 1];
    if (m.length === 3 && Array.isArray(m[0])) return [].concat(m[0], m[1], m[2]);
    if (m.length === 4) return [m[0], m[1], 0, m[2], m[3], 0, 0, 0, 1];
    return m.slice(0, 9);
  };

  class NumberPlane extends MV {
    static layer = 'bg';
    static defaults = { grid: true, numbers: false, ticks: false, tips: false, full: true, subdivisions: 2, opacity: 0.4, axis_opacity: 1, number_size: 30 };
    static actions = { apply_matrix: { dur: 2.0, ease: 'smooth' }, reset: { dur: 1.5, ease: 'smooth' }, orbit: { dur: 2.0, ease: 'smooth' } };
    autoDur() { return 1.8; }
    make() {
      this.MT = new Track(I3.slice());
      const v = this.props.view;
      this.camT = new Track(v ? [v.elev ?? v.phi ?? 30, v.azim ?? v.theta ?? -35] : [90, 0]);
      this.ghostT = new Track(0);
      this.ghostG = svgEl('g', {}, this.g);
      this.subG = svgEl('g', {}, this.g);
      this.mainG = svgEl('g', {}, this.g);
      this.axisG = svgEl('g', {}, this.g);
      this.textG = svgEl('g', {}, this.g);
    }
    doLayout() {
      const S = this.S, p = this.props;
      const P = S.portrait;
      const defX = P ? [-4.5, 4.5, 1] : [-8, 8, 1], defY = P ? [-8, 8, 1] : [-4.5, 4.5, 1];
      const xr = (p.x_range || defX).slice(), yr = (p.y_range || defY).slice();
      if (xr[2] == null) xr[2] = 1; if (yr[2] == null) yr[2] = 1;
      this.xr = xr; this.yr = yr; this.zr = p.z_range || null;
      const spanX = xr[1] - xr[0], spanY = yr[1] - yr[0];
      const explicit = p.width || p.height || p.unit || p.x != null || p.y != null;
      this.fullFrame = p.full === true || (p.full !== false && p.grid !== false && !explicit);
      const fill = p.fill ?? (this.fullFrame ? 1 : 0.8);
      let u = p.unit;
      if (!u && p.width) u = p.width / spanX;
      if (!u && p.height) u = p.height / spanY;
      if (!u) u = Math.min((S.W * fill) / spanX, (S.H * fill) / spanY);
      this.u = u;
      const cx = (p.x ?? 0.5) * S.W + (p.dx || 0), cy = (p.y ?? 0.5) * S.H + (p.dy || 0);
      this.ox = cx - u * (xr[0] + xr[1]) / 2;
      this.oy = cy + u * (yr[0] + yr[1]) / 2;
      this.ax = cx; this.ay = cy;
      this.buildLines();
    }
    buildLines() {
      const p = this.props, xr = this.xr, yr = this.yr;
      const gridCol = this.col(p.color, C.grid), axisCol = this.col(p.axis_color, C.white);
      this.lines = [];
      const ext = this.fullFrame ? 2.5 : 0;
      const X0 = xr[0] - ext * (xr[1] - xr[0]) / 2, X1 = xr[1] + ext * (xr[1] - xr[0]) / 2;
      const Y0 = yr[0] - ext * (yr[1] - yr[0]) / 2, Y1 = yr[1] + ext * (yr[1] - yr[0]) / 2;
      const add = (a, b, kind, rank) => this.lines.push({ a, b, kind, rank });
      if (p.grid !== false) {
        const sub = Math.max(1, p.subdivisions | 0);
        for (const [step, kind] of [[xr[2], 'main'], ...(sub > 1 ? [[xr[2] / sub, 'sub']] : [])]) {
          for (let k = Math.ceil(X0 / step - 1e-9); k * step <= X1 + 1e-9; k++) {
            const x = k * step;
            if (Math.abs(x) < 1e-9) continue;
            if (kind === 'sub' && Math.abs(x / xr[2] - Math.round(x / xr[2])) < 1e-6) continue;
            add([x, Y0, 0], [x, Y1, 0], kind, Math.abs(x));
          }
        }
        for (const [step, kind] of [[yr[2], 'main'], ...(sub > 1 ? [[yr[2] / sub, 'sub']] : [])]) {
          for (let k = Math.ceil(Y0 / step - 1e-9); k * step <= Y1 + 1e-9; k++) {
            const y = k * step;
            if (Math.abs(y) < 1e-9) continue;
            if (kind === 'sub' && Math.abs(y / yr[2] - Math.round(y / yr[2])) < 1e-6) continue;
            add([X0, y, 0], [X1, y, 0], kind, Math.abs(y));
          }
        }
      }
      const axX0 = this.fullFrame ? X0 : xr[0], axX1 = this.fullFrame ? X1 : xr[1];
      const axY0 = this.fullFrame ? Y0 : yr[0], axY1 = this.fullFrame ? Y1 : yr[1];
      if (p.axes !== false) {
        if (axY0 <= 0 && axY1 >= 0) add([axX0, 0, 0], [axX1, 0, 0], 'axis', 0);
        if (axX0 <= 0 && axX1 >= 0) add([0, axY0, 0], [0, axY1, 0], 'axis', 0);
        if (this.zr) add([0, 0, this.zr[0]], [0, 0, this.zr[1]], 'axis', 0);
      }
      const maxRank = Math.max(1, ...this.lines.map((l) => l.rank));
      for (const l of this.lines) {
        const parent = l.kind === 'axis' ? this.axisG : l.kind === 'sub' ? this.subG : this.mainG;
        l.el = svgEl('path', {
          fill: 'none', 'stroke-linecap': 'butt',
          stroke: l.kind === 'axis' ? axisCol : gridCol,
          'stroke-width': l.kind === 'axis' ? (p.axis_width ?? 2.5) : l.kind === 'sub' ? 1 : 2,
          'stroke-opacity': l.kind === 'axis' ? p.axis_opacity : l.kind === 'sub' ? p.opacity * 0.45 : p.opacity,
        }, parent);
        l.start = l.kind === 'axis' ? 0 : 0.18 + 0.47 * (l.rank / maxRank);
        l.len = l.kind === 'axis' ? 0.5 : 0.35;
        if (l.kind === 'main' || l.kind === 'axis') {
          l.ghost = svgEl('path', { fill: 'none', stroke: C.ghost, 'stroke-width': l.kind === 'axis' ? 2 : 1.5, 'stroke-opacity': l.kind === 'axis' ? 0.7 : 0.5 }, this.ghostG);
        }
      }
      // ticks, tips, numbers, axis labels
      this.ticks = [];
      if (p.ticks || p.numbers) {
        for (let k = Math.ceil(xr[0] / xr[2]); k * xr[2] <= xr[1] + 1e-9; k++) if (k !== 0) this.ticks.push({ v: [k * xr[2], 0, 0], dir: 'x', n: k * xr[2] });
        for (let k = Math.ceil(yr[0] / yr[2]); k * yr[2] <= yr[1] + 1e-9; k++) if (k !== 0) this.ticks.push({ v: [0, k * yr[2], 0], dir: 'y', n: k * yr[2] });
        for (const tk of this.ticks) tk.el = svgEl('path', { stroke: axisCol, 'stroke-width': 2, fill: 'none' }, this.axisG);
      }
      this.tipEls = [];
      if (p.tips) for (let i = 0; i < 2; i++) this.tipEls.push(svgEl('path', { fill: axisCol, stroke: 'none' }, this.axisG));
      this.labels = [];
      if (p.numbers) {
        const skip = p.number_skip || 1;
        for (const tk of this.ticks) {
          if (Math.round(tk.n / (tk.dir === 'x' ? xr[2] : yr[2])) % skip !== 0) continue;
          const txt = Number.isInteger(tk.n) ? String(tk.n) : tk.n.toFixed(1);
          const L = layoutTex(this.S, txt, p.number_size, { color: p.number_color || C.white });
          const gs = new GlyphSet(this.textG, this.defs, L);
          const s = this.toScreen(tk.v, 0);
          // minus signs hang left so digits stay centred under the tick (Manim convention)
          const minusW = tk.n < 0 && L.items.length > 1 ? L.items[1].bb[0] : 0;
          if (tk.dir === 'x') gs.place(s[0] - (L.w - minusW) / 2 - minusW, s[1] + 14);
          else gs.place(s[0] - L.w - 16, s[1] - L.h / 2);
          this.labels.push(gs);
        }
      }
      for (const [k, dir] of [['x_label', 'x'], ['y_label', 'y']]) {
        if (!p[k]) continue;
        const L = layoutTex(this.S, p[k], p.label_size || 40, { color: p.label_color || C.white });
        const gs = new GlyphSet(this.textG, this.defs, L);
        const end = dir === 'x' ? this.toScreen([xr[1], 0, 0], 0) : this.toScreen([0, yr[1], 0], 0);
        if (dir === 'x') gs.place(end[0] - L.w - 4, end[1] - L.h - 18);
        else gs.place(end[0] + 20, end[1] - 2);
        this.labels.push(gs);
      }
    }
    camAt(t) { return this.camT.value(t); }
    /** Math -> screen. apply = apply the plane's current linear transformation. */
    toScreen(v, t, apply = true) {
      const x = v[0], y = v[1], z = v[2] || 0;
      const m = apply ? this.MT.value(t) : I3;
      const X = m[0] * x + m[1] * y + m[2] * z, Y = m[3] * x + m[4] * y + m[5] * z, Z = m[6] * x + m[7] * y + m[8] * z;
      const [el, az] = this.camAt(t);
      if (el === 90 && az === 0) return [this.ox + this.u * X, this.oy - this.u * Y];
      const ca = Math.cos((az * Math.PI) / 180), sa = Math.sin((az * Math.PI) / 180);
      const se = Math.sin((el * Math.PI) / 180), ce = Math.cos((el * Math.PI) / 180);
      const X2 = X * ca - Y * sa, Y2 = X * sa + Y * ca;
      return [this.ox + this.u * X2, this.oy - this.u * (Y2 * se + Z * ce)];
    }
    applyM(v, t) { const m = this.MT.value(t), x = v[0], y = v[1], z = v[2] || 0; return [m[0] * x + m[1] * y + m[2] * z, m[3] * x + m[4] * y + m[5] * z, m[6] * x + m[7] * y + m[8] * z]; }
    mathPoint(anchor) { return [0, 0, 0]; }
    pointAt(anchor, t) { return anchor === '' || anchor === 'origin' ? this.toScreen([0, 0, 0], t) : super.pointAt(anchor, t); }
    localBBox() {
      const a = this.toScreen([this.xr[0], this.yr[1]], 0, false), b = this.toScreen([this.xr[1], this.yr[0]], 0, false);
      return [a[0], a[1], b[0], b[1]];
    }
    a_apply_matrix(at, dur, e, args) {
      const cur = this.MT.value(at);
      this.MT.to(at, args.absolute ? toM3(args.matrix) : mul3(toM3(args.matrix), cur), dur, e);
      if (args.ghost !== false) this.ghostT.to(at, 1, Math.min(0.5, dur), 'smooth');
    }
    a_reset(at, dur, e) { this.MT.to(at, I3.slice(), dur, e); }
    a_orbit(at, dur, e, args) {
      const c = this.camT.value(at);
      this.camT.to(at, [args.elev ?? args.phi ?? c[0], args.azim ?? args.theta ?? c[1]], dur, e);
    }
    draw(t, c) {
      const ghost = this.ghostT.value(t);
      for (const l of this.lines) {
        const q = SM(clamp((c - l.start) / l.len));
        const a = this.toScreen(l.a, t), b = this.toScreen(l.b, t);
        attr(l.el, 'd', `M${f2(a[0])} ${f2(a[1])}L${f2(b[0])} ${f2(b[1])}`);
        if (q >= 1) { attr(l.el, 'visibility', 'visible'); attr(l.el, 'stroke-dasharray', 'none'); }
        else drawOn(l.el, q, Math.hypot(b[0] - a[0], b[1] - a[1]));
        if (l.ghost) {
          attr(l.ghost, 'visibility', ghost > 0.001 && c >= 1 ? 'visible' : 'hidden');
          if (ghost > 0.001) {
            const g0 = this.toScreen(l.a, t, false), g1 = this.toScreen(l.b, t, false);
            attr(l.ghost, 'd', `M${f2(g0[0])} ${f2(g0[1])}L${f2(g1[0])} ${f2(g1[1])}`);
            attr(l.ghost, 'opacity', (ghost * 0.85).toFixed(3));
          }
        }
      }
      const tq = SM(clamp((c - 0.45) / 0.4));
      for (const tk of this.ticks) {
        const s = this.toScreen(tk.v, t);
        const h = 8 * tq;
        attr(tk.el, 'd', tk.dir === 'x' ? `M${f2(s[0])} ${f2(s[1] - h)}L${f2(s[0])} ${f2(s[1] + h)}` : `M${f2(s[0] - h)} ${f2(s[1])}L${f2(s[0] + h)} ${f2(s[1])}`);
        attr(tk.el, 'visibility', tq > 0 ? 'visible' : 'hidden');
      }
      if (this.tipEls.length) {
        const ends = [[[this.xr[1], 0, 0], [this.xr[0], 0, 0]], [[0, this.yr[1], 0], [0, this.yr[0], 0]]];
        const q = SM(clamp((c - 0.3) / 0.25));
        ends.forEach(([e1, e0], i) => {
          const B = this.toScreen(e1, t), A = this.toScreen(e0, t);
          const L = Math.hypot(B[0] - A[0], B[1] - A[1]) || 1, ux = (B[0] - A[0]) / L, uy = (B[1] - A[1]) / L;
          const tl = 20 * q, hw = 8 * q;
          const tip = [B[0] + ux * 6, B[1] + uy * 6];
          attr(this.tipEls[i], 'd', polyD([tip, [tip[0] - ux * tl - uy * hw, tip[1] - uy * tl + ux * hw], [tip[0] - ux * tl + uy * hw, tip[1] - uy * tl - ux * hw]], true));
          attr(this.tipEls[i], 'visibility', q > 0 ? 'visible' : 'hidden');
        });
      }
      const lq = clamp((c - 0.55) / 0.45);
      const m = this.MT.value(t);
      const moved = Math.abs(m[0] - 1) + Math.abs(m[1]) + Math.abs(m[3]) + Math.abs(m[4] - 1) > 1e-3;
      for (const gs of this.labels) { gs.show(!moved); gs.write(lq); }
    }
  }
  class Axes extends NumberPlane {
    static defaults = Object.assign({}, NumberPlane.defaults, { grid: false, numbers: true, ticks: true, tips: true, full: false });
  }

  // ================================================================== Tex / Label / Title / Matrix
  class Tex extends MV {
    static layer = 'text';
    static defaults = { tex: '', size: 56, color: '#FFFFFF', colors: null, align: 'center' };
    static actions = { transform: { dur: 1.4, ease: 'smooth' }, set_color: { dur: 0.6, ease: 'smooth' } };
    texSource() { return String(this.props.tex); }
    texKeys() { return null; }
    mkLayout(tex, opts = {}) {
      const p = this.props;
      return layoutTex(this.S, tex, opts.size ?? p.size, { color: opts.color ?? this.baseColor(), colors: opts.colors ?? p.colors, keys: opts.keys ?? this.texKeys() });
    }
    autoDur() { const n = this.versions[0].L.items.length; return clamp(0.5 + 0.055 * n, 0.8, 2.6); }
    make() {
      LOOK_BASE = this.S.look.base || LOOK_BASE;
      const L = this.mkLayout(this.texSource());
      this.versions = [{ at: -Infinity, L }];
      this.trans = [];
      this.partColors = new Map();
    }
    originFor(L) {
      const a = this.props.align;
      if (a === 'left') return [this.anchorPt[0], this.anchorPt[1] - L.h / 2];
      if (a === 'right') return [this.anchorPt[0] - L.w, this.anchorPt[1] - L.h / 2];
      return [this.anchorPt[0] - L.w / 2, this.anchorPt[1] - L.h / 2];
    }
    doLayout() {
      const v0 = this.versions[0];
      const [cx, cy] = this.placeAnchor(v0.L.w, v0.L.h);
      const a = this.props.align;
      this.anchorPt = a === 'left' ? [cx - v0.L.w / 2, cy] : a === 'right' ? [cx + v0.L.w / 2, cy] : [cx, cy];
      this.ax = cx; this.ay = cy;
      v0.o = this.originFor(v0.L);
      if (this.props.backdrop) this.backdrop = svgEl('rect', { fill: this.col(this.props.backdrop_color, '#000000'), rx: 10 }, this.g);
      v0.set = new GlyphSet(this.g, this.defs, v0.L);
      v0.set.place(v0.o[0], v0.o[1]);
      this.afterTexLayout && this.afterTexLayout();
    }
    versionAt(t) { let v = this.versions[0]; for (const x of this.versions) if (x.at <= t) v = x; return v; }
    activeTrans(t) { for (const tr of this.trans) if (t >= tr.at && t < tr.at + tr.dur) return tr; return null; }
    localBBox(t, part) {
      const tr = this.activeTrans(t);
      const box = (v) => {
        let its = v.L.items;
        if (part != null) { its = its.filter((it) => it.part === String(part)); if (!its.length) its = v.L.items; }
        const b = [Infinity, Infinity, -Infinity, -Infinity];
        for (const it of its) { b[0] = Math.min(b[0], it.bb[0]); b[1] = Math.min(b[1], it.bb[1]); b[2] = Math.max(b[2], it.bb[2]); b[3] = Math.max(b[3], it.bb[3]); }
        return [b[0] + v.o[0], b[1] + v.o[1], b[2] + v.o[0], b[3] + v.o[1]];
      };
      if (tr) { const p = tr.ease(clamp((t - tr.at) / tr.dur)); const a = box(tr.from), b = box(tr.to); return a.map((v, i) => lerp(v, b[i], p)); }
      return box(this.versionAt(t));
    }
    colBBox(t, col) {
      const v = this.versionAt(t);
      const its = v.L.items.filter((it) => it.meta && it.meta.col === col);
      if (!its.length) return this.bbox(t);
      const b = [Infinity, Infinity, -Infinity, -Infinity];
      for (const it of its) { b[0] = Math.min(b[0], it.bb[0]); b[1] = Math.min(b[1], it.bb[1]); b[2] = Math.max(b[2], it.bb[2]); b[3] = Math.max(b[3], it.bb[3]); }
      const { dx, dy, s } = this.xform(t);
      const f = (x, y) => [this.ax + dx + (x + v.o[0] - this.ax) * s, this.ay + dy + (y + v.o[1] - this.ay) * s];
      return [...f(b[0], b[1]), ...f(b[2], b[3])];
    }
    a_transform(at, dur, e, args) {
      const from = this.versionAt(at);
      const L = this.mkLayout(args.tex, { colors: args.colors, size: args.size, keys: args.keys });
      if (args.align) this.props.align = args.align;
      const to = { at: at + dur, L };
      to.o = this.originFor(L);
      to.set = new GlyphSet(this.g, this.defs, L);
      to.set.place(to.o[0], to.o[1]);
      to.set.show(false);
      this.versions.push(to);
      // match glyphs: same {{part}} + same glyph first, then same glyph anywhere (in order)
      const A = from.L.items, B = L.items, usedA = new Set(), usedB = new Set(), pairs = [];
      const pass = (cond) => {
        for (let i = 0; i < A.length; i++) {
          if (usedA.has(i) || A[i].kind === 'svg') continue;
          for (let j = 0; j < B.length; j++) {
            if (usedB.has(j) || B[j].key !== A[i].key || !cond(A[i], B[j])) continue;
            usedA.add(i); usedB.add(j); pairs.push([i, j]); break;
          }
        }
      };
      if (args.match !== 'none') { pass((a, b) => a.part && a.part === b.part); pass(() => true); }
      const g = svgEl('g', { display: 'none' }, this.g);
      const tr = { at, dur, ease: getEase(e), from, to, g, moves: [], outs: [], ins: [] };
      const sw = Math.max(1.1, L.size * 0.028);
      for (const [i, j] of pairs) {
        const en = mkItemPath(g, this.defs, B[j], sw);
        attr(en.el, 'fill-opacity', 1); attr(en.el, 'stroke-opacity', 0); attr(en.el, 'visibility', 'visible');
        tr.moves.push({ a: A[i], b: B[j], en });
      }
      // unmatched glyphs: morph path-to-path (flubber), paired in reading order; svg pieces fade/write
      const ua = [], ub = [];
      A.forEach((it, i) => { if (usedA.has(i)) return; if (it.kind === 'svg' || args.morph === false) tr.outs.push({ it, en: mkItemPath(g, this.defs, it, sw) }); else ua.push(it); });
      B.forEach((it, j) => { if (usedB.has(j)) return; if (it.kind === 'svg' || args.morph === false) tr.ins.push({ it, en: mkItemPath(g, this.defs, it, sw) }); else ub.push(it); });
      tr.morphs = [];
      if (ua.length && ub.length) {
        const n = Math.max(ua.length, ub.length);
        const ringOf = (it, o) => (largestRing(ringsD(it.d)) || []).map(([x, y]) => [x + o[0], y + o[1]]);
        for (let i = 0; i < n; i++) {
          const a = ua[Math.floor((i * ua.length) / n)], b = ub[Math.floor((i * ub.length) / n)];
          const el = svgEl('path', { stroke: 'none' }, g);
          const fa = mkItemPath(g, this.defs, a, sw), fb = mkItemPath(g, this.defs, b, sw);
          tr.morphs.push({ a, b, el, fa, fb, f: CA.morph(ringD(ringOf(a, from.o)), ringD(ringOf(b, to.o))), firstA: !tr.morphs.some((m) => m.a === a), firstB: !tr.morphs.some((m) => m.b === b) });
        }
      } else {
        for (const it of ua) tr.outs.push({ it, en: mkItemPath(g, this.defs, it, sw) });
        for (const it of ub) tr.ins.push({ it, en: mkItemPath(g, this.defs, it, sw) });
      }
      this.trans.push(tr);
    }
    a_set_color(at, dur, e, args) {
      const key = String(args.part ?? args.tex ?? '');
      if (!this.partColors.has(key)) {
        const v = this.versionAt(at);
        const it = v.L.items.find((x) => x.part === key);
        this.partColors.set(key, new Track(it ? it.color : C.white));
      }
      this.partColors.get(key).to(at, this.col(args.color, C.yellow), dur, e);
    }
    colorFn(t) {
      const tint = this.tintAt(t);
      const pc = this.partColors;
      return (it) => {
        let c = it.part != null && pc.has(it.part) ? pc.get(it.part).value(t) : it.color;
        if (tint.amt > 0.001) c = mixColor(c, tint.color, tint.amt);
        return c;
      };
    }
    draw(t, c) {
      const tr = this.activeTrans(t);
      const colorOf = this.colorFn(t);
      if (this.backdrop) {
        const b = this.localBBox(t), pad = this.props.backdrop_pad ?? 26;
        attr(this.backdrop, 'x', f2(b[0] - pad)); attr(this.backdrop, 'y', f2(b[1] - pad));
        attr(this.backdrop, 'width', f2(b[2] - b[0] + 2 * pad)); attr(this.backdrop, 'height', f2(b[3] - b[1] + 2 * pad));
        attr(this.backdrop, 'fill-opacity', ((this.props.backdrop_opacity ?? 0.85) * clamp(c * 4)).toFixed(3));
      }
      for (const v of this.versions) v.set.show(false);
      for (const x of this.trans) if (x !== tr) attr(x.g, 'display', 'none');
      if (tr) {
        attr(tr.g, 'display', 'inline');
        const p = tr.ease(clamp((t - tr.at) / tr.dur));
        const u = clamp((t - tr.at) / tr.dur);
        const fo = tr.from.o, to = tr.to.o;
        for (const m of tr.moves) {
          const a = m.a.bb, b = m.b.bb;
          const A = [a[0] + fo[0], a[1] + fo[1], a[2] + fo[0], a[3] + fo[1]];
          const B = [b[0] + to[0], b[1] + to[1], b[2] + to[0], b[3] + to[1]];
          const cur = A.map((v, i) => lerp(v, B[i], p));
          const kx = (cur[2] - cur[0]) / Math.max(1e-6, B[2] - B[0]), ky = (cur[3] - cur[1]) / Math.max(1e-6, B[3] - B[1]);
          const tf = `translate(${f2(cur[0])} ${f2(cur[1])}) scale(${kx.toFixed(4)} ${ky.toFixed(4)}) translate(${f2(to[0] - B[0])} ${f2(to[1] - B[1])})`;
          attr(m.en.wrap, 'transform', tf);
          attr(m.en.el, 'fill', mixColor(colorOf(m.a), colorOf(m.b), p));
        }
        for (const o of tr.outs) {
          attr(o.en.wrap, 'transform', `translate(${f2(fo[0])} ${f2(fo[1])})`);
          if (o.it.kind === 'svg') { writeItem(o.en, 1, colorOf(o.it)); attr(o.en.wrap, 'opacity', (1 - SM(clamp(u / 0.4))).toFixed(3)); continue; }
          attr(o.en.el, 'visibility', 'visible'); attr(o.en.el, 'stroke-opacity', '0');
          attr(o.en.el, 'fill', colorOf(o.it));
          attr(o.en.el, 'fill-opacity', (1 - SM(clamp(u / 0.4))).toFixed(3));
        }
        for (const m of tr.morphs) {
          // exact source glyph hands over to the interpolated outline, which hands over to the exact target
          const ca = colorOf(m.a), cb = colorOf(m.b);
          const ka = 1 - SM(clamp(p / 0.15)), kb = SM(clamp((p - 0.85) / 0.15));
          attr(m.el, 'd', m.f(p));
          attr(m.el, 'fill', mixColor(ca, cb, p));
          attr(m.el, 'fill-opacity', (1 - Math.max(ka, kb)).toFixed(3));
          for (const [en, k, c, o, first] of [[m.fa, ka, ca, fo, m.firstA], [m.fb, kb, cb, to, m.firstB]]) {
            attr(en.wrap, 'transform', `translate(${f2(o[0])} ${f2(o[1])})`);
            attr(en.el, 'visibility', first && k > 0.001 ? 'visible' : 'hidden');
            attr(en.el, 'fill', c); attr(en.el, 'fill-opacity', k.toFixed(3)); attr(en.el, 'stroke-opacity', '0');
          }
        }
        for (const o of tr.ins) {
          attr(o.en.wrap, 'transform', `translate(${f2(to[0])} ${f2(to[1])})`);
          writeItem(o.en, clamp((u - 0.2) / 0.75), colorOf(o.it));
        }
        return;
      }
      const v = this.versionAt(t);
      v.set.show(true);
      v.set.write(c, colorOf);
    }
    worldPaths(t) {
      const v = this.versionAt(t);
      const out = [];
      for (const it of v.L.items) {
        let ring;
        if (it.kind === 'svg') {
          const b = it.bb;
          ring = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
        } else ring = largestRing(ringsD(it.d));
        if (!ring) continue;
        ring = this.xfRing(ring.map(([x, y]) => [x + v.o[0], y + v.o[1]]), t);
        const cx = ring.reduce((s, q) => s + q[0], 0) / ring.length;
        out.push({ ring, color: it.color, fill: true, fillOp: 1, sw: 0, cx });
      }
      return out;
    }
  }

  /** Plain text in Computer Modern; $...$ segments are math. */
  function textToTex(s) {
    const esc = (x) => x.replace(/\\/g, '\\textbackslash ').replace(/([#%&_{}$])/g, '\\$1').replace(/~/g, '\\textasciitilde ').replace(/\^/g, '\\textasciicircum ');
    return String(s).split(/(\$[^$]*\$)/).map((seg) => (seg.startsWith('$') && seg.endsWith('$') && seg.length > 1 ? seg.slice(1, -1) : seg ? `\\text{${esc(seg)}}` : '')).join('');
  }
  class Label extends Tex {
    static defaults = Object.assign({}, Tex.defaults, { text: '', size: 42 });
    texSource() { return this.props.tex || textToTex(this.props.text); }
    a_transform(at, dur, e, args) { super.a_transform(at, dur, e, Object.assign({}, args, { tex: args.tex || textToTex(args.text || '') })); }
  }
  class Title extends Label {
    static defaults = Object.assign({}, Label.defaults, { size: 60, to_edge: 'top', buff: 54, underline: true });
    afterTexLayout() {
      if (!this.props.underline) return;
      this.ul = svgEl('path', { fill: 'none', stroke: C.white, 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-opacity': 0.85 }, this.g);
    }
    draw(t, c) {
      super.draw(t, c);
      if (!this.ul) return;
      const b = this.localBBox(t);
      const w = Math.max((b[2] - b[0]) * 1.25, (b[2] - b[0]) + 120), cx = (b[0] + b[2]) / 2, y = b[3] + 22;
      const q = SM(clamp(c / 0.7));
      attr(this.ul, 'd', `M${f2(cx - (w / 2) * q)} ${f2(y)}L${f2(cx + (w / 2) * q)} ${f2(y)}`);
      attr(this.ul, 'visibility', q > 0.002 ? 'visible' : 'hidden');
    }
  }
  class Matrix extends Tex {
    static defaults = Object.assign({}, Tex.defaults, { rows: [[1, 0], [0, 1]], col_colors: null, entry_colors: null, bracket: 'b', prefix: '', suffix: '', size: 52 });
    texKeys() { if (!this._keys) this.texSource(); return this._keys; }
    texSource() {
      const p = this.props;
      return this.buildTex(p.rows, p.col_colors, p.entry_colors, p.prefix, p.suffix);
    }
    buildTex(rows, colColors, entryColors, prefix, suffix) {
      const keys = [];
      const body = rows.map((r, ri) => r.map((v, ci) => {
        const k = keys.length;
        keys.push({ key: String(v), meta: { row: ri, col: ci } });
        const c = (entryColors && entryColors[ri] && entryColors[ri][ci]) || (colColors && colColors[ci]);
        const inner = c ? `\\textcolor{${this.col(c, C.white)}}{${v}}` : String(v);
        return `\\htmlClass{mvp-${k}}{${inner}}`;
      }).join(' & ')).join(' \\\\ ');
      this._keys = keys;
      const env = (this.props.bracket || 'b') + 'matrix';
      return `${prefix || ''}\\begin{${env}} ${body} \\end{${env}}${suffix || ''}`;
    }
    a_transform(at, dur, e, args) {
      if (args.rows) {
        const tex = this.buildTex(args.rows, args.col_colors ?? this.props.col_colors, args.entry_colors, args.prefix ?? this.props.prefix, args.suffix ?? this.props.suffix);
        return super.a_transform(at, dur, e, Object.assign({}, args, { tex, keys: this._keys }));
      }
      super.a_transform(at, dur, e, args);
    }
  }

  // ================================================================== Vector
  class Vector extends MV {
    static defaults = { coords: [1, 1], from: null, color: '#FFFF00', stroke: 6, tip: 30, label: null, label_size: 46, label_pos: 'end', transform: true };
    static actions = { set: { dur: 1.2, ease: 'smooth' }, shift: { dur: 1.2, ease: 'smooth' } };
    make() {
      const p = this.props;
      const c = p.coords || p.to || [1, 1];
      this.coordsT = new Track([c[0], c[1], c[2] || 0]);
      this.tails = [{ at: -Infinity, dur: 0, ease: SM, ref: p.from || [0, 0, 0] }];
      this.color = this.baseColor(C.yellow);
      this.shaft = svgEl('path', { fill: 'none', stroke: this.color, 'stroke-width': p.stroke, 'stroke-linecap': 'butt' }, this.g);
      this.tipEl = svgEl('path', { fill: this.color, stroke: this.color, 'stroke-width': 1, 'stroke-linejoin': 'round' }, this.g);
    }
    doLayout() {
      const p = this.props;
      if (p.label) {
        this.labL = layoutTex(this.S, p.label, p.label_size, { color: this.col(p.label_color, this.color), colors: p.label_colors });
        this.lab = new GlyphSet(this.g, this.defs, this.labL);
      }
      const b = this.localBBox(0);
      this.ax = (b[0] + b[2]) / 2; this.ay = (b[1] + b[3]) / 2;
    }
    tailMath(t) {
      let k = 0;
      for (let i = 0; i < this.tails.length; i++) if (this.tails[i].at <= t) k = i;
      return this._tail(k, t);
    }
    _tail(k, t) {
      const key = this.tails[k];
      const v = resolveMath(this.S, key.ref, t) || [0, 0, 0];
      if (k === 0) return v;
      const p = key.ease(clamp((t - key.at) / key.dur));
      if (p >= 1) return v;
      const prev = this._tail(k - 1, t);
      return [lerp(prev[0], v[0], p), lerp(prev[1], v[1], p), lerp(prev[2] || 0, v[2] || 0, p)];
    }
    tipMath(t) { const a = this.tailMath(t), c = this.coordsT.value(t); return [a[0] + c[0], a[1] + c[1], (a[2] || 0) + c[2]]; }
    mathPoint(anchor, t) {
      if (anchor === 'tail') return this.tailMath(t);
      if (anchor === 'mid') { const a = this.tailMath(t), b = this.tipMath(t); return a.map((v, i) => (v + b[i]) / 2); }
      return this.tipMath(t);
    }
    scr(v, t) {
      const pl = this.plane;
      if (!pl) return [this.S.W / 2 + v[0] * 100, this.S.H / 2 - v[1] * 100];
      return pl.toScreen(v, t, this.props.transform !== false);
    }
    pointAt(anchor, t) {
      if (anchor === 'tail') return this.scr(this.tailMath(t), t);
      if (anchor === 'mid') return this.scr(this.mathPoint('mid', t), t);
      if (anchor === '' || anchor === 'tip') return this.scr(this.tipMath(t), t);
      return super.pointAt(anchor, t);
    }
    /** Values for counters: x, y, z (as displayed after the plane's matrix), length, angle (deg). */
    mathValue(name, t) {
      const pl = this.plane;
      const tip = this.tipMath(t), tail = this.tailMath(t);
      let d = [tip[0] - tail[0], tip[1] - tail[1], tip[2] - tail[2]];
      let tp = tip;
      if (pl && this.props.transform !== false) { tp = pl.applyM(tip, t); const tl = pl.applyM(tail, t); d = [tp[0] - tl[0], tp[1] - tl[1], tp[2] - tl[2]]; }
      switch (name) {
        case 'x': return tp[0];
        case 'y': return tp[1];
        case 'z': return tp[2];
        case 'dx': return d[0];
        case 'dy': return d[1];
        case 'length': return Math.hypot(d[0], d[1], d[2]);
        case 'angle': return (Math.atan2(d[1], d[0]) * 180) / Math.PI;
        default: return tp[0];
      }
    }
    localBBox(t) {
      const a = this.scr(this.tailMath(t), t), b = this.scr(this.tipMath(t), t);
      return [Math.min(a[0], b[0]) - 4, Math.min(a[1], b[1]) - 4, Math.max(a[0], b[0]) + 4, Math.max(a[1], b[1]) + 4];
    }
    a_set(at, dur, e, args) {
      const c = args.coords || args.to;
      this.coordsT.to(at, [c[0], c[1], c[2] || 0], dur, e);
      if (args.label) { /* label text changes are done with a separate Tex */ }
    }
    a_shift(at, dur, e, args) { this.tails.push({ at, dur, ease: getEase(e), ref: args.from ?? args.to ?? [0, 0, 0] }); }
    geom(t, p) {
      const A = this.scr(this.tailMath(t), t), B = this.scr(this.tipMath(t), t);
      const full = Math.hypot(B[0] - A[0], B[1] - A[1]);
      const ux = full > 1e-6 ? (B[0] - A[0]) / full : 1, uy = full > 1e-6 ? (B[1] - A[1]) / full : 0;
      const tipLen = Math.min(this.props.tip, full * 0.35) * p;
      const E = [A[0] + (B[0] - A[0]) * p, A[1] + (B[1] - A[1]) * p];
      const hw = tipLen * 0.46;
      const base = [E[0] - ux * tipLen, E[1] - uy * tipLen];
      const tri = [E, [base[0] - uy * hw, base[1] + ux * hw], [base[0] + uy * hw, base[1] - ux * hw]];
      const shaftEnd = [E[0] - ux * tipLen * 0.85, E[1] - uy * tipLen * 0.85];
      return { A, B, E, ux, uy, tri, shaftEnd, full };
    }
    draw(t, c) {
      const p = SM(clamp(c / 0.85));
      const vis = p > 0.001;
      attr(this.shaft, 'visibility', vis ? 'visible' : 'hidden');
      attr(this.tipEl, 'visibility', vis ? 'visible' : 'hidden');
      const tint = this.tintAt(t);
      const col = tint.amt > 0.001 ? mixColor(this.color, tint.color, tint.amt) : this.color;
      attr(this.shaft, 'stroke', col); attr(this.tipEl, 'fill', col); attr(this.tipEl, 'stroke', col);
      if (vis) {
        const g = this.geom(t, p);
        const sw = Math.min(this.props.stroke, Math.max(1.5, g.full * p * 0.12));
        attr(this.shaft, 'stroke-width', f2(sw));
        attr(this.shaft, 'd', `M${f2(g.A[0])} ${f2(g.A[1])}L${f2(g.shaftEnd[0])} ${f2(g.shaftEnd[1])}`);
        attr(this.tipEl, 'd', polyD(g.tri, true));
      }
      if (this.lab) {
        const q = clamp((c - 0.6) / 0.4);
        const g = this.geom(t, 1);
        const L = this.labL, buff = this.props.label_buff ?? 14;
        let cx, cy;
        if (this.props.label_pos === 'mid' || this.props.label_pos === 'left' || this.props.label_pos === 'right') {
          const m = [(g.A[0] + g.B[0]) / 2, (g.A[1] + g.B[1]) / 2];
          let nx = g.uy, ny = -g.ux;           // left-hand normal (screen, y down)
          if (this.props.label_pos === 'right') { nx = -nx; ny = -ny; }
          if (this.props.label_pos === 'mid' && ny > 0) { nx = -nx; ny = -ny; } // prefer above
          const r = Math.abs(nx) * L.w / 2 + Math.abs(ny) * L.h / 2 + buff;
          cx = m[0] + nx * r; cy = m[1] + ny * r;
        } else {
          const r = Math.abs(g.ux) * L.w / 2 + Math.abs(g.uy) * L.h / 2 + buff;
          cx = g.B[0] + g.ux * r; cy = g.B[1] + g.uy * r;
        }
        this.lab.place(cx - L.w / 2, cy - L.h / 2);
        this.lab.write(q, (it) => (tint.amt > 0.001 ? mixColor(it.color, tint.color, tint.amt) : it.color));
      }
    }
    worldPaths(t) {
      const g = this.geom(t, 1);
      const sw = this.props.stroke / 2;
      const quad = [[g.A[0] - g.uy * sw, g.A[1] + g.ux * sw], [g.shaftEnd[0] - g.uy * sw, g.shaftEnd[1] + g.ux * sw], [g.shaftEnd[0] + g.uy * sw, g.shaftEnd[1] - g.ux * sw], [g.A[0] + g.uy * sw, g.A[1] - g.ux * sw]];
      return [
        { ring: this.xfRing(quad, t), color: this.color, fill: true, fillOp: 1, sw: 0, cx: (g.A[0] + g.E[0]) / 2 },
        { ring: this.xfRing(g.tri, t), color: this.color, fill: true, fillOp: 1, sw: 0, cx: g.E[0] },
      ];
    }
  }

  // ================================================================== Function compiler
  const _fnCache = new Map();
  function compileFn(src) {
    if (typeof src === 'function') return src;
    if (_fnCache.has(src)) return _fnCache.get(src);
    const body = String(src).replace(/\^/g, '**');
    // eslint-disable-next-line no-new-func
    const f = new Function('x', `const {sin,cos,tan,asin,acos,atan,atan2,exp,sqrt,abs,log,log2,log10,pow,min,max,floor,ceil,round,sign,sinh,cosh,tanh,PI,E}=Math; const pi=PI, e=E, ln=log; return (${body});`);
    _fnCache.set(src, f);
    return f;
  }

  // ================================================================== Shape (graph, circle, polygon, line, curve, rect, arc, tangent, area)
  class Shape extends MV {
    static defaults = { kind: 'graph', color: '#FFFFFF', stroke: 4, fill: null, fill_opacity: null, dashed: false, samples: 240, space: 'plane' };
    static actions = { set: { dur: 1.2, ease: 'smooth' } };
    make() {
      this.keys = [{ at: -Infinity, dur: 0, ease: SM, props: Object.assign({}, this.props) }];
      this.path = svgEl('path', { fill: 'none', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, this.g);
      this.fillEl = svgEl('path', { stroke: 'none' }, this.g);
      this.g.insertBefore(this.fillEl, this.path);
    }
    doLayout() {
      const b = this.localBBox(0);
      this.ax = (b[0] + b[2]) / 2; this.ay = (b[1] + b[3]) / 2;
    }
    usePlane(pp) { return pp.space !== 'screen' && this.plane; }
    pt(v, t, pp) {
      const pl = this.usePlane(pp);
      if (pl) return pl.toScreen(v, t, pp.transform !== false);
      return [v[0] * this.S.W, v[1] * this.S.H];
    }
    ref(v, t, pp) { return Array.isArray(v) ? this.pt(v, t, pp) : resolvePoint(this.S, v, t, this.usePlane(pp)); }
    /** Polyline (screen) for a prop set at time t -> {pts, closed} */
    shapeOf(pp, t) {
      const pl = this.usePlane(pp);
      const kind = pp.kind;
      const n = pp.samples;
      if (kind === 'graph' || kind === 'area') {
        const f = compileFn(pp.fn);
        const xr = pp.x_range || (pl ? [pl.xr[0], pl.xr[1]] : [-5, 5]);
        const pts = [];
        // trim the ends where the curve leaves the axes' y-range (ends at the exact crossing)
        const yc = pp.y_clip || (pl && !pl.fullFrame ? [pl.yr[0], pl.yr[1]] : null);
        const samp = [];
        for (let i = 0; i <= n; i++) { const x = lerp(xr[0], xr[1], i / n), y = f(x); if (isFinite(y)) samp.push([x, y]); }
        let i0 = 0, i1 = samp.length - 1;
        const inside = (q) => !yc || (q[1] >= yc[0] - 1e-9 && q[1] <= yc[1] + 1e-9);
        if (yc) { while (i0 < i1 && !inside(samp[i0])) i0++; while (i1 > i0 && !inside(samp[i1])) i1--; }
        const cross = (a, b) => { const lim = b[1] > yc[1] || a[1] > yc[1] ? yc[1] : yc[0]; const u = (lim - a[1]) / (b[1] - a[1]); return [lerp(a[0], b[0], u), lim]; };
        if (yc && i0 > 0) pts.push(this.pt([...cross(samp[i0], samp[i0 - 1]), 0], t, pp));
        for (let i = i0; i <= i1; i++) pts.push(this.pt([samp[i][0], samp[i][1], 0], t, pp));
        if (yc && i1 < samp.length - 1) pts.push(this.pt([...cross(samp[i1], samp[i1 + 1]), 0], t, pp));
        if (kind === 'area') {
          pts.push(this.pt([xr[1], 0, 0], t, pp), this.pt([xr[0], 0, 0], t, pp));
          return { pts, closed: true };
        }
        return { pts, closed: false };
      }
      if (kind === 'circle' || kind === 'arc') {
        const c = pp.center || [0, 0];
        const a0 = pp.start_angle ?? 0, a1 = kind === 'arc' ? (pp.angle ?? 90) + a0 : a0 + 360;
        const m = Math.max(24, Math.round(n / 2)), pts = [];
        const r = pp.radius ?? 1;
        const cs = Array.isArray(c) ? null : this.ref(c, t, pp);
        for (let i = 0; i <= m; i++) {
          const a = ((a0 + (a1 - a0) * (i / m)) * Math.PI) / 180;
          if (cs) pts.push([cs[0] + r * Math.cos(a) * (pl ? pl.u : 1), cs[1] - r * Math.sin(a) * (pl ? pl.u : 1)]);
          else pts.push(this.pt([c[0] + r * Math.cos(a), c[1] + r * Math.sin(a), 0], t, pp));
        }
        if (kind === 'circle') pts.pop();
        return { pts, closed: kind === 'circle' };
      }
      if (kind === 'polygon') return { pts: pp.points.map((v) => this.ref(v, t, pp)), closed: true };
      if (kind === 'rect') {
        const c = pp.center || [0, 0], w = pp.width ?? 2, h = pp.height ?? 1;
        return { pts: [[c[0] - w / 2, c[1] + h / 2], [c[0] + w / 2, c[1] + h / 2], [c[0] + w / 2, c[1] - h / 2], [c[0] - w / 2, c[1] - h / 2]].map((v) => this.pt(v, t, pp)), closed: true };
      }
      if (kind === 'line') return { pts: [this.ref(pp.from, t, pp), this.ref(pp.to, t, pp)], closed: false };
      if (kind === 'curve') {
        const P = pp.points.map((v) => this.ref(v, t, pp));
        if (P.length < 3) return { pts: P, closed: false };
        const out = [];
        for (let i = 0; i < P.length - 1; i++) {
          const p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(P.length - 1, i + 2)];
          for (let k = 0; k < 16; k++) {
            const s = k / 16, s2 = s * s, s3 = s2 * s;
            out.push([0, 1].map((d) => 0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * s + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * s2 + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * s3)));
          }
        }
        out.push(P[P.length - 1]);
        return { pts: out, closed: !!pp.closed };
      }
      if (kind === 'tangent') {
        const gph = this.S.get(pp.graph);
        const f = compileFn(gph.keys[gph.keys.length - 1].props.fn);
        let x0 = pp.x ?? 0;
        if (pp.dot) { const d = this.S.get(pp.dot); x0 = d.mathPoint('', t)[0]; }
        const h = 1e-4, y0 = f(x0), k = (f(x0 + h) - f(x0 - h)) / (2 * h);
        const len = pp.length ?? 3, dx = len / 2 / Math.hypot(1, k);
        return { pts: [this.pt([x0 - dx, y0 - k * dx, 0], t, pp), this.pt([x0 + dx, y0 + k * dx, 0], t, pp)], closed: false };
      }
      throw new Error(`Shape "${this.id}": unknown kind "${kind}" (graph, area, circle, arc, polygon, rect, line, curve, tangent)`);
    }
    geomAt(t) {
      let k = 0;
      for (let i = 0; i < this.keys.length; i++) if (this.keys[i].at <= t) k = i;
      const key = this.keys[k];
      const cur = this.shapeOf(key.props, t);
      if (k === 0) return cur;
      const p = key.ease(clamp((t - key.at) / key.dur));
      if (p >= 1) return cur;
      const prev = this.shapeOf(this.keys[k - 1].props, t);
      const N = 240;
      const a = resample(prev.pts, N, prev.closed), b = resample(cur.pts, N, cur.closed);
      return { pts: a.map((q, i) => [lerp(q[0], b[i][0], p), lerp(q[1], b[i][1], p)]), closed: cur.closed };
    }
    /** Function value helpers for dots/counters riding this graph. */
    fnAt(t) { let k = 0; for (let i = 0; i < this.keys.length; i++) if (this.keys[i].at <= t) k = i; return compileFn(this.keys[k].props.fn); }
    localBBox(t) {
      const { pts } = this.geomAt(t);
      const b = [Infinity, Infinity, -Infinity, -Infinity];
      for (const q of pts) { b[0] = Math.min(b[0], q[0]); b[1] = Math.min(b[1], q[1]); b[2] = Math.max(b[2], q[0]); b[3] = Math.max(b[3], q[1]); }
      return b[0] === Infinity ? [0, 0, 1, 1] : b;
    }
    a_set(at, dur, e, args) {
      const prev = this.keys[this.keys.length - 1].props;
      const np = Object.assign({}, prev, args);
      delete np.dur; delete np.ease;
      this.keys.push({ at, dur, ease: getEase(e), props: np });
    }
    draw(t, c) {
      const key = this.keys[0].props;
      const { pts, closed } = this.geomAt(t);
      const color = this.col(key.color, C.white);
      const tint = this.tintAt(t);
      const col = tint.amt > 0.001 ? mixColor(color, tint.color, tint.amt) : color;
      const fillCol = this.col(key.fill, null) || (key.kind === 'area' ? color : null);
      const fo = key.fill_opacity ?? (key.kind === 'area' ? 0.35 : 0.5);
      const stroke = key.kind === 'area' ? (key.stroke_area ?? 0) : key.stroke;
      if (key.kind === 'area') {
        // sweep the region in from left to right
        const q = SM(clamp(c));
        const nn = pts.length - 2, m = Math.max(2, Math.round(nn * q));
        const sub = pts.slice(0, m);
        const last = sub[sub.length - 1], first = sub[0];
        const bottom = [[last[0], pts[nn][1]], [first[0], pts[nn + 1][1]]];
        attr(this.fillEl, 'd', q > 0.002 ? polyD(sub.concat(bottom), true) : '');
        attr(this.fillEl, 'fill', fillCol || col); attr(this.fillEl, 'fill-opacity', fo);
        attr(this.path, 'visibility', 'hidden');
        return;
      }
      const L = polyLen(pts, closed);
      const sq = SM(clamp(c / (fillCol ? 0.7 : 1)));
      attr(this.path, 'stroke', col); attr(this.path, 'stroke-width', stroke);
      if (key.dashed) {
        const D = Array.isArray(key.dashed) ? key.dashed.join(' ') : '10 8';
        attr(this.path, 'stroke-dasharray', D);
        const P = closed ? pts.concat([pts[0]]) : pts;
        attr(this.path, 'd', polyD(cutPoly(P, L * sq), false));
        attr(this.path, 'visibility', sq > 0.001 ? 'visible' : 'hidden');
      } else {
        attr(this.path, 'd', polyD(pts, closed));
        if (sq >= 1) { attr(this.path, 'visibility', stroke > 0 ? 'visible' : 'hidden'); attr(this.path, 'stroke-dasharray', 'none'); }
        else drawOn(this.path, sq, L);
      }
      if (fillCol) {
        const fq = SM(clamp((c - 0.55) / 0.45));
        attr(this.fillEl, 'd', fq > 0.001 ? polyD(pts, true) : '');
        attr(this.fillEl, 'fill', fillCol); attr(this.fillEl, 'fill-opacity', (fo * fq).toFixed(3));
      } else attr(this.fillEl, 'd', '');
    }
    worldPaths(t) {
      const key = this.keys[this.keys.length - 1].props;
      const { pts, closed } = this.geomAt(t);
      const ring = closed ? resample(pts, 160, true) : resample(pts, 80, false).concat(resample(pts, 80, false).reverse());
      const fill = !!(key.fill || key.kind === 'area');
      const cx = ring.reduce((s, q) => s + q[0], 0) / ring.length;
      return [{ ring: this.xfRing(ring, t), color: this.col(key.fill || key.color, C.white), fill, fillOp: key.fill_opacity ?? (key.kind === 'area' ? 0.35 : 0.5), sw: key.stroke, cx }];
    }
  }

  // ================================================================== Dot
  class Dot extends MV {
    static defaults = { pos: null, on: null, x: 0, follow: null, color: '#FFFFFF', radius: 10, label: null, label_dir: 'ur', label_size: 40, trace: false, trace_color: null, trace_width: 3, trace_from: null };
    static actions = { move: { dur: 1.0, ease: 'smooth' }, flash: { dur: 0.7, ease: 'out' } };
    make() {
      const p = this.props;
      this.color = this.baseColor(C.white);
      this.posT = new Track(p.pos ? [p.pos[0], p.pos[1], p.pos[2] || 0] : [0, 0, 0]);
      this.xT = new Track(p.x ?? 0);
      this.trail = svgEl('path', { fill: 'none', stroke: this.col(p.trace_color, this.color), 'stroke-width': p.trace_width, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.g);
      this.flashG = svgEl('g', {}, this.g);
      this.flashes2 = [];
      this.dot = svgEl('circle', { r: 0, fill: this.color }, this.g);
    }
    doLayout() {
      const p = this.props;
      if (p.label) { this.labL = layoutTex(this.S, p.label, p.label_size, { color: this.col(p.label_color, this.color) }); this.lab = new GlyphSet(this.g, this.defs, this.labL); }
      const c = this.center(0); this.ax = c[0]; this.ay = c[1];
    }
    mathPoint(anchor, t) {
      const p = this.props;
      if (p.on) { const x = this.xT.value(t); return [x, this.S.get(p.on).fnAt(t)(x), 0]; }
      if (p.follow) return resolveMath(this.S, p.follow, t) || [0, 0, 0];
      return this.posT.value(t);
    }
    /** Values for counters: x, y (=f(x) on a graph), slope (f'(x) on a graph). */
    mathValue(name, t) {
      const m = this.mathPoint('', t);
      if (name === 'slope' && this.props.on) { const f = this.S.get(this.props.on).fnAt(t), h = 1e-4; return (f(m[0] + h) - f(m[0] - h)) / (2 * h); }
      return name === 'y' ? m[1] : name === 'z' ? m[2] : m[0];
    }
    center(t) {
      const p = this.props;
      if (p.follow) return resolvePoint(this.S, p.follow, t, this.plane);
      const pl = this.plane;
      const m = this.mathPoint('', t);
      if (!pl) return [m[0] * this.S.W, m[1] * this.S.H];
      return pl.toScreen(m, t, this.props.transform !== false);
    }
    pointAt(anchor, t) { return anchor === '' || anchor === 'center' ? this.center(t) : super.pointAt(anchor, t); }
    localBBox(t) { const c = this.center(t), r = this.props.radius; return [c[0] - r, c[1] - r, c[0] + r, c[1] + r]; }
    a_move(at, dur, e, args) {
      if (this.props.on && args.x != null) { this.xT.to(at, args.x, dur, e); return; }
      if (args.pos) { this.posT.to(at, [args.pos[0], args.pos[1], args.pos[2] || 0], dur, e); return; }
      super.a_move(at, dur, e, args);
    }
    a_flash(at, dur, e, args) { this.flashes2.push({ at, dur, color: this.col(args.color, C.yellow), els: null }); }
    draw(t, c) {
      const p = this.props;
      const C0 = this.center(t);
      const q = SM(clamp(c / 0.6));
      const tint = this.tintAt(t);
      const col = tint.amt > 0.001 ? mixColor(this.color, tint.color, tint.amt) : this.color;
      attr(this.dot, 'cx', f2(C0[0])); attr(this.dot, 'cy', f2(C0[1]));
      attr(this.dot, 'r', f2(p.radius * q)); attr(this.dot, 'fill', col);
      attr(this.dot, 'visibility', q > 0.001 ? 'visible' : 'hidden');
      // traced path: sampled from trace_from (or entrance) to t; a pure function of t
      if (p.trace) {
        const t0 = p.trace_from ?? this.enterAt ?? 0;
        const pts = [];
        if (t > t0) {
          const n = Math.min(900, Math.ceil((t - t0) * 60));
          for (let i = 0; i <= n; i++) pts.push(this.center(t0 + ((t - t0) * i) / n));
        }
        attr(this.trail, 'd', pts.length > 1 ? polyD(pts, false) : '');
        attr(this.trail, 'stroke-opacity', c > 0 ? 0.9 * Math.min(1, c * 2) : 0);
      }
      for (const f of this.flashes2) {
        const u = (t - f.at) / f.dur;
        if (!f.els) f.els = Array.from({ length: 12 }, () => svgEl('path', { stroke: f.color, 'stroke-width': 3, 'stroke-linecap': 'round', fill: 'none' }, this.flashG));
        const on = u >= 0 && u <= 1;
        f.els.forEach((el, i) => {
          attr(el, 'visibility', on ? 'visible' : 'hidden');
          if (!on) return;
          const a = (i / 12) * Math.PI * 2, r0 = p.radius + 8, r1 = r0 + 46;
          const s1 = lerp(r0, r1, SM(clamp(u / 0.7))), s0 = lerp(r0, r1, SM(clamp((u - 0.3) / 0.7)));
          attr(el, 'd', `M${f2(C0[0] + Math.cos(a) * s0)} ${f2(C0[1] + Math.sin(a) * s0)}L${f2(C0[0] + Math.cos(a) * s1)} ${f2(C0[1] + Math.sin(a) * s1)}`);
        });
      }
      if (this.lab) {
        const L = this.labL, d = DIRS[p.label_dir] || DIRS.ur, r = p.radius + 10;
        const cx = C0[0] + d[0] * (r + L.w / 2 * Math.abs(d[0]) * 1.2), cy = C0[1] + d[1] * (r + L.h / 2 * Math.abs(d[1]) * 1.2);
        this.lab.place(cx - L.w / 2, cy - L.h / 2);
        this.lab.write(clamp((c - 0.4) / 0.6));
      }
    }
    worldPaths(t) {
      const c = this.center(t), r = this.props.radius, ring = [];
      for (let i = 0; i < 40; i++) { const a = (i / 40) * Math.PI * 2; ring.push([c[0] + r * Math.cos(a), c[1] + r * Math.sin(a)]); }
      return [{ ring: this.xfRing(ring, t), color: this.color, fill: true, fillOp: 1, sw: 0, cx: c[0] }];
    }
  }

  // ================================================================== DashedProjection
  class DashedProjection extends MV {
    static defaults = { from: null, to: 'both', color: '#FFFFFF', opacity: 0.8, stroke: 2.5, dash: [9, 7] };
    make() {
      const p = this.props;
      this.els = [0, 1].map(() => svgEl('path', { fill: 'none', stroke: this.col(p.color, C.white), 'stroke-width': p.stroke, 'stroke-opacity': p.opacity, 'stroke-dasharray': p.dash.join(' '), 'stroke-linecap': 'butt' }, this.g));
    }
    doLayout() { const b = this.localBBox(0); this.ax = (b[0] + b[2]) / 2; this.ay = (b[1] + b[3]) / 2; }
    segs(t) {
      const p = this.props, S = this.S, pl = this.plane;
      const A = resolvePoint(S, p.from, t, pl);
      if (Array.isArray(p.to) || (typeof p.to === 'string' && !['x', 'y', 'both'].includes(p.to))) return [[A, resolvePoint(S, p.to, t, pl)]];
      const m = resolveMath(S, p.from, t);
      if (!m || !pl) throw new Error(`DashedProjection "${this.id}": "from" must be on a plane to project onto an axis`);
      const src = this.S.get(String(p.from).split('.')[0]);
      const apply = !(src && src.props && src.props.transform === false);
      const out = [];
      if (p.to === 'x' || p.to === 'both') out.push([A, pl.toScreen([m[0], 0, 0], t, apply)]);
      if (p.to === 'y' || p.to === 'both') out.push([A, pl.toScreen([0, m[1], 0], t, apply)]);
      return out;
    }
    localBBox(t) {
      const b = [Infinity, Infinity, -Infinity, -Infinity];
      for (const s of this.segs(t)) for (const q of s) { b[0] = Math.min(b[0], q[0]); b[1] = Math.min(b[1], q[1]); b[2] = Math.max(b[2], q[0]); b[3] = Math.max(b[3], q[1]); }
      return b;
    }
    draw(t, c) {
      const q = SM(clamp(c));
      const segs = this.segs(t);
      this.els.forEach((el, i) => {
        const s = segs[i];
        if (!s || q <= 0.001) { attr(el, 'visibility', 'hidden'); return; }
        const [A, B] = s;
        attr(el, 'visibility', 'visible');
        attr(el, 'd', `M${f2(A[0])} ${f2(A[1])}L${f2(lerp(A[0], B[0], q))} ${f2(lerp(A[1], B[1], q))}`);
      });
    }
  }

  // ================================================================== Brace
  /** Tapered curly brace outline from P0 to P1 bulging along normal n (unit). */
  function braceGeom(P0, P1, n, depth) {
    const L = Math.hypot(P1[0] - P0[0], P1[1] - P0[1]) || 1e-6;
    const ux = (P1[0] - P0[0]) / L, uy = (P1[1] - P0[1]) / L;
    const h = Math.min(depth, Math.max(8, L * 0.35)), r = h / 2;
    const at = (s, d) => [P0[0] + ux * s + n[0] * d, P0[1] + uy * s + n[1] * d];
    // centerline: curl at ends, straight shoulders, sharp middle tip
    const cl = [];
    const quad = (a, b, c, k) => { for (let i = 1; i <= k; i++) { const s = i / k, u = 1 - s; cl.push([u * u * a[0] + 2 * u * s * b[0] + s * s * c[0], u * u * a[1] + 2 * u * s * b[1] + s * s * c[1]]); } };
    const M = L / 2, rr = Math.min(r, L / 4);
    cl.push([0, 0]);
    quad([0, 0], [0, rr], [rr, rr], 10);
    cl.push([M - rr, rr]);
    quad([M - rr, rr], [M, rr], [M, 2 * rr], 10);
    const half = cl.length;
    quad([M, 2 * rr], [M, rr], [M + rr, rr], 10);
    cl.push([L - rr, rr]);
    quad([L - rr, rr], [L, rr], [L, 0], 10);
    // densify the straight shoulders so thickness tapers smoothly
    const dense = [];
    for (let i = 0; i < cl.length; i++) {
      if (i > 0) { const a = cl[i - 1], b = cl[i], d = Math.hypot(b[0] - a[0], b[1] - a[1]); const k = Math.ceil(d / 6); for (let j = 1; j < k; j++) dense.push([lerp(a[0], b[0], j / k), lerp(a[1], b[1], j / k), i]); }
      dense.push([cl[i][0], cl[i][1], i]);
    }
    const thick = Math.max(2.2, h * 0.3);
    const W = (s) => { const x = s / L; const e = Math.min(x, 1 - x) * 2; return thick * (0.25 + 0.75 * Math.pow(Math.sin(Math.PI * Math.min(1, e * 1.1) / 2), 0.6)); };
    const top = [], bot = [];
    for (let i = 0; i < dense.length; i++) {
      const a = dense[Math.max(0, i - 1)], b = dense[Math.min(dense.length - 1, i + 1)];
      let tx = b[0] - a[0], ty = b[1] - a[1]; const tl = Math.hypot(tx, ty) || 1; tx /= tl; ty /= tl;
      const w = W(dense[i][0]) / 2;
      top.push([dense[i][0] - ty * w, dense[i][1] + tx * w]);
      bot.push([dense[i][0] + ty * w, dense[i][1] - tx * w]);
    }
    const outline = top.concat(bot.reverse()).map(([s, d]) => at(s, d));
    const center = dense.map(([s, d]) => at(s, d));
    const midIdx = dense.findIndex((q) => q[2] >= half - 1 && Math.abs(q[0] - M) < 1e-6);
    return { outline, center, mid: midIdx < 0 ? Math.floor(center.length / 2) : midIdx, tip: at(M, 2 * rr), h: 2 * rr };
  }
  class Brace extends MV {
    static defaults = { from: null, to: null, target: null, part: null, side: null, label: null, label_size: 44, color: '#FFFFFF', buff: 12, depth: 26, label_buff: 12 };
    make() {
      const p = this.props;
      this.color = this.baseColor(C.white);
      this.fillEl = svgEl('path', { fill: this.color, stroke: 'none' }, this.g);
      this.strokes = [0, 1].map(() => svgEl('path', { fill: 'none', stroke: this.color, 'stroke-width': 3.2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.g));
    }
    doLayout() {
      const p = this.props;
      if (p.label) { this.labL = layoutTex(this.S, p.label, p.label_size, { color: this.col(p.label_color, this.color), colors: p.label_colors }); this.lab = new GlyphSet(this.g, this.defs, this.labL); }
      const g = this.geom(0);
      this.ax = g.tip[0]; this.ay = g.tip[1];
    }
    ends(t) {
      const p = this.props, S = this.S, pl = this.plane;
      if (p.target) {
        const e = S.get(p.target);
        e.layout && e.layout();
        const b = e.bbox(t, p.part);
        const side = p.side || 'down';
        if (side === 'down') return { A: [b[0], b[3]], B: [b[2], b[3]], n: [0, 1] };
        if (side === 'up') return { A: [b[0], b[1]], B: [b[2], b[1]], n: [0, -1] };
        if (side === 'left') return { A: [b[0], b[1]], B: [b[0], b[3]], n: [-1, 0] };
        return { A: [b[2], b[1]], B: [b[2], b[3]], n: [1, 0] };
      }
      const A = resolvePoint(S, p.from, t, pl), B = resolvePoint(S, p.to, t, pl);
      const dx = B[0] - A[0], dy = B[1] - A[1];
      const L = Math.hypot(dx, dy) || 1e-6;
      let n = [-dy / L, dx / L];
      const side = p.side || (Math.abs(dx) >= Math.abs(dy) ? 'down' : 'right');
      const want = DIRS[side] || DIRS.down;
      if (n[0] * want[0] + n[1] * want[1] < 0) n = [-n[0], -n[1]];
      return { A, B, n };
    }
    geom(t) {
      const { A, B, n } = this.ends(t);
      const b = this.props.buff;
      return braceGeom([A[0] + n[0] * b, A[1] + n[1] * b], [B[0] + n[0] * b, B[1] + n[1] * b], n, this.props.depth);
    }
    localBBox(t) {
      const g = this.geom(t);
      const b = [Infinity, Infinity, -Infinity, -Infinity];
      for (const q of g.outline) { b[0] = Math.min(b[0], q[0]); b[1] = Math.min(b[1], q[1]); b[2] = Math.max(b[2], q[0]); b[3] = Math.max(b[3], q[1]); }
      return b;
    }
    labelCenter(t) {
      const { n } = this.ends(t), g = this.geom(t), L = this.labL;
      const r = Math.abs(n[0]) * L.w / 2 + Math.abs(n[1]) * L.h / 2 + this.props.label_buff;
      return [g.tip[0] + n[0] * r, g.tip[1] + n[1] * r];
    }
    pointAt(anchor, t) {
      if (anchor === 'label' && this.lab) return this.labelCenter(t);
      if (anchor === 'tip' || anchor === '') return this.geom(t).tip;
      return super.pointAt(anchor, t);
    }
    draw(t, c) {
      const g = this.geom(t);
      const tint = this.tintAt(t);
      const col = tint.amt > 0.001 ? mixColor(this.color, tint.color, tint.amt) : this.color;
      // grow from the middle tip outwards (stroke), then fill the tapered shape
      const sq = SM(clamp(c / 0.55));
      const fq = SM(clamp((c - 0.35) / 0.4));
      const halves = [g.center.slice(0, g.mid + 1).reverse(), g.center.slice(g.mid)];
      this.strokes.forEach((el, i) => {
        const pts = halves[i];
        const L = polyLen(pts, false);
        attr(el, 'stroke', col);
        attr(el, 'd', polyD(cutPoly(pts, L * sq), false));
        attr(el, 'visibility', sq > 0.001 && fq < 1 ? 'visible' : 'hidden');
        attr(el, 'stroke-opacity', (1 - fq).toFixed(3));
      });
      attr(this.fillEl, 'd', fq > 0.001 ? polyD(g.outline, true) : '');
      attr(this.fillEl, 'fill', col);
      attr(this.fillEl, 'fill-opacity', fq.toFixed(3));
      if (this.lab) {
        const lc = this.labelCenter(t);
        this.lab.place(lc[0] - this.labL.w / 2, lc[1] - this.labL.h / 2);
        this.lab.write(clamp((c - 0.45) / 0.55), (it) => (tint.amt > 0.001 ? mixColor(it.color, tint.color, tint.amt) : it.color));
      }
    }
    worldPaths(t) {
      const g = this.geom(t);
      return [{ ring: this.xfRing(g.outline, t), color: this.color, fill: true, fillOp: 1, sw: 0, cx: g.tip[0] }];
    }
  }

  // ================================================================== NumberCounter (DecimalNumber)
  class NumberCounter extends MV {
    static layer = 'text';
    static defaults = { value: 0, decimals: 2, prefix: '', suffix: '', color: '#FFFFFF', size: 48, anchor: 'center', track: null, follow: null, offset: [0, 0], side: 'ur', show_sign: false };
    static actions = { set: { dur: 1.0, ease: 'smooth' } };
    make() {
      LOOK_BASE = this.S.look.base || LOOK_BASE;
      const p = this.props;
      this.color = this.baseColor(C.white);
      this.valT = new Track(+p.value || 0);
      this.font = fontData('Main-Regular');
      this.numG = svgEl('g', {}, this.g);
      this.pool = [];
    }
    autoDur() { return 0.9; }
    doLayout() {
      const p = this.props;
      const opt = { color: this.color, colors: p.colors };
      this.preL = p.prefix ? layoutTex(this.S, p.prefix, p.size, opt) : null;
      this.sufL = p.suffix ? layoutTex(this.S, p.suffix, p.size, opt) : null;
      if (this.preL) this.pre = new GlyphSet(this.g, this.defs, this.preL);
      if (this.sufL) this.suf = new GlyphSet(this.g, this.defs, this.sufL);
      this.gsc = p.size / this.font.upm;
      this.asc = 0.69 * p.size; // digit height (Computer Modern digits ~0.644em) + margin
      const w0 = this.totalW(this.valueAt(0));
      const h0 = Math.max(this.preL ? this.preL.h : 0, this.asc);
      if (!p.follow) {
        const [cx, cy] = this.placeAnchor(w0, h0);
        this.ax = cx; this.ay = cy;
        this.left = cx - w0 / 2;
        // anchor "eq": x is where the prefix ends (stack counters with their '=' signs aligned)
        if (p.anchor === 'eq' && this.preL) this.left = cx - this.preL.w;
        else if (p.anchor === 'left') this.left = cx;
      }
    }
    valueAt(t) {
      const tr = this.props.track;
      if (tr) {
        const [id, name] = typeof tr === 'string' ? tr.split('.') : [tr.target, tr.value];
        return this.S.get(id).mathValue(name || 'x', t);
      }
      return this.valT.value(t);
    }
    str(v) {
      const p = this.props;
      const d = p.decimals;
      let s = Math.abs(v).toFixed(d);
      if (+s === 0) v = 0;
      return (v < 0 ? '\u2212' : p.show_sign ? '+' : '') + s;
    }
    numW(s) { let w = 0; for (const ch of s) { const g = this.font.g[ch.codePointAt(0)]; w += (g ? g[0] : 500) * this.gsc; } return w; }
    totalW(v) { const gap = this.props.size * 0.3; return (this.preL ? this.preL.w + gap : 0) + this.numW(this.str(v)) + (this.sufL ? this.sufL.w + gap : 0); }
    baseline() { return this.preL ? this.preL.bl : this.asc; }
    origin(t) {
      const p = this.props;
      if (p.follow) {
        const pt = resolvePoint(this.S, p.follow, t, this.plane);
        const d = DIRS[p.side] || DIRS.ur;
        const w = this.totalW(this.valueAt(t)), h = Math.max(this.preL ? this.preL.h : 0, this.asc);
        const r = 20;
        const cx = pt[0] + d[0] * (r + w / 2) + (p.offset[0] || 0), cy = pt[1] + d[1] * (r + h / 2) + (p.offset[1] || 0);
        return [cx - w / 2, cy - h / 2];
      }
      const h = Math.max(this.preL ? this.preL.h : 0, this.asc);
      return [this.left, this.ay - h / 2];
    }
    localBBox(t) {
      const o = this.origin(t), w = this.totalW(this.valueAt(t)), h = Math.max(this.preL ? this.preL.h : 0, this.asc);
      return [o[0], o[1], o[0] + w, o[1] + h];
    }
    a_set(at, dur, e, args) { this.valT.to(at, +args.value, dur, e); }
    draw(t, c) {
      const p = this.props;
      const o = this.origin(t);
      const tint = this.tintAt(t);
      const col = tint.amt > 0.001 ? mixColor(this.color, tint.color, tint.amt) : this.color;
      const cf = (it) => (tint.amt > 0.001 ? mixColor(it.color, tint.color, tint.amt) : it.color);
      const gap = p.size * 0.3;
      const bl = this.baseline();
      let x = o[0];
      if (this.pre) { this.pre.place(x, o[1] + bl - this.preL.bl); this.pre.write(clamp(c / 0.8), cf); x += this.preL.w + gap; }
      const s = this.str(this.valueAt(t));
      const chars = Array.from(s);
      while (this.pool.length < chars.length) this.pool.push({ el: svgEl('path', { 'stroke-linejoin': 'round', 'stroke-width': Math.max(1.1, p.size * 0.028) }, this.numG), it: { kind: 'g', color: this.color } });
      const nq = clamp((c - 0.2) / 0.8);
      this.pool.forEach((en, i) => {
        if (i >= chars.length) { attr(en.el, 'visibility', 'hidden'); return; }
        const g = this.font.g[chars[i].codePointAt(0)];
        if (!g) { attr(en.el, 'visibility', 'hidden'); return; }
        const d = tfD(g[1], this.gsc, this.gsc, x, o[1] + bl);
        if (en._d !== d) { en._d = d; attr(en.el, 'd', d); en.el._caLen = null; }
        const [st, w] = lagWindow(i, chars.length);
        writeItem(en, nq >= 1 ? 1 : clamp((nq - st) / w), col);
        x += g[0] * this.gsc;
      });
      if (this.suf) { this.suf.place(x + gap, o[1] + bl - this.sufL.bl); this.suf.write(clamp((c - 0.2) / 0.8), cf); }
    }
  }

  // ================================================================== Morph (element form of the morph action)
  class Morph extends MV {
    static autoEnter = false;
    static defaults = { from: null, to: null };
    static actions = { play: { dur: 1.4, ease: 'smooth' } };
    a_play(at, dur, e, args) { this.S.get(this.props.from).a_morph(at, dur, e, Object.assign({}, args, { to: this.props.to })); }
    a_enter(at, dur, e, args) { this.a_play(at, args.dur ?? 1.4, 'smooth', args); }
  }

  window.MV = { layoutTex, fontData };
  register('NumberPlane', NumberPlane);
  register('Axes', Axes);
  register('Tex', Tex);
  register('MathTex', Tex);
  register('Label', Label);
  register('Title', Title);
  register('Matrix', Matrix);
  register('Vector', Vector);
  register('Arrow', Vector);
  register('Shape', Shape);
  register('Dot', Dot);
  register('DashedProjection', DashedProjection);
  register('Brace', Brace);
  register('NumberCounter', NumberCounter);
  register('Counter', NumberCounter);
  register('Morph', Morph);

  // ================================================================== layout
  registerLayout('math-vector', (S) => {
    LOOK_BASE = S.look.base || LOOK_BASE;
    S._mvPlane = S.list.find((e) => e instanceof NumberPlane) || null;
    // morph targets appear through the morph: never auto-enter them
    for (const b of S.spec.beats || []) {
      if (b.action === 'morph' && b.args && b.args.to && S.has(b.args.to)) S.get(b.args.to).props.auto = false;
      // write/create are entrances too: an element entered by them must not also auto-enter
      if (b.action === 'write' || b.action === 'create') for (const id of [].concat(b.target)) if (S.has(id)) S.get(id).props.auto = false;
    }
    for (const e of S.list) if (e instanceof Morph && S.has(e.props.to)) S.get(e.props.to).props.auto = false;
    if (S._mvPlane) S._mvPlane.layout();
    for (const e of S.list) if (e.layout) e.layout();
  });
})();
