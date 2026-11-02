/* whiteboard-saas Look: original vector hand art (CC0, made for ClipAgent).
 * Three flat-shaded right hands, each drawn so that its "hot spot" sits at (0, 0):
 *   marker : holding a marker, (0,0) = felt tip.            Ink color slot: {{INK}}
 *   place  : two layers (back + thumb) gripping an asset's bottom edge, (0,0) = grip point on the edge.
 *   point  : pointing hand, (0,0) = index fingertip. Points straight up (rotate the group to aim).
 * Arms are long so they always leave the canvas. Colors: {{SKIN}}, {{SHADE}}, {{LINE}}, {{NAIL}}, {{SLEEVE}}, {{CUFF}}.
 */
(function () {
  'use strict';
  const H = {};

  // Hand holding a marker. Drawn with the marker vertical (tip up at 0,0, body going +y), then
  // rotated so the marker leans toward the lower right like a right hand writing on a board.
  H.marker = `
<g transform="rotate(-31)">
  <path d="M-10,330 C-14,290 -16,260 -10,222 L102,222 C108,262 108,300 104,332 Z" fill="{{SKIN}}"/>
  <path d="M-16,320 L110,320 L170,1500 L-60,1500 Z" fill="{{SLEEVE}}"/>
  <path d="M-17,318 L111,318 L114,356 L-19,356 Z" fill="{{CUFF}}"/>
  <path d="M60,356 L114,356 L170,1500 L120,1500 Z" fill="#000" opacity="0.10"/>
  <g>
    <path d="M-15,44 L-15,230 L15,230 L15,44 Z" fill="#2B2B33"/>
    <path d="M-9,52 L-9,220 L-4,220 L-4,52 Z" fill="#4A4A55"/>
    <path d="M-15,58 L15,58 L15,70 L-15,70 Z" fill="{{INK}}"/>
    <path d="M-15,44 L-9,18 L9,18 L15,44 Z" fill="#D5D6DE"/>
    <path d="M-9,18 L-6,18 L-10,44 L-15,44 Z" fill="#B7B8C2"/>
    <path d="M-7,19 L-5,5 C-3,-1 3,-1 5,5 L7,19 Z" fill="{{INK}}"/>
  </g>
  <path d="M2,110 C24,90 64,90 90,108 C114,126 122,166 118,206 C115,234 106,252 98,266 L-8,266 C-30,244 -52,210 -52,178 C-52,148 -28,122 2,110 Z" fill="{{SKIN}}"/>
  <path d="M96,126 C114,150 120,182 114,214 C110,236 102,252 96,266 L78,266 C92,236 100,196 96,126 Z" fill="{{SHADE}}"/>
  <path d="M-50,196 C-44,226 -28,250 -8,266 L8,266 C-14,246 -34,222 -50,196 Z" fill="{{SHADE}}" opacity="0.8"/>
  <path d="M44,156 C60,152 76,158 88,170" fill="none" stroke="{{LINE}}" stroke-width="3" stroke-linecap="round" opacity="0.5"/>
  <path d="M-30,150 C-14,138 6,130 24,128" fill="none" stroke="{{SHADE}}" stroke-width="27" stroke-linecap="round"/>
  <path d="M-30,146 C-14,134 6,127 24,125" fill="none" stroke="{{SKIN}}" stroke-width="20" stroke-linecap="round"/>
  <path d="M74,124 C56,100 32,78 13,56" fill="none" stroke="{{SHADE}}" stroke-width="28" stroke-linecap="round"/>
  <path d="M71,120 C54,98 31,76 13,55" fill="none" stroke="{{SKIN}}" stroke-width="22" stroke-linecap="round"/>
  <path d="M36,92 C42,86 46,84 50,84" fill="none" stroke="{{LINE}}" stroke-width="2.6" stroke-linecap="round" opacity="0.6"/>
  <path d="M5,52 C7,44 15,42 20,46 C23,50 22,56 18,60 Z" fill="{{NAIL}}"/>
  <path d="M-46,176 C-40,134 -27,102 -15,76" fill="none" stroke="{{SHADE}}" stroke-width="31" stroke-linecap="round"/>
  <path d="M-42,172 C-37,132 -25,100 -14,75" fill="none" stroke="{{SKIN}}" stroke-width="24" stroke-linecap="round"/>
  <path d="M-20,70 C-20,62 -12,60 -8,64 C-6,68 -8,76 -12,79 Z" fill="{{NAIL}}"/>
  <path d="M-38,126 C-32,124 -28,120 -26,114" fill="none" stroke="{{LINE}}" stroke-width="2.6" stroke-linecap="round" opacity="0.55"/>
</g>`;

  // Hand placing an asset: back layer sits behind the asset (palm, fingers hidden behind it),
  // front layer is the thumb pressing on the asset's bottom edge. Hand comes from below.
  H.placeBack = `
<g transform="rotate(14)">
  <path d="M-58,150 C-62,220 -60,300 -56,380 L64,380 C66,300 66,220 60,150 Z" fill="{{SKIN}}"/>
  <path d="M-66,330 L72,330 L110,1500 L-110,1500 Z" fill="{{SLEEVE}}"/>
  <path d="M-67,328 L73,328 L76,368 L-70,368 Z" fill="{{CUFF}}"/>
  <path d="M20,368 L76,368 L110,1500 L60,1500 Z" fill="#000" opacity="0.10"/>
  <path d="M-70,30 C-72,-10 -40,-26 0,-26 C46,-26 74,-6 72,40 C70,90 66,130 58,176 L-56,176 C-64,130 -68,80 -70,30 Z" fill="{{SKIN}}"/>
  <path d="M50,-14 C66,0 74,20 72,44 C70,92 64,136 56,176 L36,176 C48,120 56,60 50,-14 Z" fill="{{SHADE}}"/>
  <path d="M-40,96 C-20,104 10,106 34,98" fill="none" stroke="{{LINE}}" stroke-width="3" stroke-linecap="round" opacity="0.45"/>
</g>`;
  H.placeFront = `
<g transform="rotate(14)">
  <path d="M-66,66 C-74,30 -62,-6 -38,-18" fill="none" stroke="{{SHADE}}" stroke-width="34" stroke-linecap="round"/>
  <path d="M-62,62 C-70,28 -59,-4 -37,-15" fill="none" stroke="{{SKIN}}" stroke-width="27" stroke-linecap="round"/>
  <path d="M-44,-22 C-36,-30 -26,-28 -24,-20 C-23,-13 -30,-8 -38,-10 Z" fill="{{NAIL}}"/>
  <path d="M-70,26 C-64,22 -60,22 -56,24" fill="none" stroke="{{LINE}}" stroke-width="2.6" stroke-linecap="round" opacity="0.55"/>
</g>`;

  // Pointing hand, index finger straight up, tip at (0,0); wrist and sleeve below.
  H.point = `
<g>
  <path d="M-58,250 C-62,320 -60,380 -56,430 L70,430 C74,380 74,320 68,250 Z" fill="{{SKIN}}"/>
  <path d="M-64,400 L76,400 L88,1600 L-76,1600 Z" fill="{{SLEEVE}}"/>
  <path d="M-66,398 L78,398 L80,440 L-68,440 Z" fill="{{CUFF}}"/>
  <path d="M28,440 L80,440 L88,1600 L44,1600 Z" fill="#000" opacity="0.10"/>
  <path d="M-52,120 C-62,150 -64,210 -54,262 C-46,296 -20,310 10,310 C44,310 70,296 78,262 C86,226 86,180 80,150 C74,124 50,112 20,112 Z" fill="{{SKIN}}"/>
  <path d="M70,140 C84,170 86,220 78,260 C72,288 56,302 36,308 C56,284 66,240 70,140 Z" fill="{{SHADE}}"/>
  <path d="M-28,8 L-28,170" fill="none" stroke="{{SHADE}}" stroke-width="46" stroke-linecap="round"/>
  <path d="M-30,6 L-30,168" fill="none" stroke="{{SKIN}}" stroke-width="39" stroke-linecap="round"/>
  <path d="M-40,4 C-40,-6 -20,-6 -20,4 L-20,22 C-20,30 -40,30 -40,22 Z" fill="{{NAIL}}"/>
  <path d="M-42,74 C-34,78 -24,78 -16,74" fill="none" stroke="{{LINE}}" stroke-width="3" stroke-linecap="round" opacity="0.55"/>
  <path d="M-42,102 C-34,106 -24,106 -16,102" fill="none" stroke="{{LINE}}" stroke-width="3" stroke-linecap="round" opacity="0.4"/>
  <path d="M0,136 L58,136" fill="none" stroke="{{SHADE}}" stroke-width="36" stroke-linecap="round"/>
  <path d="M0,132 L56,132" fill="none" stroke="{{SKIN}}" stroke-width="29" stroke-linecap="round"/>
  <path d="M2,172 L60,172" fill="none" stroke="{{SHADE}}" stroke-width="36" stroke-linecap="round"/>
  <path d="M2,168 L58,168" fill="none" stroke="{{SKIN}}" stroke-width="29" stroke-linecap="round"/>
  <path d="M4,206 L58,206" fill="none" stroke="{{SHADE}}" stroke-width="34" stroke-linecap="round"/>
  <path d="M4,202 L56,202" fill="none" stroke="{{SKIN}}" stroke-width="27" stroke-linecap="round"/>
  <path d="M70,270 C60,236 36,214 4,206" fill="none" stroke="{{SHADE}}" stroke-width="36" stroke-linecap="round"/>
  <path d="M68,266 C58,234 34,212 4,202" fill="none" stroke="{{SKIN}}" stroke-width="29" stroke-linecap="round"/>
  <path d="M-8,196 C-12,206 -6,214 4,214 C10,212 12,204 8,198 Z" fill="{{NAIL}}"/>
</g>`;

  const DEFAULT_COLORS = {
    SKIN: '#F4C6A3', SHADE: '#E3A27C', LINE: '#B4744F', NAIL: '#FBE3D2',
    SLEEVE: '#5E17EB', CUFF: '#4A0FC2', INK: '#111111',
  };
  /** Fill the color slots. opts may override any slot (e.g. {INK: '#5E17EB', SLEEVE: '#1E1E1E'}). */
  function paint(name, opts) {
    const c = Object.assign({}, DEFAULT_COLORS, opts || {});
    return H[name].replace(/\{\{(\w+)\}\}/g, (_, k) => c[k] || '#000');
  }
  window.WB_HANDS = { art: H, paint, colors: DEFAULT_COLORS };
})();
