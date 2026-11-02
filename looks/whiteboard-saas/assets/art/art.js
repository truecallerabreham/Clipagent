/* whiteboard-saas Look: original line-art kit (CC0, drawn for ClipAgent).
 * Every piece is a 200x200 viewBox of plain SVG shapes. HandDraw draws every stroked shape in
 * document order (the hand follows the pen), then reveals every filled shape with an angled
 * color wipe. Color slots are filled at build time:
 *   {{INK}} outline  {{A}} accent  {{A2}} accent tint  {{Y}} yellow  {{Y2}} yellow tint
 *   {{G}} green  {{G2}} green tint  {{R}} red  {{R2}} red tint  {{B}} blue  {{B2}} blue tint
 *   {{GR}} light gray  {{W}} white
 * Stroke attributes are added for you: any shape with stroke="{{INK}}" (or another slot) is drawn.
 */
(function () {
  'use strict';
  const S = 'stroke="{{INK}}"';
  const A = {};

  A.lightbulb = `
<path d="M70,128 C52,112 44,94 46,76 C49,46 74,26 100,26 C126,26 151,46 154,76 C156,94 148,112 130,128 C124,134 122,140 122,148 L78,148 C78,140 76,134 70,128 Z" fill="{{Y}}" ${S}/>
<rect x="78" y="148" width="44" height="26" rx="6" fill="{{GR}}" ${S}/>
<path d="M80,161 L120,161" fill="none" ${S}/>
<path d="M88,175 Q100,188 112,175" fill="none" ${S}/>
<path d="M68,74 C70,60 80,50 92,46" fill="none" stroke="{{W}}" stroke-width="7"/>
<path d="M100,4 L100,12" fill="none" ${S}/>
<path d="M30,34 L37,41" fill="none" ${S}/>
<path d="M170,34 L163,41" fill="none" ${S}/>
<path d="M14,84 L24,84" fill="none" ${S}/>
<path d="M176,84 L186,84" fill="none" ${S}/>`;

  A.rocket = `
<g transform="rotate(40 100 100)">
<path d="M70,84 C52,94 44,112 44,144 L70,126 Z" fill="{{A}}" ${S}/>
<path d="M130,84 C148,94 156,112 156,144 L130,126 Z" fill="{{A}}" ${S}/>
<path d="M100,14 C126,36 134,70 132,118 L68,118 C66,70 74,36 100,14 Z" fill="{{A2}}" ${S}/>
<circle cx="100" cy="66" r="15" fill="{{B}}" ${S}/>
<path d="M82,118 L118,118 L112,134 L88,134 Z" fill="{{GR}}" ${S}/>
<path d="M88,140 C86,156 94,172 100,190 C106,172 114,156 112,140 Z" fill="{{Y}}" ${S}/>
</g>`;

  A.chart = `
<rect x="48" y="118" width="26" height="54" rx="4" fill="{{A2}}" ${S}/>
<rect x="88" y="88" width="26" height="84" rx="4" fill="{{A2}}" ${S}/>
<rect x="128" y="56" width="26" height="116" rx="4" fill="{{A}}" ${S}/>
<path d="M28,22 L28,174 L182,174" fill="none" ${S}/>
<path d="M44,96 L78,66 L104,78 L158,26" fill="none" stroke="{{Y}}" stroke-width="9"/>
<path d="M136,26 L160,24 L158,48" fill="none" stroke="{{Y}}" stroke-width="9"/>`;

  A.user = `
<path d="M40,178 C40,136 66,114 100,114 C134,114 160,136 160,178 Z" fill="{{A}}" ${S}/>
<circle cx="100" cy="68" r="34" fill="{{A2}}" ${S}/>`;

  A.team = `
<path d="M14,170 C14,138 32,122 56,122 C80,122 98,138 98,170 Z" fill="{{A2}}" ${S}/>
<circle cx="56" cy="88" r="24" fill="{{A2}}" ${S}/>
<path d="M102,170 C102,138 120,122 144,122 C168,122 186,138 186,170 Z" fill="{{A2}}" ${S}/>
<circle cx="144" cy="88" r="24" fill="{{A2}}" ${S}/>
<path d="M52,180 C52,136 74,116 100,116 C126,116 148,136 148,180 Z" fill="{{A}}" ${S}/>
<circle cx="100" cy="72" r="30" fill="{{W}}" ${S}/>`;

  A.gear = `
<path d="M154.9,88.9 L171.4,90.7 L171.4,109.3 L154.9,111.1 L151.7,121.4 L146.7,130.9 L157.1,143.9 L143.9,157.1 L130.9,146.7 L121.4,151.7 L111.1,154.9 L109.3,171.4 L90.7,171.4 L88.9,154.9 L78.6,151.7 L69.1,146.7 L56.1,157.1 L42.9,143.9 L53.3,130.9 L48.3,121.4 L45.1,111.1 L28.6,109.3 L28.6,90.7 L45.1,88.9 L48.3,78.6 L53.3,69.1 L42.9,56.1 L56.1,42.9 L69.1,53.3 L78.6,48.3 L88.9,45.1 L90.7,28.6 L109.3,28.6 L111.1,45.1 L121.4,48.3 L130.9,53.3 L143.9,42.9 L157.1,56.1 L146.7,69.1 L151.7,78.6 Z" fill="{{A2}}" ${S}/>
<circle cx="100" cy="100" r="22" fill="{{W}}" ${S}/>`;

  A.money = `
<rect x="20" y="50" width="160" height="100" rx="12" fill="{{G2}}" ${S}/>
<circle cx="100" cy="100" r="28" fill="{{G}}" ${S}/>
<path d="M111,88 C107,81 93,81 91,89 C89,98 111,100 109,111 C107,119 93,120 89,112" fill="none" ${S}/>
<path d="M100,76 L100,124" fill="none" ${S}/>
<path d="M40,72 L52,72" fill="none" ${S}/>
<path d="M148,128 L160,128" fill="none" ${S}/>`;

  A.clock = `
<circle cx="100" cy="102" r="74" fill="{{Y2}}" ${S}/>
<path d="M100,40 L100,50" fill="none" ${S}/>
<path d="M162,102 L152,102" fill="none" ${S}/>
<path d="M100,164 L100,154" fill="none" ${S}/>
<path d="M38,102 L48,102" fill="none" ${S}/>
<path d="M100,102 L100,66" fill="none" ${S}/>
<path d="M100,102 L128,118" fill="none" stroke="{{A}}"/>
<circle cx="100" cy="102" r="6" fill="{{INK}}"/>`;

  A.cloud = `
<path d="M56,150 C28,150 20,122 34,108 C42,98 54,96 62,98 C64,70 88,52 112,56 C132,60 144,74 148,90 C168,88 184,104 182,124 C180,142 166,150 150,150 Z" fill="{{B2}}" ${S}/>
<path d="M72,98 C76,84 88,76 100,76" fill="none" stroke="{{W}}" stroke-width="7"/>`;

  A.database = `
<path d="M42,46 L42,154 C42,166 68,176 100,176 C132,176 158,166 158,154 L158,46 Z" fill="{{A2}}"/>
<ellipse cx="100" cy="46" rx="58" ry="20" fill="{{A}}" ${S}/>
<path d="M42,46 L42,154 C42,166 68,176 100,176 C132,176 158,166 158,154 L158,46" fill="none" ${S}/>
<path d="M42,82 C42,94 68,104 100,104 C132,104 158,94 158,82" fill="none" ${S}/>
<path d="M42,118 C42,130 68,140 100,140 C132,140 158,130 158,118" fill="none" ${S}/>`;

  A.check = `
<circle cx="100" cy="100" r="74" fill="{{G}}" ${S}/>
<path d="M62,102 L90,130 L140,74" fill="none" ${S} stroke-width="11"/>`;

  A.cross = `
<circle cx="100" cy="100" r="74" fill="{{R}}" ${S}/>
<path d="M70,70 L130,130" fill="none" ${S} stroke-width="11"/>
<path d="M130,70 L70,130" fill="none" ${S} stroke-width="11"/>`;

  A.laptop = `
<rect x="40" y="44" width="120" height="84" rx="8" fill="{{B2}}" ${S}/>
<path d="M18,148 L182,148 L170,166 L30,166 Z" fill="{{GR}}" ${S}/>
<path d="M58,70 L110,70" fill="none" stroke="{{A}}"/>
<path d="M58,92 L138,92" fill="none" ${S}/>
<path d="M58,110 L120,110" fill="none" ${S}/>
<path d="M40,128 L40,148 M160,128 L160,148" fill="none" ${S}/>`;

  A.phone = `
<rect x="56" y="14" width="88" height="172" rx="16" fill="{{W}}" ${S}/>
<rect x="68" y="38" width="64" height="112" rx="6" fill="{{A2}}" ${S}/>
<path d="M88,26 L112,26" fill="none" ${S}/>
<circle cx="100" cy="168" r="7" fill="none" ${S}/>`;

  A.target = `
<circle cx="96" cy="104" r="72" fill="{{R2}}" ${S}/>
<circle cx="96" cy="104" r="46" fill="{{W}}" ${S}/>
<circle cx="96" cy="104" r="20" fill="{{R}}" ${S}/>
<path d="M96,104 L170,30" fill="none" ${S}/>
<path d="M150,26 L170,30 L174,50" fill="none" ${S}/>`;

  A.shield = `
<path d="M100,18 L164,42 C164,104 140,152 100,182 C60,152 36,104 36,42 Z" fill="{{A2}}" ${S}/>
<path d="M72,100 L94,122 L132,80" fill="none" stroke="{{A}}" stroke-width="10"/>`;

  A.lock = `
<path d="M66,92 L66,64 C66,42 80,28 100,28 C120,28 134,42 134,64 L134,92" fill="none" ${S}/>
<rect x="46" y="90" width="108" height="88" rx="14" fill="{{Y}}" ${S}/>
<circle cx="100" cy="126" r="10" fill="{{INK}}"/>
<path d="M100,130 L100,152" fill="none" ${S}/>`;

  A.mail = `
<rect x="22" y="46" width="156" height="108" rx="12" fill="{{B2}}" ${S}/>
<path d="M26,54 L100,110 L174,54" fill="none" ${S}/>`;

  A.star = `
<path d="M100,18 L124,72 L182,78 L138,118 L150,176 L100,146 L50,176 L62,118 L18,78 L76,72 Z" fill="{{Y}}" ${S}/>`;

  A.chat = `
<path d="M34,40 L166,40 C176,40 182,46 182,56 L182,122 C182,132 176,138 166,138 L86,138 L50,170 L54,138 L34,138 C24,138 18,132 18,122 L18,56 C18,46 24,40 34,40 Z" fill="{{A2}}" ${S}/>
<circle cx="66" cy="90" r="7" fill="{{INK}}"/>
<circle cx="100" cy="90" r="7" fill="{{INK}}"/>
<circle cx="134" cy="90" r="7" fill="{{INK}}"/>`;

  A.document = `
<path d="M48,16 L122,16 L156,50 L156,184 L48,184 Z" fill="{{W}}" ${S}/>
<path d="M122,16 L122,50 L156,50" fill="{{GR}}" ${S}/>
<path d="M68,82 L136,82" fill="none" stroke="{{A}}"/>
<path d="M68,108 L136,108" fill="none" ${S}/>
<path d="M68,134 L136,134" fill="none" ${S}/>
<path d="M68,160 L112,160" fill="none" ${S}/>`;

  A.cart = `
<path d="M14,36 L44,36 L66,128 L156,128" fill="none" ${S}/>
<path d="M50,58 L178,58 L164,108 L62,108 Z" fill="{{A2}}" ${S}/>
<circle cx="76" cy="156" r="14" fill="{{A}}" ${S}/>
<circle cx="146" cy="156" r="14" fill="{{A}}" ${S}/>`;

  A.megaphone = `
<path d="M40,80 L110,46 L110,150 L40,118 Z" fill="{{A2}}" ${S}/>
<rect x="20" y="78" width="22" height="42" rx="6" fill="{{A}}" ${S}/>
<path d="M58,120 L70,170 L92,170 L84,128" fill="{{GR}}" ${S}/>
<path d="M132,72 C144,84 144,112 132,124" fill="none" ${S}/>
<path d="M152,56 C176,80 176,116 152,140" fill="none" ${S}/>`;

  A.calendar = `
<rect x="26" y="36" width="148" height="140" rx="14" fill="{{W}}" ${S}/>
<path d="M26,74 L174,74 L174,50 C174,42 168,36 160,36 L40,36 C32,36 26,42 26,50 Z" fill="{{A}}" ${S}/>
<path d="M66,20 L66,50 M134,20 L134,50" fill="none" ${S}/>
<rect x="52" y="94" width="26" height="22" rx="4" fill="{{GR}}"/>
<rect x="88" y="94" width="26" height="22" rx="4" fill="{{GR}}"/>
<rect x="124" y="94" width="26" height="22" rx="4" fill="{{Y}}" ${S}/>
<rect x="52" y="132" width="26" height="22" rx="4" fill="{{GR}}"/>
<rect x="88" y="132" width="26" height="22" rx="4" fill="{{GR}}"/>`;

  A.server = `
<rect x="34" y="28" width="132" height="60" rx="10" fill="{{A2}}" ${S}/>
<rect x="34" y="112" width="132" height="60" rx="10" fill="{{A2}}" ${S}/>
<circle cx="62" cy="58" r="8" fill="{{G}}"/>
<circle cx="62" cy="142" r="8" fill="{{G}}"/>
<path d="M90,58 L142,58 M90,142 L142,142" fill="none" ${S}/>`;

  A.browser = `
<rect x="14" y="30" width="172" height="140" rx="12" fill="{{W}}" ${S}/>
<path d="M14,64 L186,64 L186,42 C186,35 181,30 174,30 L26,30 C19,30 14,35 14,42 Z" fill="{{GR}}" ${S}/>
<circle cx="34" cy="47" r="5" fill="{{R}}"/>
<circle cx="50" cy="47" r="5" fill="{{Y}}"/>
<circle cx="66" cy="47" r="5" fill="{{G}}"/>
<rect x="32" y="82" width="60" height="70" rx="6" fill="{{A2}}" ${S}/>
<path d="M108,88 L168,88 M108,110 L160,110 M108,132 L148,132" fill="none" ${S}/>`;

  A.arrowRight = `
<path d="M20,100 C70,92 120,104 170,98" fill="none" ${S}/>
<path d="M146,74 L172,98 L144,124" fill="none" ${S}/>`;

  A.heart = `
<path d="M100,170 C60,140 22,110 22,72 C22,46 42,30 64,30 C82,30 94,40 100,54 C106,40 118,30 136,30 C158,30 178,46 178,72 C178,110 140,140 100,170 Z" fill="{{R}}" ${S}/>`;

  A.puzzle = `
<path d="M30,60 L80,60 C76,36 124,36 120,60 L170,60 L170,104 C146,100 146,148 170,144 L170,180 L30,180 Z" fill="{{A2}}" ${S}/>`;

  A.coins = `
<ellipse cx="100" cy="150" rx="62" ry="20" fill="{{Y}}" ${S}/>
<path d="M38,150 L38,126 M162,150 L162,126" fill="none" ${S}/>
<ellipse cx="100" cy="126" rx="62" ry="20" fill="{{Y}}" ${S}/>
<path d="M38,126 L38,102 M162,126 L162,102" fill="none" ${S}/>
<ellipse cx="100" cy="102" rx="62" ry="20" fill="{{Y}}" ${S}/>
<path d="M38,102 L38,78 M162,102 L162,78" fill="none" ${S}/>
<ellipse cx="100" cy="78" rx="62" ry="20" fill="{{Y}}" ${S}/>
<path d="M80,78 L120,78" fill="none" ${S}/>`;

  window.WB_ART = A;
})();
