/* stickman-story Look: Primitives (Scene, Walkthrough). Scene vocabulary is documented in PRIMITIVES.md.
 *
 * Everything is compiled from Beats into tracks/event lists at build time; render(t) is a pure
 * function of t. Ambient loops (blinks, typing, scrolling, steam, boiling stress scribbles) are
 * computed from t with seeded noise, never from a clock.
 *
 * Drawing rules: uniform 5 px black ink (#000000) on white, round caps/joins, no shading. Shapes
 * that must hide what is behind them (head, torso, hands, props) are filled with paper white.
 */
(function () {
  'use strict';
  const {
    Primitive, Track, Events, register, registerLayout,
    el, svgEl, css, attr, clamp, lerp, prog, bump, getEase, noise, rng, hashStr,
    splitWords, revealWords,
  } = window.CA;

  const INK = '#000000', PAPER = '#FFFFFF', TXT = '#111111';
  const SW = 5; // ink width in design px (after the composition scale)
  const D2R = Math.PI / 180;
  const n1 = (v) => (Math.round(v * 10) / 10).toString();
  const pt = (p) => `${n1(p[0])},${n1(p[1])}`;
  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const ICONS = () => window.STICK_ICONS || {};

  // ------------------------------------------------------------------ async assets (images)
  // seek() may return a Promise (Contract 2). Images are decoded asynchronously, so the first seek
  // after build waits for them, then renders again. Wrapping keeps _runtime untouched.
  const pendingAssets = [];
  (function wrapSeek() {
    const api = window.clipagent;
    if (!api || api._stickWrapped) return;
    const orig = api.seek;
    api._stickWrapped = true;
    api.seek = function (t) {
      orig.call(api, t);
      if (!pendingAssets.length) return undefined;
      const ps = pendingAssets.splice(0);
      return Promise.all(ps).then(() => { orig.call(api, t); });
    };
  })();
  function specUrl() {
    const q = new URLSearchParams(location.search).get('spec');
    return new URL(q || '.', location.href);
  }
  function lookUrl(scene) { return scene.look.base || new URL(`../${scene.spec.look}/`, location.href).href; }
  function resolveSrc(scene, src) {
    if (!src) return '';
    if (/^(data:|https?:|blob:)/.test(src)) return src;
    if (src.startsWith('look:')) return new URL(src.slice(5), lookUrl(scene)).href;
    return new URL(src, specUrl()).href;
  }
  function loadImg(imgEl, src) {
    imgEl.src = src;
    pendingAssets.push(imgEl.decode().catch(() => null));
  }

  // ------------------------------------------------------------------ text measuring
  let _mctx = null;
  function textWidth(str, font) {
    if (!_mctx) _mctx = document.createElement('canvas').getContext('2d');
    _mctx.font = font;
    return _mctx.measureText(str).width;
  }
  const HAND = "'Patrick Hand', 'Comic Sans MS', cursive";

  // ------------------------------------------------------------------ 3/4 projection (desk props)
  // World: X right, Y up, Z toward the viewer. Seen from slightly above. ZC = character plane.
  const ZC = 60, KY = 0.94, KZ = 0.34;
  const P3 = (X, Y, Z) => [X, -KY * Y + KZ * (Z - ZC)];

  // ------------------------------------------------------------------ shapes
  function poly(pts, close = true) { return 'M' + pts.map(pt).join('L') + (close ? 'Z' : ''); }
  /** Thought-bubble cloud: bumps around an ellipse. */
  function cloudPath(cx, cy, rx, ry, n = 9, seed = 1) {
    const r = rng(seed);
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + 0.2 + (r() - 0.5) * 0.18;
      pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
    }
    let d = `M${pt(pts[0])}`;
    for (let i = 0; i < n; i++) {
      const a = pts[i], b = pts[(i + 1) % n];
      const ch = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const rr = ch * (0.56 + r() * 0.08);
      d += `A${n1(rr)},${n1(rr)} 0 0 1 ${pt(b)}`;
    }
    return d + 'Z';
  }
  /** Scribble stress cloud: a tangled loop; `i` re-seeds it (boiling animation). */
  function scribblePath(cx, cy, w, h, i) {
    const r = rng(9157 + i * 31);
    const loops = 7, steps = loops * 14;
    const pts = [];
    for (let k = 0; k <= steps; k++) {
      const u = k / steps;
      const a = u * loops * Math.PI * 2;
      const drift = (u - 0.5) * w * 0.55;
      const rx = w * (0.2 + 0.07 * Math.sin(u * 9 + i)), ry = h * (0.34 + 0.08 * Math.cos(u * 7 + i));
      pts.push([cx + drift + Math.cos(a) * rx + (r() - 0.5) * 5, cy + Math.sin(a) * ry + (r() - 0.5) * 5]);
    }
    let d = `M${pt(pts[0])}`;
    for (let k = 1; k < pts.length - 1; k += 2) d += `Q${pt(pts[k])} ${pt(pts[k + 1])}`;
    return d;
  }
  function teardrop(x, y, s) {
    return `M${n1(x)},${n1(y - 15 * s)}C${n1(x + 6 * s)},${n1(y - 5 * s)} ${n1(x + 10 * s)},${n1(y)} ${n1(x + 10 * s)},${n1(y + 5 * s)}` +
      `A${n1(10 * s)},${n1(10 * s)} 0 1 1 ${n1(x - 10 * s)},${n1(y + 5 * s)}C${n1(x - 10 * s)},${n1(y)} ${n1(x - 6 * s)},${n1(y - 5 * s)} ${n1(x)},${n1(y - 15 * s)}Z`;
  }
  function sparkPath(x, y, r) {
    const k = r * 0.22;
    return `M${n1(x)},${n1(y - r)}Q${n1(x + k)},${n1(y - k)} ${n1(x + r)},${n1(y)}Q${n1(x + k)},${n1(y + k)} ${n1(x)},${n1(y + r)}` +
      `Q${n1(x - k)},${n1(y + k)} ${n1(x - r)},${n1(y)}Q${n1(x - k)},${n1(y - k)} ${n1(x)},${n1(y - r)}Z`;
  }
  /** Lucide icon (24 grid) as an SVG group scaled to `size`, ink width kept at SW. */
  function iconGroup(parent, name, x, y, size, inkScale) {
    const inner = ICONS()[name];
    if (!inner) return null;
    const k = size / 24;
    const g = svgEl('g', { transform: `translate(${n1(x - size / 2)},${n1(y - size / 2)}) scale(${k.toFixed(4)})`, fill: 'none', stroke: INK, 'stroke-width': (SW / inkScale / k).toFixed(3) }, parent);
    g.innerHTML = inner;
    return g;
  }

  // ------------------------------------------------------------------ face & pose tables
  // brows: [Linner, Louter, Larch, Rinner, Router, Rarch] offsets (down +). L/R = screen left/right.
  // mouth: [width, cornerL up, cornerR up, upper-lip ctrl y, lower-lip ctrl y, wobble]
  const MOODS = {
    neutral: { brows: [0, 0, 3, 0, 0, 3], mouth: [28, 4, 4, 4, 4, 0], eye: 1, wide: 1 },
    happy: { brows: [-5, -4, 5, -5, -4, 5], mouth: [44, 10, 10, 3, 24, 0], eye: 0.92, wide: 1 },
    smile: { brows: [-2, -2, 4, -2, -2, 4], mouth: [36, 8, 8, 8, 8, 0], eye: 1, wide: 1 },
    confident: { brows: [3, -3, 3, -8, -11, 6], mouth: [34, 2, 11, 6, 6, 0], eye: 0.86, wide: 1 },
    stressed: { brows: [-10, 5, 1, -10, 5, 1], mouth: [34, -2, -2, -2, -2, 3.2], eye: 1, wide: 1.06 },
    sad: { brows: [-9, 5, 0, -9, 5, 0], mouth: [28, -7, -7, -8, -8, 0], eye: 0.9, wide: 1 },
    surprised: { brows: [-15, -12, 6, -15, -12, 6], mouth: [20, 0, 0, -13, 13, 0], eye: 1, wide: 1.14 },
    angry: { brows: [9, -6, 0, 9, -6, 0], mouth: [30, -5, -5, -3, -3, 0], eye: 0.8, wide: 1 },
    sleepy: { brows: [3, 4, 1, 3, 4, 1], mouth: [16, 0, 0, -2, 5, 0], eye: 0.32, wide: 1 },
    focused: { brows: [5, -1, 1, 5, -1, 1], mouth: [24, 0, 0, 0, 0, 0], eye: 0.84, wide: 1 },
    thinking: { brows: [-3, -6, 4, 4, 1, 1], mouth: [22, -2, 3, 1, 1, 0], eye: 1, wide: 1 },
  };
  const MOUTHS = {
    smile: [36, 8, 8, 8, 8, 0], grin: [44, 10, 10, 3, 24, 0], frown: [28, -7, -7, -8, -8, 0],
    open: [28, 3, 3, -6, 16, 0], o: [20, 0, 0, -13, 13, 0], flat: [26, 0, 0, 0, 0, 0],
    smirk: [34, 2, 11, 6, 6, 0], wobble: [34, -2, -2, -2, -2, 3.2], small: [18, 2, 2, 2, 2, 0],
    neutral: [28, 4, 4, 4, 4, 0],
  };
  const BROWS = {
    neutral: MOODS.neutral.brows, stressed: MOODS.stressed.brows, worried: MOODS.stressed.brows,
    confident: MOODS.confident.brows, raised: MOODS.surprised.brows, angry: MOODS.angry.brows,
    sad: MOODS.sad.brows, focused: MOODS.focused.brows, happy: MOODS.happy.brows,
  };
  const LOOP_POSES = { type: 'type', scroll: 'scroll', wave: 'wave', victory: 'victory', clap: 'clap' };

  // rig dimensions (local units; the scene scales the whole composition)
  const R = { head: 60, torsoW: 64, torsoH: 150, thigh: 82, shin: 84, upper: 76, fore: 72, hand: 11 };

  // ------------------------------------------------------------------ Rig
  /** The stickman. One instance per Scene; all layers animate independently from tracks. */
  class Rig {
    constructor(owner, parent, o) {
      this.owner = owner;
      this.seed = hashStr(owner.id);
      this.sit = o.pose === 'sit';
      this.dir = o.dir; // -1 facing left, 0 front, 1 facing right
      this.inkScale = o.inkScale || 1;
      this.targets = o.targets || {};
      // skeleton anchors
      if (this.sit) {
        this.seatY = -84;
        this.hip = [0, this.seatY - 12];
        this.torsoBot = this.seatY - 3;
      } else {
        this.hip = [0, -(R.thigh + R.shin) + 2];
        this.torsoBot = this.hip[1] + 12;
      }
      this.torsoTop = this.torsoBot - R.torsoH;
      this.headC = [0, this.torsoTop - R.head + 8];
      this.neck = [0, this.torsoTop + 6];
      this.shoulder = { L: [-R.torsoW / 2 + 1, this.torsoTop + 30], R: [R.torsoW / 2 - 1, this.torsoTop + 30] };
      // in a 3/4 view the far arm attaches a little behind the torso (used when that arm is drawn behind it)
      this.shoulderBack = {};
      for (const sd of ['L', 'R']) this.shoulderBack[sd] = [this.shoulder[sd][0] + (this.dir || 0) * 10, this.shoulder[sd][1] - 4];
      // tracks
      const mood = MOODS[o.mood] || MOODS.neutral;
      this.faceT = new Track(this.dir * 0.62);
      this.lookT = new Track(this.lookVec(o.look, o));
      this.browsT = new Track(mood.brows.slice());
      this.mouthT = new Track(mood.mouth.slice());
      this.eyeT = new Track(mood.eye);
      this.wideT = new Track(mood.wide);
      this.tiltT = new Track(0);
      this.nods = []; // {at, dur, times, kind: 'nod'|'shake'}
      this.blinks = [];
      this.talks = []; // {at, dur}
      this.presses = []; // {at, dur}
      const pose0 = this.poseAngles(o.arms || 'rest', o.armsArgs || {});
      this.armsT = new Track(pose0.angles);
      this.hands = new Events().add(-1e9, { L: pose0.L, R: pose0.R, back: pose0.back, kind: o.arms || 'rest' });
      this.loopAmp = {};
      for (const k of ['type', 'scroll', 'wave', 'victory', 'clap']) this.loopAmp[k] = new Track(LOOP_POSES[o.arms] === k ? 1 : 0);
      this.typeStarts = new Events();
      if (o.arms === 'type') this.typeStarts.add(-1e9, { on: true });
      this.pose0 = pose0;
      this.build(parent);
    }

    // ---------- geometry helpers
    lookVec(v, o = {}) {
      if (Array.isArray(v)) return [clamp(+v[0], -1, 1), clamp(+v[1], -1, 1)];
      const d = this.dir || 1;
      const T = this.targets;
      const toward = (p) => {
        if (!p) return [d * 0.8, 0.1];
        const h = this.headC;
        const dx = p[0] - h[0], dy = p[1] - h[1];
        const L = Math.hypot(dx, dy) || 1;
        return [clamp((dx / L) * 1.15, -1, 1), clamp((dy / L) * 1.1, -1, 1)];
      };
      switch (v) {
        case 'left': return [-1, 0];
        case 'right': return [1, 0];
        case 'up': return [0, -1];
        case 'down': return [0, 0.9];
        case 'up-left': return [-0.75, -0.75];
        case 'up-right': return [0.75, -0.75];
        case 'down-left': return [-0.75, 0.7];
        case 'down-right': return [0.75, 0.7];
        case 'camera': case 'center': case 'front': case 'viewer': return [0, 0];
        case 'phone': return [d * 0.35, 0.95];
        case 'screen': case 'laptop': case 'monitor': return toward(T.screen || T.prop);
        case 'prop': return toward(T.prop);
        case undefined: case null: case '':
          if (this.sit && T.screen) return toward(T.screen);
          return [this.dir * 0.35, 0];
        default:
          if (T[v]) return toward(T[v]);
          return [0, 0];
      }
    }
    /** 2-bone IK. Returns [a1, a2] in degrees (0 = straight down, + toward screen right). */
    ik(S, T, prefer) {
      const L1 = R.upper, L2 = R.fore;
      let dx = T[0] - S[0], dy = T[1] - S[1];
      let d = Math.hypot(dx, dy);
      const maxd = L1 + L2 - 0.5, mind = Math.abs(L1 - L2) + 6;
      if (d > maxd) { dx *= maxd / d; dy *= maxd / d; d = maxd; }
      if (d < mind) { const k = mind / (d || 1); dx *= k; dy *= k; d = mind; }
      const base = Math.atan2(dx, dy) / D2R;
      const alpha = Math.acos(clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1, 1)) / D2R;
      const beta = Math.acos(clamp((L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2), -1, 1)) / D2R;
      const sols = [1, -1].map((s) => {
        const a1 = base + s * alpha, a2 = -s * (180 - beta);
        const e = [S[0] + L1 * Math.sin(a1 * D2R), S[1] + L1 * Math.cos(a1 * D2R)];
        return { a: [a1, a2], e };
      });
      let pick;
      if (prefer === 'out') pick = Math.abs(sols[0].e[0]) >= Math.abs(sols[1].e[0]) ? sols[0] : sols[1];
      else if (prefer === 'in') pick = Math.abs(sols[0].e[0]) <= Math.abs(sols[1].e[0]) ? sols[0] : sols[1];
      else pick = sols[0].e[1] >= sols[1].e[1] ? sols[0] : sols[1]; // elbow down
      return pick.a;
    }
    straightAt(S, T) { return [Math.atan2(T[0] - S[0], T[1] - S[1]) / D2R, 0]; }
    resolveTarget(v, item) {
      const T = this.targets;
      if (item != null && T.items && T.items[item]) { const q = T.items[item]; return [q[0] - (q[0] > this.headC[0] ? 36 : -36), q[1]]; }
      if (Array.isArray(v)) return [+v[0], +v[1]];
      if (typeof v === 'string' && T[v]) return T[v];
      const h = this.headC, d = this.dir || 1;
      switch (v) {
        case 'left': return [h[0] - 300, h[1] + 40];
        case 'right': return [h[0] + 300, h[1] + 40];
        case 'up': return [h[0] + d * 120, h[1] - 300];
        case 'up-left': return [h[0] - 250, h[1] - 220];
        case 'up-right': return [h[0] + 250, h[1] - 220];
        case 'viewer': case 'camera': return [h[0] + d * 140, h[1] + 120];
        default: return T.prop || [h[0] + d * 300, h[1] + 40];
      }
    }
    /** Pose -> arm angles [La1, La2, Ra1, Ra2], hand shapes and which arm is behind the torso. */
    poseAngles(pose, args) {
      const reach = ['type', 'scroll', 'phone'].includes(pose) || (pose === 'rest' && this.dir);
      const backSide = this.dir > 0 ? 'L' : this.dir < 0 ? 'R' : null;
      const S = Object.assign({}, this.shoulder);
      if (reach && backSide) S[backSide] = this.shoulderBack[backSide];
      const d = this.dir || 1;
      const rest = { L: [-17, 9], R: [17, -9] };
      let L = rest.L, Rr = rest.R, hL = 'open', hR = 'open';
      const back = backSide;
      const side = (p) => (p[0] >= 0 ? 'R' : 'L');
      const hipPt = (s) => [s === 'L' ? -R.torsoW / 2 - 4 : R.torsoW / 2 + 4, this.torsoBot - 26];
      switch (pose) {
        case 'rest': case 'down': break;
        case 'hips': L = this.ik(S.L, hipPt('L'), 'out'); Rr = this.ik(S.R, hipPt('R'), 'out'); break;
        case 'victory': L = [-126, -26]; Rr = [126, 26]; hL = hR = 'fist'; break;
        case 'wave': {
          if (d > 0 || this.dir === 0) { Rr = [132, 30]; } else { L = [-132, -30]; }
          break;
        }
        case 'shrug': L = [-52, -84]; Rr = [52, 84]; break;
        case 'think': {
          // elbow out and down, fist resting just under the chin
          if (d >= 0) { Rr = [40, -194]; hR = 'fist'; } else { L = [-40, 194]; hL = 'fist'; }
          break;
        }
        case 'facepalm': {
          const fh = [this.headC[0] + (d >= 0 ? 1 : -1) * (this.dir ? 46 : 38), this.headC[1] - 36];
          if (d >= 0) Rr = this.ik(S.R, fh, 'out'); else L = this.ik(S.L, fh, 'out');
          break;
        }
        case 'type': {
          const kb = this.targets.keyboard || [[this.headC[0] + d * 95, this.torsoTop + 85], [this.headC[0] + d * 140, this.torsoTop + 85]];
          const kL = d > 0 ? kb[0] : kb[1], kR = d > 0 ? kb[1] : kb[0];
          L = this.ik(S.L, kL, 'down'); Rr = this.ik(S.R, kR, 'down');
          break;
        }
        case 'scroll': case 'phone': {
          const ph = [this.shoulder.R[0] + 34, this.torsoTop + 64];
          if (d >= 0) { Rr = this.ik(S.R, ph, 'out'); hR = 'phone'; } else { L = this.ik(S.L, [-ph[0], ph[1]], 'out'); hL = 'phone'; }
          break;
        }
        case 'point': case 'present': {
          const T = this.resolveTarget(args.at ?? args.to ?? 'prop', args.item);
          const s = args.arm ? (args.arm === 'left' ? 'L' : 'R') : side([T[0] - this.headC[0], 0]);
          const a = this.straightAt(S[s], T);
          if (pose === 'point') { a[0] = clamp(a[0], -170, 170); a[1] = s === 'R' ? -6 : 6; }
          else { a[0] = clamp(a[0], -80, 80); a[1] = s === 'R' ? -10 : 10; }
          if (s === 'R') { Rr = a; hR = pose === 'point' ? 'point' : 'open'; } else { L = a; hL = pose === 'point' ? 'point' : 'open'; }
          break;
        }
        case 'press': {
          const T = this.resolveTarget(args.at ?? args.to ?? 'button');
          const s = args.arm ? (args.arm === 'left' ? 'L' : 'R') : side([T[0] - this.headC[0], 0]);
          const a = this.ik(S[s], T, 'down');
          if (s === 'R') { Rr = a; hR = 'point'; } else { L = a; hL = 'point'; }
          break;
        }
        case 'clap': L = this.ik(S.L, [-6, this.torsoTop + 40], 'out'); Rr = this.ik(S.R, [6, this.torsoTop + 40], 'out'); break;
        default: throw new Error(`Scene "${this.owner.id}": unknown arms pose "${pose}" (rest, hips, victory, wave, shrug, think, facepalm, type, scroll, phone, point, present, press, clap)`);
      }
      return { angles: [L[0], L[1], Rr[0], Rr[1]], L: hL, R: hR, back: ['type', 'scroll', 'phone'].includes(pose) ? back : (pose === 'rest' && this.dir ? back : null) };
    }

    // ---------- build
    build(parent) {
      const g = (this.g = svgEl('g', { class: 'ss-rig', fill: 'none', stroke: INK, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, parent));
      const W = { fill: PAPER };
      this.backArm = svgEl('g', {}, g);
      this.legsG = svgEl('g', {}, g);
      this.legs = [svgEl('path', {}, this.legsG), svgEl('path', {}, this.legsG)];
      this.torso = svgEl('rect', Object.assign({ x: -R.torsoW / 2, y: this.torsoTop, width: R.torsoW, height: R.torsoH, rx: R.torsoW / 2 }, W), g);
      // head
      this.headG = svgEl('g', {}, g);
      this.hair = svgEl('path', {}, this.headG);
      this.skull = svgEl('circle', Object.assign({ cx: 0, cy: 0, r: R.head }, W), this.headG);
      this.faceG = svgEl('g', {}, this.headG);
      this.eyes = [0, 1].map(() => {
        const e = {};
        e.white = svgEl('ellipse', { fill: PAPER }, this.faceG);
        e.pupil = svgEl('ellipse', { fill: INK, stroke: 'none' }, this.faceG);
        e.glint = svgEl('circle', { fill: PAPER, stroke: 'none', r: 2.4 }, this.faceG);
        e.lid = svgEl('path', {}, this.faceG);
        return e;
      });
      this.brows = [svgEl('path', {}, this.faceG), svgEl('path', {}, this.faceG)];
      this.mouth = svgEl('path', { fill: PAPER }, this.faceG);
      this.frontArm = svgEl('g', {}, g);
      this.arms = {};
      for (const s of ['L', 'R']) {
        const a = {};
        a.g = svgEl('g', {}, this.frontArm);
        a.line = svgEl('path', {}, a.g);
        a.phone = svgEl('g', { visibility: 'hidden' }, a.g);
        a.phoneBody = svgEl('rect', { x: -19, y: -33, width: 38, height: 66, rx: 7, fill: PAPER }, a.phone);
        a.phoneLines = svgEl('g', { 'clip-path': '' }, a.phone);
        a.phoneLineEls = [0, 1, 2, 3].map(() => svgEl('line', {}, a.phoneLines));
        a.thumb = svgEl('path', {}, a.phone);
        a.finger = svgEl('path', {}, a.g);
        a.hand = svgEl('circle', { r: R.hand, fill: PAPER }, a.g);
        this.arms[s] = a;
      }
      this.renderLegs();
      this.blinks = this.blinkSchedule();
    }
    blinkSchedule() {
      const r = rng(this.seed ^ 0xb11c);
      const out = [];
      let t = 0.5 + r() * 1.6;
      const end = (this.owner.scene.spec.duration || 30) + 2;
      while (t < end) {
        out.push(t);
        if (r() < 0.16) out.push(t + 0.26); // double blink
        t += 2.3 + r() * 2.6;
      }
      return out;
    }
    renderLegs() {
      const d = this.dir || 0;
      const sw = this.inkScale;
      if (this.sit) {
        const dd = d || 1;
        const k1 = [dd * R.thigh, this.hip[1] - 7], a1 = [dd * (R.thigh + 12), -7];
        const k2 = [dd * (R.thigh - 14), this.hip[1] - 12], a2 = [dd * (R.thigh - 4), -9];
        attr(this.legs[0], 'd', `M${pt([-dd * 6, this.hip[1] - 6])}L${pt(k2)}L${pt(a2)}L${pt(add(a2, [dd * 20, 0]))}`);
        attr(this.legs[1], 'd', `M${pt(this.hip)}L${pt(k1)}L${pt(a1)}L${pt(add(a1, [dd * 20, 0]))}`);
      } else {
        const hL = [-13, this.hip[1]], hR = [13, this.hip[1]];
        const aL = [-24, -7], aR = [24, -7];
        const fL = d ? add(aL, [d * 20, 0]) : add(aL, [-19, 0]);
        const fR = d ? add(aR, [d * 20, 0]) : add(aR, [19, 0]);
        attr(this.legs[0], 'd', `M${pt(hL)}L${pt(aL)}L${pt(fL)}`);
        attr(this.legs[1], 'd', `M${pt(hR)}L${pt(aR)}L${pt(fR)}`);
      }
      void sw;
    }

    // ---------- compile-time actions
    setMood(at, mood, dur) {
      const m = MOODS[mood];
      if (!m) throw new Error(`Scene "${this.owner.id}": unknown mood "${mood}" (${Object.keys(MOODS).join(', ')})`);
      this.browsT.to(at, m.brows.slice(), dur, 'smooth');
      this.mouthT.to(at, m.mouth.slice(), dur, 'smooth');
      this.eyeT.to(at, m.eye, dur, 'smooth');
      this.wideT.to(at, m.wide, dur, 'smooth');
    }
    setArms(at, pose, dur, args) {
      const p = this.poseAngles(pose, args || {});
      this.armsT.to(at, p.angles, dur, args.ease || 'smooth');
      this.hands.add(at + dur * 0.5, { L: p.L, R: p.R, back: p.back, kind: pose });
      const loop = LOOP_POSES[pose];
      for (const k in this.loopAmp) {
        if (k === loop) this.loopAmp[k].to(at + dur * 0.55, 1, 0.35, 'smooth');
        else this.loopAmp[k].to(at, 0, Math.min(0.25, dur), 'smooth');
      }
      this.typeStarts.add(at, { on: pose === 'type' });
      if (pose === 'press') this.presses.push({ at: at + dur * 0.85, dur: 0.38 });
    }

    // ---------- render
    loops(t) {
      const A = this.loopAmp;
      const out = [0, 0, 0, 0];
      const ty = A.type.value(t);
      if (ty > 0.001) {
        for (let s = 0; s < 2; s++) {
          const ph = (t + s * 0.083) / 0.165;
          const i = Math.floor(ph), u = ph - i;
          const hit = noise(this.seed + s * 77, i) > 0.28 ? Math.pow(Math.sin(Math.PI * u), 2) : 0;
          out[s * 2] += ty * hit * (s ? -3 : 3);
          out[s * 2 + 1] += ty * hit * (s ? 9 : -9);
        }
      }
      const wv = A.wave.value(t);
      if (wv > 0.001) {
        const w = Math.sin(t * Math.PI * 2 * 2.1);
        const k = this.dir < 0 ? 0 : 2, sg = this.dir < 0 ? -1 : 1;
        out[k] += sg * wv * 5 * w;
        out[k + 1] += sg * wv * 26 * w;
      }
      const vc = A.victory.value(t);
      if (vc > 0.001) {
        const w = Math.sin(t * Math.PI * 2 * 1.7);
        out[0] -= vc * 7 * w; out[2] += vc * 7 * w;
        out[1] -= vc * 10 * w; out[3] += vc * 10 * w;
      }
      const cl = A.clap.value(t);
      if (cl > 0.001) {
        const w = Math.pow(Math.abs(Math.sin(t * Math.PI * 2.4)), 0.7);
        out[0] -= cl * 10 * w; out[2] += cl * 10 * w;
      }
      for (const p of this.presses) {
        const b = bump(t, p.at, p.dur);
        if (b > 0) { // push the pressing hand 10% further
          const hk = this.hands.last(p.at);
          const s = hk && hk.L === 'point' ? 0 : 2;
          out[s + 1] += (s ? -1 : 1) * 14 * b;
          out[s] += (s ? 1 : -1) * 4 * b;
        }
      }
      return out;
    }
    armPoints(s, a1, a2, isBack) {
      const S = isBack ? this.shoulderBack[s] : this.shoulder[s];
      const e = [S[0] + R.upper * Math.sin(a1 * D2R), S[1] + R.upper * Math.cos(a1 * D2R)];
      const h = [e[0] + R.fore * Math.sin((a1 + a2) * D2R), e[1] + R.fore * Math.cos((a1 + a2) * D2R)];
      return { S, e, h, ang: a1 + a2 };
    }
    render(t, local) {
      // ----- arms
      const ang = this.armsT.value(t);
      const lo = this.loops(t);
      const hk = this.hands.last(t) || {};
      for (const [s, i] of [['L', 0], ['R', 2]]) {
        const a = this.arms[s];
        const P = this.armPoints(s, ang[i] + lo[i], ang[i + 1] + lo[i + 1], hk.back === s);
        const host = hk.back === s ? this.backArm : this.frontArm;
        if (a.g.parentNode !== host) host.appendChild(a.g);
        const shape = hk[s] || 'open';
        // the line stops at the hand outline
        const dirv = [Math.sin(P.ang * D2R), Math.cos(P.ang * D2R)];
        attr(a.line, 'd', `M${pt(P.S)}L${pt(P.e)}L${pt(P.h)}`);
        const hr = shape === 'fist' ? R.hand + 1.5 : shape === 'point' ? R.hand - 2 : R.hand;
        attr(a.hand, 'cx', n1(P.h[0])); attr(a.hand, 'cy', n1(P.h[1])); attr(a.hand, 'r', n1(hr));
        if (shape === 'point') {
          const f0 = add(P.h, [dirv[0] * (hr - 2), dirv[1] * (hr - 2)]);
          const f1 = add(P.h, [dirv[0] * (hr + 19), dirv[1] * (hr + 19)]);
          attr(a.finger, 'd', `M${pt(f0)}L${pt(f1)}`);
          attr(a.finger, 'visibility', 'visible');
        } else attr(a.finger, 'visibility', 'hidden');
        if (shape === 'phone') {
          attr(a.phone, 'visibility', 'visible');
          const side = s === 'R' ? 1 : -1;
          const c = [P.h[0] + side * 6, P.h[1] - 30];
          attr(a.phone, 'transform', `translate(${n1(c[0])},${n1(c[1])}) rotate(${side * -8})`);
          // scrolling content + thumb swipe
          const sc = this.loopAmp.scroll.value(t);
          const period = 0.9;
          const cyc = Math.max(0, t) / period, ci = Math.floor(cyc), cu = cyc - ci;
          const swipe = clamp((cu - 0.15) / 0.35);
          const se = getEase('smooth')(swipe);
          const off = sc > 0.01 ? (ci + se) * 15 : 0;
          a.phoneLineEls.forEach((ln, k) => {
            let y = -20 + ((k * 15 - off) % 60 + 60) % 60;
            const vis = y <= 22 && y >= -22;
            attr(ln, 'x1', -10); attr(ln, 'x2', k % 2 ? 4 : 9);
            attr(ln, 'y1', n1(y)); attr(ln, 'y2', n1(y));
            attr(ln, 'visibility', vis ? 'visible' : 'hidden');
          });
          const lift = sc > 0.01 ? (cu < 0.15 ? 0 : cu < 0.5 ? 0 : clamp((cu - 0.5) / 0.15)) : 0;
          const ty = sc > 0.01 ? lerp(14, -10, se) * (1 - lift) + 14 * lift : 4;
          attr(a.thumb, 'd', `M${n1(side * -24)},${n1(ty + 18)}Q${n1(side * -12)},${n1(ty + 8)} ${n1(side * -4)},${n1(ty)}`);
          attr(a.thumb, 'visibility', lift > 0.5 && lift < 1 ? 'hidden' : 'visible');
        } else attr(a.phone, 'visibility', 'hidden');
      }
      // ----- head
      const tilt = this.tiltT.value(t);
      let nodY = 0, shakeX = 0;
      for (const n of this.nods) {
        if (t < n.at || t > n.at + n.dur) continue;
        const u = (t - n.at) / n.dur;
        const env = Math.sin(Math.PI * u);
        const w = Math.sin(u * Math.PI * 2 * n.times);
        if (n.kind === 'shake') shakeX += env * w * 9; else nodY += env * Math.max(0, w) * 9;
      }
      const hc = this.headC;
      attr(this.headG, 'transform', `translate(${n1(hc[0])},${n1(hc[1] + nodY * 0.35)}) rotate(${n1(tilt)},0,${R.head - 8})`);
      const face = this.faceT.value(t);
      const fx = face * 15 + shakeX, fy = nodY;
      // hair: exactly three strands from the top of the skull
      let hd = '';
      for (const k of [-1, 0, 1]) {
        const bx = k * 15 + face * 5;
        const by = -Math.sqrt(R.head * R.head - bx * bx) + 1;
        const tip = [bx + k * 9 + 5, by - 27 + Math.abs(k) * 4];
        const c = [bx + k * 2 - 9, by - 15];
        hd += `M${pt([bx, by])}Q${pt(c)} ${pt(tip)}`;
      }
      attr(this.hair, 'd', hd);
      // eyes
      let open = this.eyeT.value(t);
      for (const b of this.blinks.concat(this.owner.extraBlinks || [])) {
        if (t >= b && t <= b + 0.2) { const u = (t - b) / 0.2; open *= 1 - (u < 0.35 ? u / 0.35 : u < 0.5 ? 1 : 1 - (u - 0.5) / 0.5); }
      }
      const wide = this.wideT.value(t);
      const lk = this.lookT.value(t);
      const spread = 20 * (1 - Math.abs(face) * 0.14);
      const erx = 12.5 * wide, ery0 = 16.5 * wide;
      const ery = Math.max(0.1, ery0 * open);
      for (let i = 0; i < 2; i++) {
        const E = this.eyes[i];
        const cx = fx + (i ? spread : -spread) + face * (i ? -1.5 : 1.5), cy = -8 + fy;
        const closed = open < 0.2;
        attr(E.white, 'cx', n1(cx)); attr(E.white, 'cy', n1(cy));
        attr(E.white, 'rx', n1(erx)); attr(E.white, 'ry', n1(ery));
        attr(E.white, 'visibility', closed ? 'hidden' : 'visible');
        attr(E.lid, 'visibility', closed ? 'visible' : 'hidden');
        if (closed) attr(E.lid, 'd', `M${pt([cx - erx, cy + 1])}Q${pt([cx, cy + 7])} ${pt([cx + erx, cy + 1])}`);
        const pr = 6.6;
        const px = cx + lk[0] * (erx - pr - 1.5), py = cy + lk[1] * Math.max(0, ery - pr - 1.5);
        const pry = Math.min(pr, Math.max(0, ery - 2.5));
        attr(E.pupil, 'cx', n1(px)); attr(E.pupil, 'cy', n1(py));
        attr(E.pupil, 'rx', n1(pr)); attr(E.pupil, 'ry', n1(pry));
        attr(E.pupil, 'visibility', closed || pry < 1 ? 'hidden' : 'visible');
        attr(E.glint, 'cx', n1(px + 2.4)); attr(E.glint, 'cy', n1(py - 2.6));
        attr(E.glint, 'visibility', closed || pry < 4 ? 'hidden' : 'visible');
      }
      // brows
      const bw = this.browsT.value(t);
      for (let i = 0; i < 2; i++) {
        const sg = i ? 1 : -1;
        const cx = fx + sg * spread;
        const by = -8 + fy - ery0 - 11 - (wide - 1) * 16;
        const lim = (q) => { const r0 = Math.hypot(q[0], q[1]), m = R.head - 9; return r0 > m ? [q[0] * m / r0, q[1] * m / r0] : q; };
        const inner = lim([cx - sg * 10, by + bw[i * 3]]), outer = lim([cx + sg * 12, by + bw[i * 3 + 1]]);
        const mid = [(inner[0] + outer[0]) / 2, (inner[1] + outer[1]) / 2 - bw[i * 3 + 2]];
        const c = [2 * mid[0] - (inner[0] + outer[0]) / 2, 2 * mid[1] - (inner[1] + outer[1]) / 2];
        attr(this.brows[i], 'd', `M${pt(inner)}Q${pt(c)} ${pt(outer)}`);
      }
      // mouth
      const m = this.mouthT.value(t).slice();
      let talk = 0;
      for (const tk of this.talks) {
        if (t < tk.at || t > tk.at + tk.dur) continue;
        const env = Math.min(1, (t - tk.at) / 0.08, (tk.at + tk.dur - t) / 0.08);
        const ph = (t - tk.at) / 0.105;
        const i = Math.floor(ph), u = ph - i;
        const a0 = noise(this.seed + 5, i), a1 = noise(this.seed + 5, i + 1);
        const s = lerp(a0, a1, u * u * (3 - 2 * u));
        talk = Math.max(talk, env * (s < 0.22 ? 0 : s));
      }
      if (talk > 0) { m[3] -= talk * 4; m[4] += talk * 15; m[0] = lerp(m[0], 26, talk * 0.4); }
      attr(this.mouth, 'd', this.mouthPath(fx, 26 + fy, m));
    }
    mouthPath(cx, cy, m) {
      const [w, cL, cR, U, D, wob] = m;
      const N = 12;
      const L = [cx - w / 2, cy - cL], Rr = [cx + w / 2, cy - cR];
      const q = (a, c, b, u) => (1 - u) * (1 - u) * a + 2 * (1 - u) * u * c + u * u * b;
      const up = [], dn = [];
      for (let i = 0; i <= N; i++) {
        const u = i / N;
        const x = q(L[0], cx, Rr[0], u);
        const wv = wob ? Math.sin(u * Math.PI * 4) * wob * Math.sin(u * Math.PI) : 0;
        up.push([x, q(L[1], cy + U, Rr[1], u) + wv]);
        dn.push([x, q(L[1], cy + D, Rr[1], u) + wv]);
      }
      const pts = up.concat(dn.reverse().slice(1, -1));
      return 'M' + pts.map(pt).join('L') + 'Z';
    }
  }

  // ------------------------------------------------------------------ Props
  // Each prop builder returns { g, box: [x0,y0,x1,y1], anchors: {name: [x,y]}, render(t) , actions }.
  const PROP_KINDS = ['desk', 'chair', 'laptop', 'monitor', 'phone', 'clock', 'checklist', 'timer', 'mug', 'coffee', 'door'];

  function buildDesk(parent, o) {
    const g = svgEl('g', {}, parent);
    const x0 = o.x0, x1 = o.x1, Y = o.top, z0 = -150, z1 = 40, th = 16;
    const fl = P3(x0, Y, z1), fr = P3(x1, Y, z1), bl = P3(x0, Y, z0), br = P3(x1, Y, z0);
    // back legs (seen between the front legs), then top, front face, front legs
    const legIn = 34;
    for (const x of [x0 + legIn + 30, x1 - legIn - 30]) {
      const a = P3(x, Y - th, z0 + 30), b = P3(x, 0, z0 + 30);
      svgEl('path', { d: `M${pt(a)}L${pt(b)}` }, g);
    }
    svgEl('path', { d: poly([bl, br, fr, fl]), fill: PAPER }, g);
    const ffl = [fl[0], fl[1] + th * KY], ffr = [fr[0], fr[1] + th * KY];
    svgEl('path', { d: poly([fl, fr, ffr, ffl]), fill: PAPER }, g);
    for (const x of [x0 + legIn, x1 - legIn]) {
      const a = P3(x, Y - th, z1 - 4), b = P3(x, 0, z1 - 4);
      svgEl('path', { d: `M${pt(a)}L${pt(b)}` }, g);
    }
    // a drawer on the far end
    if (o.drawer !== false) {
      const dx0 = x1 - legIn - 120, dx1 = x1 - legIn - 12;
      const d0 = P3(dx0, Y - th, z1 - 4), d1 = P3(dx1, Y - th - 58, z1 - 4);
      svgEl('rect', { x: n1(d0[0]), y: n1(d0[1]), width: n1(d1[0] - d0[0]), height: n1(d1[1] - d0[1]), rx: 6, fill: PAPER }, g);
      const hx = (d0[0] + d1[0]) / 2, hy = (d0[1] + d1[1]) / 2;
      svgEl('path', { d: `M${n1(hx - 18)},${n1(hy)}L${n1(hx + 18)},${n1(hy)}` }, g);
    }
    return { g, box: [Math.min(fl[0], bl[0]) - 4, bl[1] - 4, Math.max(fr[0], br[0]) + 4, 4], top: Y, render() {} };
  }

  function buildChair(parent, o) {
    const g = svgEl('g', {}, parent);
    const d = o.dir || 1, sy = o.seatY;
    const back = -d * 50;
    svgEl('path', { d: `M${n1(back)},${sy - 2}L${n1(back - d * 7)},${sy - 150}` }, g);
    svgEl('rect', { x: Math.min(-d * 52, d * 46), y: sy, width: 98, height: 13, rx: 6.5, fill: PAPER }, g);
    svgEl('path', { d: `M${n1(-d * 38)},${sy + 13}L${n1(-d * 46)},0M${n1(d * 32)},${sy + 13}L${n1(d * 40)},0` }, g);
    return { g, box: [Math.min(back - d * 20, d * 46) - 6, sy - 160, Math.max(back - d * 20, d * 50) + 6, 2], render() {} };
  }

  /** Screen content drawn in a 100 x 64 unit rect, mapped onto a parallelogram via an affine matrix. */
  function screenContent(owner, parent, matrix, initial, inkScale, kScreen) {
    const g = svgEl('g', { transform: matrix }, parent);
    const sw = (SW / inkScale / kScreen).toFixed(3);
    const states = {};
    const mk = (name) => (states[name] = svgEl('g', { 'stroke-width': sw, visibility: 'hidden' }, g));
    // code: lines that "type" in while the typing loop runs
    const code = mk('code');
    const lines = [[8, 46], [16, 62], [16, 40], [8, 28], [16, 70], [8, 36]];
    const codeEls = lines.map(([x, w], i) => svgEl('line', { x1: x, x2: x + w, y1: 10 + i * 9, y2: 10 + i * 9 }, code));
    const err = mk('error');
    svgEl('path', { d: 'M50,12L68,46L32,46Z', fill: PAPER }, err);
    svgEl('path', { d: 'M50,24L50,34M50,40L50,40.5' }, err);
    const ok = mk('success');
    svgEl('circle', { cx: 50, cy: 31, r: 18, fill: PAPER }, ok);
    svgEl('path', { d: 'M41,31L48,38L60,24' }, ok);
    const chart = mk('chart');
    svgEl('path', { d: 'M12,52L12,8M12,52L90,52' }, chart);
    const chartLine = svgEl('path', { d: 'M18,46L36,36L52,40L70,22L86,14' }, chart);
    const blank = mk('blank');
    void blank;
    const txt = mk('text');
    const textEl = svgEl('text', { x: 50, y: 38, 'text-anchor': 'middle', fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': 18 }, txt);
    const ev = new Events().add(-1e9, { state: initial || 'code' });
    return {
      setState(at, s, text) {
        if (!states[s]) throw new Error(`${owner.id}: unknown screen state "${s}" (code, error, success, chart, blank, text)`);
        ev.add(at, { state: s, text });
      },
      render(t, typed) {
        const cur = ev.last(t);
        for (const k in states) attr(states[k], 'visibility', k === cur.state ? 'visible' : 'hidden');
        if (cur.state === 'text') { if (textEl.textContent !== (cur.text || '')) textEl.textContent = cur.text || ''; }
        if (cur.state === 'code') {
          // typed is in "units of line length"; null => all lines complete
          let rem = typed == null ? 1e9 : typed;
          lines.forEach(([x, w], i) => {
            const vis = clamp(rem, 0, w);
            rem -= w;
            attr(codeEls[i], 'x2', n1(x + Math.max(0.01, vis)));
            attr(codeEls[i], 'visibility', vis > 0.5 ? 'visible' : 'hidden');
          });
        }
        if (cur.state === 'chart') {
          const p = prog(t, cur.at, 0.9, 'smooth');
          window.CA.drawOn(chartLine, cur.at < -1e8 ? 1 : p);
        }
      },
      totalCode: lines.reduce((s, l) => s + l[1], 0),
    };
  }

  function laptopGeom(o) {
    const alpha = (o.alpha ?? 50) * D2R, d = o.dir || 1;
    const b = [-d * Math.cos(alpha), Math.sin(alpha)]; // toward the user (X, Z)
    const a = [d * Math.sin(alpha), Math.cos(alpha)]; // width axis
    return { a, b };
  }
  function buildLaptop(owner, parent, o) {
    const g = svgEl('g', {}, parent);
    const { a, b } = laptopGeom(o);
    const W = 150, D = 100, Y = o.top, th = 7, LH = 112, lean = 12 * D2R;
    const [hx, hz] = o.hinge; // world X,Z of hinge-left
    const W3 = (u, v, y) => P3(hx + a[0] * u + b[0] * v, Y + y, hz + a[1] * u + b[1] * v);
    // base slab
    const b0 = W3(0, 0, th), b1 = W3(W, 0, th), b2 = W3(W, D, th), b3 = W3(0, D, th);
    const f2 = W3(W, D, 0), f3 = W3(0, D, 0), f1 = W3(W, 0, 0);
    svgEl('path', { d: poly([b3, b2, f2, f3]), fill: PAPER }, g);
    svgEl('path', { d: poly([b1, b2, f2, f1]), fill: PAPER }, g);
    svgEl('path', { d: poly([b0, b1, b2, b3]), fill: PAPER }, g);
    // keyboard hint + trackpad on the base
    // lid (leaning back from the hinge, away from the user)
    const up = LH * Math.cos(lean), back = -LH * Math.sin(lean);
    const L0 = W3(0, back, th + up), L1 = W3(W, back, th + up);
    const h0 = W3(0, 0, th), h1 = W3(W, 0, th);
    svgEl('path', { d: poly([h0, h1, L1, L0]), fill: PAPER }, g);
    // screen inset: affine map of a 100 x 64 rect
    const inset = (u, v) => [lerp(lerp(L0[0], L1[0], u), lerp(h0[0], h1[0], u), v), lerp(lerp(L0[1], L1[1], u), lerp(h0[1], h1[1], u), v)];
    const s00 = inset(0.09, 0.1), s10 = inset(0.91, 0.1), s01 = inset(0.09, 0.86);
    const mx = [(s10[0] - s00[0]) / 100, (s10[1] - s00[1]) / 100, (s01[0] - s00[0]) / 64, (s01[1] - s00[1]) / 64, s00[0], s00[1]];
    const kScr = Math.sqrt(Math.abs(mx[0] * mx[3] - mx[1] * mx[2]));
    const scr = screenContent(owner, g, `matrix(${mx.map((v) => v.toFixed(4)).join(',')})`, o.screen, o.inkScale, kScr);
    const keyboard = [W3(W * 0.26, D * 0.62, th), W3(W * 0.62, D * 0.56, th)];
    const all = [b0, b1, b2, b3, f2, f3, f1, L0, L1];
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    return {
      g, box: [Math.min(...xs) - 4, Math.min(...ys) - 4, Math.max(...xs) + 4, Math.max(...ys) + 4],
      anchors: { keyboard, screen: inset(0.5, 0.45), button: keyboard[1] }, screen: scr, render() {},
    };
  }
  function buildMonitor(owner, parent, o) {
    const g = svgEl('g', {}, parent);
    const { a, b } = laptopGeom(Object.assign({}, o, { alpha: o.alpha ?? 58 }));
    const W = 200, H = 128, Y = o.top, neck = 46;
    const [hx, hz] = o.hinge;
    const W3 = (u, v, y) => P3(hx + a[0] * u + b[0] * v, Y + y, hz + a[1] * u + b[1] * v);
    // foot + neck
    const fc = W3(W / 2, 10, 0);
    svgEl('ellipse', { cx: n1(fc[0]), cy: n1(fc[1]), rx: 36, ry: 11, fill: PAPER }, g);
    const n0 = W3(W / 2, 4, 0), nn = W3(W / 2, 4, neck + 6);
    svgEl('path', { d: `M${pt(n0)}L${pt(nn)}` }, g);
    const c00 = W3(0, 0, neck + H), c10 = W3(W, 0, neck + H), c11 = W3(W, 0, neck), c01 = W3(0, 0, neck);
    svgEl('path', { d: poly([c00, c10, c11, c01]), fill: PAPER }, g);
    const inset = (u, v) => [lerp(lerp(c00[0], c10[0], u), lerp(c01[0], c11[0], u), v), lerp(lerp(c00[1], c10[1], u), lerp(c01[1], c11[1], u), v)];
    const s00 = inset(0.07, 0.1), s10 = inset(0.93, 0.1), s01 = inset(0.07, 0.88);
    const mx = [(s10[0] - s00[0]) / 100, (s10[1] - s00[1]) / 100, (s01[0] - s00[0]) / 64, (s01[1] - s00[1]) / 64, s00[0], s00[1]];
    const kScr = Math.sqrt(Math.abs(mx[0] * mx[3] - mx[1] * mx[2]));
    const scr = screenContent(owner, g, `matrix(${mx.map((v) => v.toFixed(4)).join(',')})`, o.screen, o.inkScale, kScr);
    // a keyboard in front of the monitor (flat slab)
    const k0 = W3(30, 70, 0), k1 = W3(W - 30, 70, 0), k2 = W3(W - 30, 110, 0), k3 = W3(30, 110, 0);
    const K = [k0, k1, k2, k3].map((p) => [p[0], p[1]]);
    svgEl('path', { d: poly(K), fill: PAPER }, g);
    const keyboard = [W3(W * 0.36, 92, 4), W3(W * 0.62, 88, 4)];
    const all = [c00, c10, c11, c01, k0, k1, k2, k3, fc];
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    return {
      g, box: [Math.min(...xs) - 40, Math.min(...ys) - 4, Math.max(...xs) + 40, Math.max(...ys) + 14],
      anchors: { keyboard, screen: inset(0.5, 0.45), button: keyboard[1] }, screen: scr, render() {},
    };
  }

  function buildMug(owner, parent, o) {
    const g = svgEl('g', {}, parent);
    const [cx, by] = o.at; // projected bottom center
    const r = 22, h = 50, ry = r * 0.36;
    svgEl('path', { d: `M${n1(cx + r - 2)},${n1(by - h + 12)}C${n1(cx + r + 22)},${n1(by - h + 8)} ${n1(cx + r + 22)},${n1(by - 12)} ${n1(cx + r - 2)},${n1(by - 14)}` }, g);
    svgEl('path', { d: `M${n1(cx - r)},${n1(by - h)}L${n1(cx - r)},${n1(by)}A${r},${n1(ry)} 0 0 0 ${n1(cx + r)},${n1(by)}L${n1(cx + r)},${n1(by - h)}Z`, fill: PAPER }, g);
    svgEl('ellipse', { cx: n1(cx), cy: n1(by - h), rx: r, ry: n1(ry), fill: PAPER }, g);
    const steam = [0, 1, 2].map(() => svgEl('path', {}, g));
    return {
      g, box: [cx - r - 6, by - h - 100, cx + r + 26, by + ry + 4], anchors: { mug: [cx, by - h / 2] },
      render(t) {
        steam.forEach((p, i) => {
          const ph = ((t * 0.55 + i / 3) % 1 + 1) % 1;
          const x0 = cx - 12 + i * 12, y0 = by - h - 12 - ph * 32;
          let d = '';
          for (let k = 0; k <= 8; k++) {
            const yy = y0 - k * 5;
            const xx = x0 + Math.sin(k * 0.9 + t * 3 + i * 2) * 4;
            d += (k ? 'L' : 'M') + pt([xx, yy]);
          }
          attr(p, 'd', d);
          const op = Math.sin(Math.PI * ph);
          attr(p, 'opacity', (op * 0.9).toFixed(3));
          attr(p, 'stroke-width', (SW * 0.7 / o.inkScale).toFixed(3));
        });
      },
    };
  }

  function parseClock(s) {
    if (typeof s === 'number') return s;
    const m = String(s || '10:10').match(/(\d+):(\d+)/);
    return m ? (+m[1] % 12) * 60 + +m[2] : 610;
  }
  function buildClock(owner, parent, o) {
    const g = svgEl('g', { transform: `translate(${n1(o.at[0])},${n1(o.at[1])})` }, parent);
    const r = o.r || 62;
    svgEl('circle', { r, fill: PAPER }, g);
    const ticks = [];
    for (let i = 0; i < 12; i++) {
      const a = i * 30 * D2R, L = i % 3 === 0 ? 12 : 5;
      ticks.push(`M${pt([Math.sin(a) * (r - 13), -Math.cos(a) * (r - 13)])}L${pt([Math.sin(a) * (r - 13 - L), -Math.cos(a) * (r - 13 - L)])}`);
    }
    svgEl('path', { d: ticks.join(''), 'stroke-width': (SW * 0.8 / o.inkScale).toFixed(3) }, g);
    const hourH = svgEl('line', { x1: 0, y1: 0, x2: 0, y2: -r * 0.42 }, g);
    const minH = svgEl('line', { x1: 0, y1: 0, x2: 0, y2: -r * 0.66 }, g);
    const secH = svgEl('line', { x1: 0, y1: 8, x2: 0, y2: -r * 0.72, 'stroke-width': (SW * 0.45 / o.inkScale).toFixed(3) }, g);
    svgEl('circle', { r: 4, fill: INK, stroke: 'none' }, g);
    const minutes = new Track(parseClock(o.time));
    const run = o.speed ?? 0; // clock minutes per second of video (ambient), 0 = real time-ish
    return {
      g, box: [o.at[0] - r - 4, o.at[1] - r - 4, o.at[0] + r + 4, o.at[1] + r + 4], anchors: { clock: o.at },
      a_clock(at, dur, args) {
        const cur = minutes.value(at);
        let to = args.to != null ? parseClock(args.to) : cur + (args.add ?? 60);
        if (args.to != null) while (to <= cur) to += 720;
        minutes.to(at, to, dur, args.ease || 'inOut');
      },
      render(t) {
        const m = minutes.value(t) + run * Math.max(0, t);
        attr(minH, 'transform', `rotate(${n1(m * 6)})`);
        attr(hourH, 'transform', `rotate(${n1(m * 0.5)})`);
        attr(secH, 'transform', `rotate(${Math.floor(Math.max(0, t)) * 6 + 30})`);
      },
    };
  }

  function checklistSize(o) {
    const items = o.items || ['Plan', 'Build', 'Ship'];
    const tw = Math.max(textWidth(o.title || '', `400 40px ${HAND}`), ...items.map((s) => textWidth(s, `400 34px ${HAND}`)));
    return [Math.max(250, tw + 120), (o.title ? 86 : 40) + items.length * 58 + 18];
  }
  function buildChecklist(owner, parent, o) {
    const items = o.items || ['Plan', 'Build', 'Ship'];
    const fs = 34, lh = 58;
    const font = `400 ${fs}px ${HAND}`;
    const [w, h] = checklistSize(o);
    const g = svgEl('g', { transform: `translate(${n1(o.at[0] - w / 2)},${n1(o.at[1] - h / 2)})` }, parent);
    svgEl('rect', { x: 0, y: 0, width: w, height: h, rx: 12, fill: PAPER }, g);
    // clipboard clip
    svgEl('rect', { x: w / 2 - 42, y: -14, width: 84, height: 26, rx: 8, fill: PAPER }, g);
    let y0 = 40;
    if (o.title) {
      const tt = svgEl('text', { x: w / 2, y: 64, 'text-anchor': 'middle', fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': 40 }, g);
      tt.textContent = o.title;
      y0 = 96;
    }
    const checks = [], boxes = [];
    items.forEach((s, i) => {
      const cy = y0 + i * lh + 12;
      svgEl('rect', { x: 34, y: cy - 16, width: 32, height: 32, rx: 6, fill: PAPER }, g);
      const tx = svgEl('text', { x: 84, y: cy + 11, fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': fs }, g);
      tx.textContent = s;
      const ck = svgEl('path', { d: `M38,${cy - 2}L49,${cy + 10}L72,${cy - 22}`, 'stroke-width': (SW * 1.25 / o.inkScale).toFixed(3) }, g);
      const strike = svgEl('line', { x1: 80, x2: 84 + textWidth(s, font) + 4, y1: cy + 2, y2: cy + 2, visibility: 'hidden' }, g);
      checks.push({ ck, strike, at: (o.checked || []).includes(i) ? -1e9 : null });
      boxes.push([o.at[0] - w / 2 + 50, o.at[1] - h / 2 + cy]);
    });
    return {
      g, box: [o.at[0] - w / 2 - 4, o.at[1] - h / 2 - 18, o.at[0] + w / 2 + 4, o.at[1] + h / 2 + 4],
      anchors: { checklist: [o.at[0] - w / 2 + 40, o.at[1]], items: boxes },
      a_check(at, dur, args) {
        const i = args.item ?? checks.findIndex((c) => c.at == null);
        if (i < 0 || i >= checks.length) throw new Error(`${owner.id}: checklist has no item ${args.item}`);
        checks[i].at = at; checks[i].dur = dur; checks[i].strikeOn = !!args.strike;
      },
      render(t) {
        for (const c of checks) {
          if (c.at == null || t < c.at) { attr(c.ck, 'visibility', 'hidden'); attr(c.strike, 'visibility', 'hidden'); continue; }
          const p = c.at < -1e8 ? 1 : prog(t, c.at, c.dur || 0.35, 'out');
          attr(c.ck, 'visibility', 'visible');
          window.CA.drawOn(c.ck, p);
          if (c.strikeOn) { attr(c.strike, 'visibility', 'visible'); window.CA.drawOn(c.strike, c.at < -1e8 ? 1 : prog(t, c.at + 0.2, 0.3, 'out')); }
        }
      },
    };
  }

  function fmtTime(sec) {
    sec = Math.max(0, Math.ceil(sec - 1e-6));
    const m = Math.floor(sec / 60), s = sec % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
  function buildTimer(owner, parent, o) {
    const r = o.r || 74;
    const g = svgEl('g', { transform: `translate(${n1(o.at[0])},${n1(o.at[1])})` }, parent);
    svgEl('rect', { x: -14, y: -r - 26, width: 28, height: 18, rx: 5, fill: PAPER }, g);
    svgEl('path', { d: `M0,${-r - 8}L0,${-r}` }, g);
    svgEl('path', { d: `M${n1(r * 0.62)},${n1(-r * 0.86)}L${n1(r * 0.8)},${n1(-r * 1.04)}` }, g);
    svgEl('circle', { r, fill: PAPER }, g);
    const arc = svgEl('circle', { r: r - 16, transform: 'rotate(-90)', 'stroke-dasharray': '0 1000' }, g);
    const label = svgEl('text', { x: 0, y: 14, 'text-anchor': 'middle', fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': 44 }, g);
    const total = o.seconds ?? 1500;
    const up = o.mode === 'up';
    const runs = []; // {at, rate}
    let running = null;
    if (o.running) running = { at: -1e9, rate: o.rate ?? 60 };
    const remaining = (t) => {
      let used = 0;
      for (const w of runs.concat(running ? [Object.assign({ until: 1e9 }, running)] : [])) {
        const a = w.at < 0 ? 0 : w.at;
        if (t > a) used += (Math.min(t, w.until) - a) * w.rate;
      }
      return clamp(total - used, 0, total);
    };
    const circ = 2 * Math.PI * (r - 16);
    return {
      g, box: [o.at[0] - r - 4, o.at[1] - r - 30, o.at[0] + r + 4, o.at[1] + r + 4], anchors: { timer: o.at, button: [o.at[0], o.at[1] - r - 20] },
      a_timer(at, dur, args) {
        const on = args.run ?? args.on ?? true;
        if (running) { runs.push(Object.assign({ until: at }, running)); running = null; }
        if (on) running = { at, rate: args.rate ?? 60 };
      },
      render(t) {
        const rem = remaining(t);
        const shown = up ? total - rem : rem;
        const frac = total ? shown / total : 0;
        attr(arc, 'stroke-dasharray', `${n1(circ * frac)} ${n1(circ + 10)}`);
        if (label.textContent !== fmtTime(shown)) label.textContent = fmtTime(shown);
      },
    };
  }

  function buildDoor(owner, parent, o) {
    const w = 170, h = 340;
    const [cx, by] = o.at;
    const g = svgEl('g', {}, parent);
    const x0 = cx - w / 2, y0 = by - h;
    svgEl('rect', { x: x0 - 10, y: y0 - 10, width: w + 20, height: h + 10, rx: 4, fill: PAPER }, g);
    const panel = svgEl('path', { fill: PAPER }, g);
    const knob = svgEl('circle', { r: 7, fill: PAPER }, g);
    const rays = svgEl('path', { 'stroke-dasharray': '2 16' }, g);
    const openT = new Track(o.open ? 1 : 0);
    return {
      g, box: [x0 - 14, y0 - 14, x0 + w + 14, by + 2], anchors: { door: [cx, by - h * 0.55], button: [x0 + w - 24, by - h * 0.48] },
      a_door(at, dur, args) { openT.to(at, args.open === false ? 0 : 1, dur, 'smooth'); },
      render(t) {
        const p = openT.value(t);
        const ww = w * (1 - 0.72 * p), sk = 26 * p;
        attr(panel, 'd', poly([[x0, y0], [x0 + ww, y0 - sk], [x0 + ww, by + sk * 0.6], [x0, by]]));
        attr(knob, 'cx', n1(x0 + ww - 20 * (1 - p * 0.5))); attr(knob, 'cy', n1(by - h * 0.48));
        if (p > 0.05) {
          let d = '';
          for (let i = 0; i < 4; i++) d += `M${pt([x0 + w * 0.55 + i * 6, y0 + 40 + i * 70])}L${pt([x0 + w * 0.95 + 70 * p, y0 + 60 + i * 80])}`;
          attr(rays, 'd', d); attr(rays, 'visibility', 'visible');
        } else attr(rays, 'visibility', 'hidden');
      },
    };
  }

  // ------------------------------------------------------------------ Comic symbols
  const SYMBOLS = ['bubble', 'stress', 'sweat', 'check', 'sparkles', 'exclaim', 'question', 'zzz', 'idea', 'heart', 'music'];

  // ------------------------------------------------------------------ Shot (base for Scene / Walkthrough)
  class Shot extends Primitive {
    static autoEnter = false;
    static isShot = true;
    static actions = { cut: { dur: 0 }, enter: { dur: 0 }, exit: { dur: 0 } };
    build() {
      const S = this.scene;
      css(this.root, 'width', S.W + 'px'); css(this.root, 'height', S.H + 'px');
      if (!S.shots) { S.shots = new Events(); S.shotOrder = []; }
      S.shotOrder.push(this.id);
      if (S.shotOrder.length === 1) S.shots.add(-1e9, { id: this.id });
    }
    a_cut(at) { this.scene.shots.add(at, { id: this.id }); }
    a_enter(at) { this.a_cut(at); }
    a_exit(at) { const c = this.scene.shots.last(at); if (c && c.id === this.id) this.scene.shots.add(at, { id: null }); }
    active(t) { const c = this.scene.shots.last(t); return c && c.id === this.id ? c : null; }
    /** Time since this shot was last cut to (0 for the opening shot). */
    localT(t) { const c = this.active(t); return c ? t - Math.max(0, c.at) : 0; }
    shotStart(t) { const c = this.active(t); return c ? Math.max(0, c.at) : 0; }
    render(t) {
      const on = !!this.active(t);
      css(this.root, 'visibility', on ? 'visible' : 'hidden');
      css(this.root, 'opacity', on ? '1' : '0');
      return on;
    }
  }

  // ------------------------------------------------------------------ Caption (shared)
  class Caption {
    constructor(owner, parent, cls) {
      this.owner = owner;
      this.box = el('div', { class: cls }, parent);
      this.versions = [];
    }
    add(at, str) {
      const d = el('div', { class: 'ss-cap-line' }, this.box);
      const spans = splitWords(d, String(str || ''), {});
      this.versions.push({ at, d, spans, n: spans.length });
    }
    render(t, shotStart) {
      let cur = null;
      for (const v of this.versions) if (v.at <= t) cur = v;
      for (const v of this.versions) css(v.d, 'display', v === cur ? 'block' : 'none');
      if (!cur) return;
      const start = Math.max(cur.at, shotStart);
      revealWords(cur.spans, t - start - 0.05, { stagger: 0.045, wordDur: 0.32, blur: 6, rise: 10, ease: 'out' });
    }
  }

  // ------------------------------------------------------------------ Scene
  class Scene extends Shot {
    static defaults = { layout: 'auto', pose: null, facing: null, mood: 'neutral', arms: 'rest', look: null, props: [], caption: '', symbols: [], floor: true, side: 'right' };
    static actions = Object.assign({}, Shot.actions, {
      mood: { dur: 0.3 }, face: { dur: 0.3 }, brows: { dur: 0.25 }, mouth: { dur: 0.2 }, talk: { dur: 2.0 },
      blink: { dur: 0.2 }, look: { dur: 0.22 }, turn: { dur: 0.3 }, nod: { dur: 0.75 }, shake: { dur: 0.8 }, tilt: { dur: 0.4 },
      arms: { dur: 0.45 }, type: { dur: 0.45 }, scroll: { dur: 0.45 }, point: { dur: 0.4 }, press: { dur: 0.45 },
      wave: { dur: 0.45 }, victory: { dur: 0.4, ease: 'outBack' }, think: { dur: 0.5 }, shrug: { dur: 0.4 }, rest: { dur: 0.45 },
      facepalm: { dur: 0.45 }, hips: { dur: 0.45 }, clap: { dur: 0.35 },
      symbol: { dur: 0.3 }, bubble: { dur: 0.35 }, clear: { dur: 0.2 },
      check: { dur: 0.35 }, clock: { dur: 1.6 }, timer: { dur: 0 }, screen: { dur: 0 }, door: { dur: 0.6 },
      caption: { dur: 0 },
    });

    build() {
      super.build();
      const S = this.scene, p = this.props;
      this.inkG = null;
      // ---- normalise props list
      const list = (p.props || []).map((x) => (typeof x === 'string' ? { kind: x } : Object.assign({}, x)));
      for (const x of list) {
        if (x.kind === 'coffee') x.kind = 'mug';
        if (!PROP_KINDS.includes(x.kind)) throw new Error(`Scene "${this.id}": unknown prop "${x.kind}" (${PROP_KINDS.join(', ')})`);
      }
      const kinds = list.map((x) => x.kind);
      const deskish = kinds.some((k) => ['desk', 'laptop', 'monitor'].includes(k));
      let layout = p.layout === 'auto' ? (deskish ? 'desk' : list.length ? 'stand' : 'center') : p.layout;
      if (!['desk', 'stand', 'center'].includes(layout)) throw new Error(`Scene "${this.id}": unknown layout "${layout}" (desk, stand, center)`);
      this.layout = layout;
      const sideSign = p.side === 'left' ? -1 : 1;
      let dir = p.facing === 'left' ? -1 : p.facing === 'right' ? 1 : p.facing === 'front' ? 0 : (layout === 'center' ? 0 : sideSign);
      const pose = p.pose || (layout === 'desk' ? 'sit' : 'stand');
      this.dir = dir;

      // ---- DOM: svg composition + caption
      this.svg = svgEl('svg', { class: 'ss-svg', width: S.W, height: S.H, viewBox: `0 0 ${S.W} ${S.H}` }, this.root);
      this.comp = svgEl('g', { fill: 'none', stroke: INK, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, this.svg);
      this.caption = new Caption(this, this.root, 'ss-caption' + (S.portrait ? ' portrait' : ''));
      this.caption.add(-1e9, p.caption || '');
      const capH = p.caption ? this.caption.box.offsetHeight : 0;

      // ---- layers
      const L = {};
      for (const k of ['floor', 'back', 'furniture', 'props', 'rig', 'front', 'symbols']) L[k] = svgEl('g', {}, this.comp);
      this.L = L;

      // ---- props (local coordinates; the rig stands at x = 0, ground y = 0)
      // the ink scale is not known until the fit; build with a provisional scale, then fix stroke widths
      const provisional = 1.3;
      this.props_ = [];
      const targets = {};
      const boxes = [];
      const s = sideSign;
      const usedOther = { wall: false };
      if (layout === 'desk') {
        const sit = pose === 'sit';
        const top = 131;
        const deskX0 = s > 0 ? 96 : -480, deskX1 = s > 0 ? 480 : -96;
        if (!kinds.includes('desk') || true) {
          const d = buildDesk(L.furniture, { x0: deskX0, x1: deskX1, top, drawer: true });
          boxes.push(d.box);
        }
        if (sit) { const c = buildChair(L.back, { dir: s, seatY: -82 }); boxes.push(c.box); }
        let onDesk = 0;
        for (const x of list) {
          if (x.kind === 'desk' || x.kind === 'chair') continue;
          let pr = null;
          if (x.kind === 'laptop' || x.kind === 'monitor') {
            if (x.kind === 'monitor') void 0;
            const hinge = x.kind === 'laptop' ? [s * 150, -118] : [s * 128, -120];
            pr = (x.kind === 'laptop' ? buildLaptop : buildMonitor)(this, L.props, { dir: s, top, hinge, screen: x.screen, inkScale: provisional });
            Object.assign(targets, pr.anchors);
            targets.prop = targets.prop || pr.anchors.screen;
          } else if (x.kind === 'mug') {
            const at = P3(s * (onDesk ? 400 : 360), top, -10);
            pr = buildMug(this, L.props, { at, inkScale: provisional });
            targets.mug = pr.anchors.mug;
            onDesk++;
          } else if (x.kind === 'timer') {
            const at = P3(s * 390, top, -40);
            pr = buildTimer(this, L.props, Object.assign({}, x, { at: [at[0], at[1] - 64], r: 58, inkScale: provisional }));
            targets.timer = pr.anchors.timer; targets.prop = targets.prop || targets.timer;
          } else if (x.kind === 'clock') {
            pr = buildClock(this, L.back, Object.assign({}, x, { at: [s * 390, -390], r: 56, inkScale: provisional }));
            targets.clock = pr.anchors.clock;
          } else if (x.kind === 'checklist') {
            pr = buildChecklist(this, L.back, Object.assign({}, x, { at: [s * 400, -400], inkScale: provisional }));
            targets.checklist = pr.anchors.checklist; targets.items = pr.anchors.items;
          } else if (x.kind === 'phone') {
            pr = null; // the phone lives in the hand (arms: scroll / phone)
          } else if (x.kind === 'door') {
            pr = buildDoor(this, L.back, { at: [-s * 300, 0] });
            targets.door = pr.anchors.door;
          }
          if (pr) { pr.kind = x.kind; this.props_.push(pr); boxes.push(pr.box); }
        }
      } else {
        let cursor = s * 235;
        for (const x of list) {
          let pr = null;
          if (x.kind === 'phone') continue;
          if (x.kind === 'clock' && (list.length > 1 || layout === 'center') && !usedOther.wall) {
            usedOther.wall = true;
            const ws = layout === 'center' ? s : -s;
            pr = buildClock(this, L.back, Object.assign({}, x, { at: [ws * 250, -370], r: 62, inkScale: provisional }));
            targets.clock = pr.anchors.clock;
          } else {
            const wEst = { checklist: 0, timer: 170, clock: 150, door: 200, mug: 80, laptop: 260, monitor: 260, desk: 300, chair: 120 }[x.kind];
            if (x.kind === 'checklist') {
              const [bw, bh] = checklistSize(x);
              const up = S.portrait && !this.props_.length;
              const cx = up ? s * bw * 0.22 : cursor + s * (bw / 2);
              pr = buildChecklist(this, L.back, Object.assign({}, x, { at: [cx, up ? -500 - bh / 2 : -250], inkScale: provisional }));
              cursor = cx + s * (bw / 2 + 70);
              targets.checklist = pr.anchors.checklist; targets.items = pr.anchors.items;
            } else if (x.kind === 'timer') {
              const up = S.portrait && !this.props_.length;
              const cx = up ? s * 150 : cursor + s * wEst / 2;
              pr = buildTimer(this, L.back, Object.assign({}, x, { at: [cx, up ? -610 : -250], r: 80, inkScale: provisional }));
              targets.timer = pr.anchors.timer; targets.button = pr.anchors.button; cursor = cx + s * (wEst / 2 + 70);
            } else if (x.kind === 'clock') {
              const up = S.portrait && !this.props_.length;
              const cx = up ? s * 150 : cursor + s * wEst / 2;
              pr = buildClock(this, L.back, Object.assign({}, x, { at: [cx, up ? -600 : -300], r: 72, inkScale: provisional }));
              targets.clock = pr.anchors.clock; cursor = cx + s * (wEst / 2 + 70);
            } else if (x.kind === 'door') {
              const cx = cursor + s * 100;
              pr = buildDoor(this, L.back, { at: [cx, 0], open: x.open });
              targets.door = pr.anchors.door; targets.button = pr.anchors.button; cursor = cx + s * 170;
            } else if (x.kind === 'mug') {
              pr = null; // a mug needs a desk; ignore in stand layout
            } else if (x.kind === 'chair') {
              const c = buildChair(L.back, { dir: -s, seatY: -88 });
              c.g.setAttribute('transform', `translate(${n1(cursor + s * 60)},0)`);
              const bx = c.box; pr = { g: c.g, box: [bx[0] + cursor + s * 60, bx[1], bx[2] + cursor + s * 60, bx[3]], render() {} };
              cursor += s * 180;
            } else {
              throw new Error(`Scene "${this.id}": prop "${x.kind}" needs the desk layout (add "desk" or use layout "desk")`);
            }
            if (pr && !targets.prop) targets.prop = pr.anchors ? Object.values(pr.anchors).find((v) => Array.isArray(v) && typeof v[0] === 'number') : null;
          }
          if (pr) { pr.kind = x.kind; this.props_.push(pr); boxes.push(pr.box); }
        }
      }
      if (targets.items && !targets.prop) targets.prop = targets.checklist;

      // ---- rig
      const arms = p.arms || 'rest';
      this.rig = new Rig(this, L.rig, { pose, dir, mood: p.mood, look: p.look, arms, armsArgs: p.armsArgs || {}, targets, inkScale: provisional });
      const rigBox = [-150, this.rig.headC[1] - R.head - 36, 150, 4];
      if (pose === 'sit') rigBox[0] = -80;
      boxes.push(rigBox);

      // ---- symbol placements (and reserve their space)
      this.syms = [];
      const symDefs = this.collectSymbolDefs();
      this.symSide = p.bubbleSide === 'left' ? -1 : p.bubbleSide === 'right' ? 1 : (layout === 'center' ? 1 : -s);
      for (const sd of symDefs) { const b = this.symbolBox(sd); if (b) boxes.push(b); }

      // ---- fit composition into the stage area
      const bb = boxes.reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])], [1e9, 1e9, -1e9, -1e9]);
      const padX = S.portrait ? 70 : 150;
      const topY = (S.portrait ? 150 : 56) + (capH ? capH + (S.portrait ? 70 : 44) : 0);
      const botY = S.H - (S.portrait ? 300 : 96);
      const aw = S.W - padX * 2, ah = botY - topY;
      const maxS = S.portrait ? 2.25 : 1.5;
      const k = Math.min(aw / (bb[2] - bb[0]), ah / (bb[3] - bb[1]), maxS);
      const ox = S.W / 2 - ((bb[0] + bb[2]) / 2) * k;
      const oy = topY + ah / 2 - ((bb[1] + bb[3]) / 2) * k;
      this.k = k; this.ox = ox; this.oy = oy; this.bb = bb;
      attr(this.comp, 'transform', `translate(${n1(ox)},${n1(oy)}) scale(${k.toFixed(4)})`);
      attr(this.comp, 'stroke-width', (SW / k).toFixed(3));
      // fix ink widths for elements built with the provisional scale
      for (const e of this.comp.querySelectorAll('[stroke-width]')) {
        const v = parseFloat(e.getAttribute('stroke-width'));
        if (e === this.comp) continue;
        e.setAttribute('stroke-width', (v * provisional / k).toFixed(3));
      }
      this.rig.inkScale = k;
      // floor line
      if (p.floor !== false) {
        const fx0 = bb[0] - 50, fx1 = bb[2] + 50;
        svgEl('path', { d: `M${n1(fx0)},2L${n1(fx1)},2` }, L.floor);
      }
      // initial symbols (visible from the cut)
      for (const sd of (p.symbols || [])) {
        const def = typeof sd === 'string' ? { kind: sd } : sd;
        this.addSymbol(null, def.delay ?? 0.35, def);
      }
      this.extraBlinks = [];
    }
    collectSymbolDefs() {
      const out = [];
      for (const sd of this.props.symbols || []) out.push(typeof sd === 'string' ? { kind: sd } : sd);
      for (const b of this.scene.spec.beats || []) {
        const tg = Array.isArray(b.target) ? b.target : [b.target];
        if (!tg.includes(this.id)) continue;
        const a = b.args || {};
        if (b.action === 'symbol') out.push(a);
        if (b.action === 'bubble') out.push(Object.assign({ kind: 'bubble' }, a));
        if (b.action === 'victory' && a.sparkles !== false) out.push({ kind: 'sparkles' });
      }
      return out;
    }
    /** Symbol geometry in local units (relative to the head). */
    symbolGeom(def) {
      const h = this.rig.headC, r = R.head, sd = def.side === 'left' ? -1 : def.side === 'right' ? 1 : this.symSide;
      const away = this.dir ? -this.dir : -1;
      const dx = def.dx || 0, dy = def.dy || 0;
      switch (def.kind) {
        case 'bubble': {
          const txt = def.text || '';
          const tw = txt ? Math.max(...String(txt).split('\n').map((l) => textWidth(l, `400 46px ${HAND}`))) : 0;
          const lines = txt ? String(txt).split('\n').length : 1;
          const rx = Math.max(118, Math.min(300, tw / 2 + 62)), ry = Math.max(78, lines * 30 + 44);
          if (this.scene.portrait) {
            const c = [h[0] + sd * Math.min(90, rx * 0.4) + dx, h[1] - r - ry - 92 + dy];
            return { c, rx, ry, box: [c[0] - rx - 18, c[1] - ry - 18, c[0] + rx + 18, c[1] + ry + 18], tail: [[h[0] + sd * r * 0.55, h[1] - r - 22], [h[0] + sd * r * 0.8, h[1] - r - 58]] };
          }
          const c = [h[0] + sd * (r + rx * 0.72 + 50) + dx, h[1] - r - ry * 0.5 - 30 + dy];
          return { c, rx, ry, box: [c[0] - rx - 18, c[1] - ry - 18, c[0] + rx + 18, c[1] + ry + 18], tail: [[h[0] + sd * (r * 0.75), h[1] - r * 0.95], [h[0] + sd * (r + 26), h[1] - r - 18]] };
        }
        case 'stress': { const c = [h[0] + dx, h[1] - r - 80 + dy]; return { c, box: [c[0] - 70, c[1] - 40, c[0] + 70, c[1] + 40] }; }
        case 'sweat': { const c = [h[0] + away * (r + 18) + dx, h[1] - 18 + dy]; return { c, side: away, box: [c[0] - 30, c[1] - 30, c[0] + 30, c[1] + 50] }; }
        case 'exclaim': case 'question': { const c = [h[0] + sd * (r + 34) + dx, h[1] - r - 26 + dy]; return { c, box: [c[0] - 28, c[1] - 50, c[0] + 28, c[1] + 46] }; }
        case 'zzz': { const c = [h[0] + sd * (r + 20) + dx, h[1] - r + dy]; return { c, sd, box: [c[0] - 10, c[1] - 150, c[0] + sd * 110, c[1] + 10].sort((a, b) => 0) }; }
        case 'idea': { const c = [h[0] + dx, h[1] - r - 84 + dy]; return { c, box: [c[0] - 62, c[1] - 62, c[0] + 62, c[1] + 56] }; }
        case 'heart': case 'music': { const c = [h[0] + sd * (r + 44) + dx, h[1] - r - 20 + dy]; return { c, box: [c[0] - 40, c[1] - 40, c[0] + 40, c[1] + 40] }; }
        case 'check': {
          const c = def.at && this.rig.targets[def.at] ? this.rig.targets[def.at] : [h[0] + sd * (r + 70) + dx, h[1] - r - 10 + dy];
          return { c, box: [c[0] - 48, c[1] - 48, c[0] + 48, c[1] + 48] };
        }
        case 'sparkles': {
          const top = h[1] - r;
          const a = this.layout === 'center' ? 1 : this.symSide;
          const pts = [[h[0] + a * 215, h[1] + 20], [h[0] + a * 175, h[1] - 140], [h[0] + a * 30, top - 85], [h[0] - a * 140, top - 60], [h[0] + a * 240, h[1] - 50]];
          if (this.layout === 'center') pts[4] = [h[0] - 215, h[1] + 20];
          const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
          return { pts, box: [Math.min(...xs) - 26, Math.min(...ys) - 26, Math.max(...xs) + 26, Math.max(...ys) + 26] };
        }
        default: throw new Error(`Scene "${this.id}": unknown symbol "${def.kind}" (${SYMBOLS.join(', ')})`);
      }
    }
    symbolBox(def) {
      const g = this.symbolGeom(def);
      const b = g.box;
      return [Math.min(b[0], b[2]), Math.min(b[1], b[3]), Math.max(b[0], b[2]), Math.max(b[1], b[3])];
    }
    /** Create a symbol (DOM built now); visible from `at` (null => from each cut + delay) until `until`. */
    addSymbol(at, delay, def) {
      const G = this.symbolGeom(def);
      const g = svgEl('g', { visibility: 'hidden' }, this.L.symbols);
      const inner = svgEl('g', {}, g);
      const sym = { kind: def.kind, at, delay: delay || 0, until: def.hold != null && at != null ? at + def.hold : null, g, inner, G, def, parts: {} };
      const k = this.k;
      switch (def.kind) {
        case 'bubble': {
          svgEl('circle', { cx: n1(G.tail[0][0]), cy: n1(G.tail[0][1]), r: 9, fill: PAPER }, inner);
          svgEl('circle', { cx: n1(G.tail[1][0]), cy: n1(G.tail[1][1]), r: 15, fill: PAPER }, inner);
          svgEl('path', { d: cloudPath(G.c[0], G.c[1], G.rx, G.ry, Math.round(8 + G.rx / 45), hashStr(this.id + (def.text || def.icon || ''))), fill: PAPER }, inner);
          if (def.icon) {
            const ig = iconGroup(inner, def.icon, G.c[0], G.c[1], 84, k);
            if (!ig) throw new Error(`Scene "${this.id}": unknown icon "${def.icon}" (${Object.keys(ICONS()).join(', ')})`);
          } else if (def.text) {
            const lines = String(def.text).split('\n');
            lines.forEach((ln, i) => {
              const tx = svgEl('text', { x: n1(G.c[0]), y: n1(G.c[1] + 15 + (i - (lines.length - 1) / 2) * 50), 'text-anchor': 'middle', fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': 46 }, inner);
              tx.textContent = ln;
            });
          }
          sym.origin = G.tail[0];
          break;
        }
        case 'stress':
          sym.parts.path = svgEl('path', {}, inner);
          sym.origin = G.c;
          break;
        case 'sweat':
          sym.parts.drops = [0, 1].map(() => svgEl('path', { fill: PAPER }, inner));
          sym.origin = G.c;
          break;
        case 'exclaim':
          svgEl('path', { d: `M${n1(G.c[0])},${n1(G.c[1] - 40)}L${n1(G.c[0] - 2)},${n1(G.c[1] + 14)}`, 'stroke-width': (SW * 1.7 / k).toFixed(3) }, inner);
          svgEl('circle', { cx: n1(G.c[0] - 3), cy: n1(G.c[1] + 36), r: 4.5, fill: INK }, inner);
          sym.origin = [G.c[0], G.c[1] + 40];
          break;
        case 'question':
          svgEl('path', { d: `M${n1(G.c[0] - 20)},${n1(G.c[1] - 24)}C${n1(G.c[0] - 18)},${n1(G.c[1] - 50)} ${n1(G.c[0] + 24)},${n1(G.c[1] - 50)} ${n1(G.c[0] + 20)},${n1(G.c[1] - 22)}C${n1(G.c[0] + 17)},${n1(G.c[1] - 6)} ${n1(G.c[0])},${n1(G.c[1] - 4)} ${n1(G.c[0])},${n1(G.c[1] + 14)}`, 'stroke-width': (SW * 1.5 / k).toFixed(3) }, inner);
          svgEl('circle', { cx: n1(G.c[0]), cy: n1(G.c[1] + 36), r: 4.5, fill: INK }, inner);
          sym.origin = [G.c[0], G.c[1] + 40];
          break;
        case 'zzz':
          sym.parts.zs = [0, 1, 2].map(() => { const t = svgEl('text', { fill: INK, stroke: 'none', 'font-family': HAND, 'font-size': 44 }, inner); t.textContent = 'z'; return t; });
          sym.origin = G.c;
          break;
        case 'idea': {
          iconGroup(inner, 'lightbulb', G.c[0], G.c[1], 78, k);
          let d = '';
          for (const a of [-60, -25, 25, 60, 0]) {
            const ra = (a - 90) * D2R;
            d += `M${pt([G.c[0] + Math.cos(ra) * 52, G.c[1] + Math.sin(ra) * 52])}L${pt([G.c[0] + Math.cos(ra) * 66, G.c[1] + Math.sin(ra) * 66])}`;
          }
          svgEl('path', { d }, inner);
          sym.origin = [G.c[0], G.c[1] + 40];
          break;
        }
        case 'heart': iconGroup(inner, 'heart', G.c[0], G.c[1], 64, k); sym.origin = G.c; break;
        case 'music': iconGroup(inner, 'music', G.c[0], G.c[1], 64, k); sym.origin = G.c; break;
        case 'check':
          svgEl('circle', { cx: n1(G.c[0]), cy: n1(G.c[1]), r: 38, fill: PAPER }, inner);
          sym.parts.ck = svgEl('path', { d: `M${n1(G.c[0] - 17)},${n1(G.c[1] + 1)}L${n1(G.c[0] - 4)},${n1(G.c[1] + 14)}L${n1(G.c[0] + 19)},${n1(G.c[1] - 14)}`, 'stroke-width': (SW * 1.3 / k).toFixed(3) }, inner);
          sym.origin = G.c;
          break;
        case 'sparkles':
          sym.parts.stars = G.pts.map((p, i) => svgEl('path', { d: sparkPath(p[0], p[1], i % 2 ? 16 : 22), fill: PAPER }, inner));
          sym.origin = null;
          break;
        default: throw new Error(`Scene "${this.id}": unknown symbol "${def.kind}" (${SYMBOLS.join(', ')})`);
      }
      this.syms.push(sym);
      return sym;
    }

    // ---------- actions (compile)
    a_cut(at) { super.a_cut(at); }
    a_mood(at, dur, e, args) { this.rig.setMood(at, args.mood || args.to || 'neutral', dur); }
    a_face(at, dur, e, args) { this.a_mood(at, dur, e, args); }
    a_brows(at, dur, e, args) {
      const b = BROWS[args.state || args.to];
      if (!b) throw new Error(`Scene "${this.id}": brows state "${args.state}" (${Object.keys(BROWS).join(', ')})`);
      this.rig.browsT.to(at, b.slice(), dur, 'smooth');
    }
    a_mouth(at, dur, e, args) {
      const m = MOUTHS[args.shape || args.to];
      if (!m) throw new Error(`Scene "${this.id}": mouth shape "${args.shape}" (${Object.keys(MOUTHS).join(', ')})`);
      this.rig.mouthT.to(at, m.slice(), dur, 'smooth');
    }
    a_talk(at, dur) { this.rig.talks.push({ at, dur }); }
    a_blink(at) { this.extraBlinks.push(at); }
    a_look(at, dur, e, args) { this.rig.lookT.to(at, this.rig.lookVec(args.dir ?? args.at ?? args.to ?? 'camera'), dur, 'smooth'); }
    a_turn(at, dur, e, args) {
      const v = args.to ?? args.dir;
      const f = v === 'left' ? -0.62 : v === 'right' ? 0.62 : typeof v === 'number' ? clamp(v, -1, 1) : 0;
      this.rig.faceT.to(at, f, dur, 'smooth');
    }
    a_nod(at, dur, e, args) { this.rig.nods.push({ at, dur, times: args.times ?? 2, kind: 'nod' }); }
    a_shake(at, dur, e, args) { this.rig.nods.push({ at, dur, times: args.times ?? 2, kind: 'shake' }); }
    a_tilt(at, dur, e, args) { this.rig.tiltT.to(at, clamp(args.angle ?? 8, -25, 25), dur, 'smooth'); }
    a_arms(at, dur, e, args) { this.rig.setArms(at, args.pose || args.to || 'rest', dur, args); }
    a_type(at, dur, e, args) { this.rig.setArms(at, 'type', dur, args); if (args.look !== false) this.a_look(at, 0.25, e, { dir: 'screen' }); }
    a_scroll(at, dur, e, args) { this.rig.setArms(at, 'scroll', dur, args); if (args.look !== false) this.a_look(at, 0.25, e, { dir: 'phone' }); }
    a_point(at, dur, e, args) {
      this.rig.setArms(at, 'point', dur, args);
      if (args.look !== false) this.rig.lookT.to(at, this.rig.lookVec(Array.isArray(args.at) ? null : args.at || 'prop'), 0.25, 'smooth');
    }
    a_press(at, dur, e, args) { this.rig.setArms(at, 'press', dur, Object.assign({ at: 'button' }, args)); }
    a_wave(at, dur, e, args) { this.rig.setArms(at, 'wave', dur, args); }
    a_think(at, dur, e, args) { this.rig.setArms(at, 'think', dur, args); if (args.look !== false) this.a_look(at, 0.3, e, { dir: 'up-right' }); }
    a_shrug(at, dur, e, args) { this.rig.setArms(at, 'shrug', dur, args); }
    a_rest(at, dur, e, args) { this.rig.setArms(at, 'rest', dur, args); }
    a_facepalm(at, dur, e, args) { this.rig.setArms(at, 'facepalm', dur, args); if (args.mood !== false) this.rig.setMood(at, args.mood || 'stressed', 0.3); }
    a_hips(at, dur, e, args) { this.rig.setArms(at, 'hips', dur, args); }
    a_clap(at, dur, e, args) { this.rig.setArms(at, 'clap', dur, args); }
    a_victory(at, dur, e, args) {
      this.rig.setArms(at, 'victory', dur, args);
      if (args.mood !== false) this.rig.setMood(at, args.mood || 'happy', 0.25);
      this.a_look(at, 0.2, e, { dir: 'camera' });
      if (args.sparkles !== false) this.addSymbol(at + 0.1, 0, { kind: 'sparkles', hold: args.hold });
    }
    a_symbol(at, dur, e, args) {
      if (!args.kind) throw new Error(`Scene "${this.id}": symbol needs args.kind (${SYMBOLS.join(', ')})`);
      const s = this.addSymbol(at, 0, args); s.dur = dur;
    }
    a_bubble(at, dur, e, args) { const s = this.addSymbol(at, 0, Object.assign({ kind: 'bubble' }, args)); s.dur = dur; }
    a_clear(at, dur, e, args) {
      for (const s of this.syms) {
        if (args.kind && s.kind !== args.kind) continue;
        if (s.at != null && s.at > at) continue;
        if (s.until == null || s.until > at) { s.until = at; s.outDur = dur; }
      }
    }
    findProp(kind, fallback) {
      const p = this.props_.find((x) => x.kind === kind || (fallback && fallback.includes(x.kind)));
      if (!p) throw new Error(`Scene "${this.id}": no ${kind} prop in this scene (props: ${this.props_.map((x) => x.kind).join(', ') || 'none'})`);
      return p;
    }
    a_check(at, dur, e, args) {
      const p = this.props_.find((x) => x.kind === 'checklist');
      if (p) p.a_check(at, dur, args);
      else { const s = this.addSymbol(at, 0, Object.assign({ kind: 'check' }, args)); s.dur = dur; }
    }
    a_clock(at, dur, e, args) { this.findProp('clock').a_clock(at, dur, args); }
    a_timer(at, dur, e, args) { this.findProp('timer').a_timer(at, dur, args); }
    a_door(at, dur, e, args) { this.findProp('door').a_door(at, dur, args); }
    a_screen(at, dur, e, args) { this.findProp('laptop', ['monitor']).screen.setState(at, args.state || 'code', args.text); }
    a_caption(at, dur, e, args) { this.caption.add(at, args.text || ''); }

    // ---------- render
    render(t) {
      if (!super.render(t)) return;
      const start = this.shotStart(t);
      this.caption.render(t, start);
      this.rig.render(t);
      // typed code on laptop/monitor screens
      const typing = this.rig.loopAmp.type;
      for (const pr of this.props_) {
        if (pr.screen) {
          // integrate typing amount over time since the shot started (piecewise, sampled)
          let typed = null;
          if (this.rig.typeStarts.list.length) {
            const ev = this.rig.typeStarts.last(t);
            if (ev && ev.on) {
              const s0 = Math.max(start, ev.at);
              typed = Math.max(0, t - s0) * 55 * (typing.value(t) > 0.01 ? 1 : 0) + 20;
            }
          }
          pr.screen.render(t, typed);
        }
        if (pr.render) pr.render(t);
      }
      // symbols
      for (const s of this.syms) this.renderSymbol(s, t, start);
    }
    renderSymbol(s, t, shotStart) {
      const at = s.at == null ? shotStart + s.delay : s.at;
      if (t < at || (s.until != null && t > s.until + (s.outDur || 0.2))) { attr(s.g, 'visibility', 'hidden'); return; }
      attr(s.g, 'visibility', 'visible');
      const local = t - at;
      const pin = clamp(local / (s.dur || 0.3));
      let sc = getEase('outBack')(pin), op = Math.min(1, pin * 3);
      if (s.until != null && t > s.until) { const q = clamp((t - s.until) / (s.outDur || 0.2)); sc *= 1 - 0.3 * q; op *= 1 - q; }
      const o = s.origin;
      if (o) attr(s.inner, 'transform', `translate(${n1(o[0])},${n1(o[1])}) scale(${Math.max(0.001, sc).toFixed(3)}) translate(${n1(-o[0])},${n1(-o[1])})`);
      attr(s.g, 'opacity', op.toFixed(3));
      const G = s.G, k = this.k;
      switch (s.kind) {
        case 'bubble': {
          const bob = Math.sin(local * 2.2) * 3;
          attr(s.g, 'transform', `translate(0,${n1(bob)})`);
          break;
        }
        case 'stress': attr(s.parts.path, 'd', scribblePath(G.c[0], G.c[1], 130, 70, Math.floor(local / 0.11))); break;
        case 'sweat':
          s.parts.drops.forEach((p, i) => {
            const ph = ((local / 1.15 + i * 0.5) % 1 + 1) % 1;
            const x = G.c[0] + G.side * i * 20, y = G.c[1] - 6 + i * 28 + ph * 26;
            const sz = (i ? 0.85 : 1.05) * Math.min(1, ph / 0.15, (1 - ph) / 0.2);
            attr(p, 'd', teardrop(x, y, Math.max(0.01, sz)));
          });
          break;
        case 'exclaim': case 'question': {
          const w = Math.sin(local * 5) * 5 * Math.exp(-local * 0.6);
          attr(s.g, 'transform', `rotate(${n1(w)},${n1(G.c[0])},${n1(G.c[1] + 40)})`);
          break;
        }
        case 'zzz':
          s.parts.zs.forEach((z, i) => {
            const ph = ((local / 2.4 + i / 3) % 1 + 1) % 1;
            attr(z, 'x', n1(G.c[0] + G.sd * (14 + ph * 70 + Math.sin(ph * 6) * 6)));
            attr(z, 'y', n1(G.c[1] - 10 - ph * 120));
            attr(z, 'font-size', n1(30 + ph * 26));
            attr(z, 'opacity', Math.min(1, Math.sin(Math.PI * ph) * 1.8).toFixed(3));
          });
          break;
        case 'check': window.CA.drawOn(s.parts.ck, clamp((local - 0.1) / 0.3)); break;
        case 'idea': {
          const b = 1 + 0.04 * Math.sin(local * 6);
          attr(s.g, 'transform', `translate(${n1(G.c[0])},${n1(G.c[1])}) scale(${b.toFixed(3)}) translate(${n1(-G.c[0])},${n1(-G.c[1])})`);
          break;
        }
        case 'heart': case 'music': attr(s.g, 'transform', `translate(0,${n1(Math.sin(local * 3) * 5)})`); break;
        case 'sparkles':
          s.parts.stars.forEach((p, i) => {
            const ph = local * 2.2 + i * 1.3;
            const sc2 = Math.max(0, Math.sin(ph)) * 0.6 + 0.4;
            const pin2 = getEase('outBack')(clamp((local - i * 0.07) / 0.3));
            const c = G.pts[i];
            attr(p, 'transform', `translate(${n1(c[0])},${n1(c[1])}) scale(${(sc2 * pin2).toFixed(3)}) translate(${n1(-c[0])},${n1(-c[1])})`);
          });
          break;
        default: break;
      }
      void k;
    }
  }
  register('Scene', Scene);

  // ------------------------------------------------------------------ Walkthrough
  class Walkthrough extends Shot {
    static defaults = { tabs: [], active: 0, caption: '', url: '', width: null, cursor: true };
    static actions = Object.assign({}, Shot.actions, {
      click: { dur: 0.45 }, zoom: { dur: 1.1, ease: 'smooth' }, unzoom: { dur: 0.9, ease: 'smooth' }, tab: { dur: 0.25 },
      scroll: { dur: 0.9, ease: 'smooth' }, move: { dur: 0.5, ease: 'smooth' }, caption: { dur: 0 }, highlight: { dur: 0.35 }, unhighlight: { dur: 0.25 },
    });
    build() {
      super.build();
      const S = this.scene, p = this.props;
      const tabs = (p.tabs.length ? p.tabs : [{ title: 'Untitled' }]).map((x) => (typeof x === 'string' ? { src: x, title: x.split('/').pop() } : x));
      this.tabs = tabs;
      this.root.classList.add('ss-walk');
      css(this.root, 'background', '#000000');
      this.caption = new Caption(this, this.root, 'ss-wcaption' + (S.portrait ? ' portrait' : ''));
      this.caption.add(-1e9, p.caption || '');
      const capH = p.caption ? this.caption.box.offsetHeight : 0;
      // window size: fit the content aspect into the available area
      const aspect = p.aspect || 16 / 10;
      const bar = 92;
      const top = (S.portrait ? 170 : 60) + (capH ? capH + (S.portrait ? 60 : 30) : 0);
      const bottom = S.H - (S.portrait ? 260 : 60);
      const maxW = S.W * (p.width || (S.portrait ? 0.92 : 0.84));
      const maxH = bottom - top;
      let ww = maxW, vh = ww / aspect;
      if (vh + bar > maxH) { vh = maxH - bar; ww = vh * aspect; }
      this.vw = ww; this.vh = vh;
      const wx = (S.W - ww) / 2, wy = top + (maxH - (vh + bar)) / 2;
      this.win = el('div', { class: 'ss-win', style: { left: wx + 'px', top: wy + 'px', width: ww + 'px', height: vh + bar + 'px' } }, this.root);
      const barEl = el('div', { class: 'ss-bar' }, this.win);
      const lights = el('div', { class: 'ss-lights' }, barEl);
      for (const c of ['#FF5F57', '#FEBC2E', '#28C840']) el('i', { style: { background: c } }, lights);
      const tabRow = el('div', { class: 'ss-tabs' }, barEl);
      this.tabEls = tabs.map((tb) => {
        const te = el('div', { class: 'ss-tab' }, tabRow);
        el('span', { class: 'ss-fav' }, te).textContent = (tb.title || '?').trim()[0] || '?';
        el('span', { class: 'ss-tt', text: tb.title || '' }, te);
        return te;
      });
      const addr = el('div', { class: 'ss-addr' }, barEl);
      this.urlEl = el('div', { class: 'ss-url' }, addr);
      this.view = el('div', { class: 'ss-view', style: { width: ww + 'px', height: vh + 'px' } }, this.win);
      this.layers = tabs.map((tb) => {
        const lay = el('div', { class: 'ss-page' }, this.view);
        const ghosts = [1.035, 1.075, 1.12].map(() => el('img', { class: 'ss-ghost' }, lay));
        const img = el('img', { class: 'ss-img' }, lay);
        if (tb.src) {
          const src = resolveSrc(S, tb.src);
          loadImg(img, src);
          for (const gimg of ghosts) loadImg(gimg, src);
        } else {
          css(lay, 'background', '#F4F4F5');
        }
        return { lay, img, ghosts };
      });
      // overlay (cursor, ripples, highlight boxes): content coords mapped through the zoom
      this.over = el('div', { class: 'ss-over', style: { width: ww + 'px', height: vh + 'px' } }, this.view);
      this.ripples = [];
      this.cursorEl = el('div', { class: 'ss-cursor' }, this.over,
        '<svg viewBox="0 0 28 28" width="34" height="34"><path d="M5 3 L5 22 L10 17.5 L13.6 25.2 L17 23.7 L13.5 16.2 L20 16.2 Z" fill="#111" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>');
      this.hlBoxes = [];
      // tracks
      this.tabEv = new Events().add(-1e9, { i: clamp(p.active | 0, 0, tabs.length - 1) });
      this.zoomT = new Track([0.5, 0.5, 1]);
      this.scrollT = tabs.map(() => new Track(0));
      this.curT = new Track(p.cursorAt || [0.62, 0.7]);
      this.curVis = new Track(0);
      this.switches = []; // {at, from, to}
    }
    contentToView(x, y, t) {
      // content coords (0-1 of the page image width/visible height) -> view px
      const [cx, cy, s] = this.zoomT.value(t);
      const { tx, ty } = this.zoomXform(cx, cy, s);
      return [tx + x * this.vw * s, ty + y * this.vh * s];
    }
    zoomXform(cx, cy, s) {
      const vw = this.vw, vh = this.vh;
      const tx = clamp(vw / 2 - cx * vw * s, vw - vw * s, 0);
      const ty = clamp(vh / 2 - cy * vh * s, vh - vh * s, 0);
      return { tx, ty };
    }
    a_tab(at, dur, e, args) {
      let i = args.index ?? args.to ?? args.tab;
      if (typeof i === 'string') i = this.tabs.findIndex((x) => (x.title || '').toLowerCase().includes(i.toLowerCase()));
      if (i == null || i < 0 || i >= this.tabs.length) throw new Error(`Walkthrough "${this.id}": no tab ${JSON.stringify(args)}`);
      const from = this.tabEv.last(at).i;
      this.tabEv.add(at + dur / 2, { i });
      this.switches.push({ at, dur, from, to: i });
      if (args.keepZoom !== true) this.zoomT.set(at + dur / 2, [0.5, 0.5, 1]);
    }
    a_zoom(at, dur, e, args) {
      const s = args.scale ?? 1.8;
      this.zoomT.to(at, [args.x ?? 0.5, args.y ?? 0.5, s], dur, e);
    }
    a_unzoom(at, dur, e) { this.zoomT.to(at, [0.5, 0.5, 1], dur, e); }
    a_scroll(at, dur, e, args) {
      const i = this.tabEv.last(at).i;
      this.scrollT[i].to(at, clamp(args.to ?? args.y ?? 0.5, 0, 1), dur, e);
    }
    a_move(at, dur, e, args) {
      this.curVis.to(at, 1, 0.2, 'out');
      this.curT.to(at, [args.x ?? 0.5, args.y ?? 0.5], dur, e);
    }
    a_click(at, dur, e, args) {
      const x = args.x ?? 0.5, y = args.y ?? 0.5;
      const travel = args.travel ?? dur;
      if (this.props.cursor !== false) {
        this.curVis.to(at - travel, 1, 0.2, 'out');
        this.curT.to(at - travel, [x, y], travel, 'smooth');
      }
      // the click lands at `at` (the spoken word); the cursor travels before it
      const r = el('div', { class: 'ss-ripple' }, this.over);
      this.ripples.push({ at, x, y, el: r });
    }
    a_highlight(at, dur, e, args) {
      const b = el('div', { class: 'ss-hl' }, this.over);
      this.hlBoxes.push({ at, dur, until: args.hold != null ? at + dur + args.hold : null, x: args.x ?? 0.3, y: args.y ?? 0.3, w: args.w ?? 0.3, h: args.h ?? 0.15, el: b });
    }
    a_unhighlight(at, dur) { for (const b of this.hlBoxes) if (b.at <= at && (b.until == null || b.until > at)) b.until = at; }
    a_caption(at, dur, e, args) { this.caption.add(at, args.text || ''); }
    render(t) {
      if (!super.render(t)) return;
      this.caption.render(t, this.shotStart(t));
      const cur = this.tabEv.last(t).i;
      // tabs strip + url
      this.tabEls.forEach((te, i) => te.classList.toggle('on', i === cur));
      const url = this.tabs[cur].url || this.props.url || '';
      if (this.urlEl.textContent !== url) this.urlEl.textContent = url;
      // zoom
      const [zx, zy, zs] = this.zoomT.value(t);
      const { tx, ty } = this.zoomXform(zx, zy, zs);
      // radial zoom-blur between tabs
      let blur = 0, push = 1, ghost = 0;
      for (const sw of this.switches) {
        if (t < sw.at || t > sw.at + sw.dur) continue;
        const u = (t - sw.at) / sw.dur;
        const k = u < 0.5 ? u / 0.5 : (1 - u) / 0.5; // 0 -> 1 (midpoint) -> 0
        const ke = getEase('inOut')(k);
        blur = 9 * ke; push = 1 + 0.12 * ke; ghost = ke;
      }
      this.layers.forEach((L, i) => {
        const on = i === cur;
        css(L.lay, 'visibility', on ? 'visible' : 'hidden');
        if (!on) return;
        const sc = this.scrollT[i].value(t);
        const ih = L.img.naturalWidth ? (L.img.naturalHeight / L.img.naturalWidth) * this.vw : this.vh;
        const sy = -Math.max(0, ih - this.vh) * sc;
        const base = `translate(${tx.toFixed(2)}px,${ty.toFixed(2)}px) scale(${zs.toFixed(4)})`;
        const pz = `translate(${(this.vw / 2).toFixed(1)}px,${(this.vh / 2).toFixed(1)}px) scale(${push.toFixed(4)}) translate(${(-this.vw / 2).toFixed(1)}px,${(-this.vh / 2).toFixed(1)}px)`;
        css(L.lay, 'transform', `${pz} ${base}`);
        css(L.img, 'transform', `translateY(${sy.toFixed(2)}px)`);
        css(L.img, 'filter', blur > 0.05 ? `blur(${blur.toFixed(2)}px) brightness(${(1 + 0.08 * ghost).toFixed(3)})` : 'none');
        L.ghosts.forEach((gi, j) => {
          const gs = 1 + (0.035 + j * 0.04) * ghost;
          css(gi, 'visibility', ghost > 0.02 ? 'visible' : 'hidden');
          css(gi, 'opacity', (ghost * (0.34 - j * 0.08)).toFixed(3));
          css(gi, 'transform', `translate(${(this.vw / 2).toFixed(1)}px,${(this.vh / 2 + sy).toFixed(1)}px) scale(${gs.toFixed(4)}) translate(${(-this.vw / 2).toFixed(1)}px,${(-this.vh / 2).toFixed(1)}px)`);
          css(gi, 'filter', `blur(${(blur * (1.3 + j * 0.5)).toFixed(2)}px)`);
        });
      });
      // overlay: ripples, cursor, highlight boxes (screen-space size, content-space position)
      const toV = (x, y) => [tx + x * this.vw * zs, ty + y * this.vh * zs];
      for (const r of this.ripples) {
        const age = t - r.at;
        if (age < 0 || age > 0.7) { css(r.el, 'visibility', 'hidden'); continue; }
        const p = getEase('out')(age / 0.7);
        const rad = 8 + 32 * p; // 40 px ripple
        const [vx, vy] = toV(r.x, r.y);
        css(r.el, 'visibility', 'visible');
        css(r.el, 'width', (rad * 2).toFixed(1) + 'px'); css(r.el, 'height', (rad * 2).toFixed(1) + 'px');
        css(r.el, 'transform', `translate(${(vx - rad).toFixed(1)}px,${(vy - rad).toFixed(1)}px)`);
        css(r.el, 'opacity', (1 - p).toFixed(3));
      }
      const cv = this.curVis.value(t);
      const [cx, cy] = this.curT.value(t);
      const [vx, vy] = toV(cx, cy);
      let press = 1;
      for (const r of this.ripples) { const b = bump(t, r.at - 0.06, 0.2); if (b > 0) press = Math.min(press, 1 - 0.18 * b); }
      css(this.cursorEl, 'visibility', cv > 0.01 && this.props.cursor !== false ? 'visible' : 'hidden');
      css(this.cursorEl, 'opacity', cv.toFixed(3));
      css(this.cursorEl, 'transform', `translate(${(vx - 6).toFixed(1)}px,${(vy - 4).toFixed(1)}px) scale(${press.toFixed(3)})`);
      for (const b of this.hlBoxes) {
        let v = prog(t, b.at, b.dur, 'out');
        if (b.until != null) v *= 1 - prog(t, b.until, 0.25, 'smooth');
        if (v <= 0.001) { css(b.el, 'visibility', 'hidden'); continue; }
        const [x0, y0] = toV(b.x, b.y), [x1, y1] = toV(b.x + b.w, b.y + b.h);
        const pad = 8 + (1 - v) * 10;
        css(b.el, 'visibility', 'visible');
        css(b.el, 'opacity', v.toFixed(3));
        css(b.el, 'transform', `translate(${(x0 - pad).toFixed(1)}px,${(y0 - pad).toFixed(1)}px)`);
        css(b.el, 'width', (x1 - x0 + pad * 2).toFixed(1) + 'px'); css(b.el, 'height', (y1 - y0 + pad * 2).toFixed(1) + 'px');
        css(b.el, 'background-position', `${(t * 26).toFixed(1)}px 0, ${(-t * 26).toFixed(1)}px 100%, 0 ${(-t * 26).toFixed(1)}px, 100% ${(t * 26).toFixed(1)}px`);
      }
    }
  }
  register('Walkthrough', Walkthrough);

  // ------------------------------------------------------------------ layout: every shot fills the canvas
  registerLayout('stickman-story', (S) => {
    for (const e of S.list) {
      if (e.constructor.isShot) { e.w = S.W; e.h = S.H; e.place(S.W / 2, S.H / 2); }
      else if (e.props.x != null && e.props.y != null) e.place(e.props.x * S.W, e.props.y * S.H);
      else e.place(S.W / 2, S.H / 2);
    }
  });
})();
