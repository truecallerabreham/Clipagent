'use strict';
// Display geometry helpers (pure). Displays use Electron's shape: {id, bounds:{x,y,width,height}, scaleFactor}.

function physicalSize(d) {
  return { width: Math.round(d.bounds.width * d.scaleFactor), height: Math.round(d.bounds.height * d.scaleFactor) };
}

/**
 * Pick the captured display. Order: explicit id, exact physical-size match of the captured track
 * (primary first), same aspect ratio, primary, first.
 */
function matchDisplay(displays, { id = null, width = 0, height = 0, primaryId = null } = {}) {
  if (!displays || !displays.length) return null;
  if (id !== null && id !== undefined) {
    const d = displays.find((x) => String(x.id) === String(id));
    if (d) return d;
  }
  const ordered = [...displays].sort((a, b) => (b.id === primaryId) - (a.id === primaryId));
  if (width && height) {
    const exact = ordered.find((d) => { const p = physicalSize(d); return p.width === width && p.height === height; });
    if (exact) return exact;
    const dip = ordered.find((d) => d.bounds.width === width && d.bounds.height === height);
    if (dip) return dip;
    const ar = width / height;
    const aspect = ordered.find((d) => Math.abs(d.bounds.width / d.bounds.height - ar) < 0.01);
    if (aspect) return aspect;
  }
  return ordered[0];
}

/** Bar window rect -> [x, y, w, h] as 0-1 of the display (clipped), or null if not on that display. */
function overlayRect(bar, displayBounds) {
  const x1 = Math.max(bar.x, displayBounds.x);
  const y1 = Math.max(bar.y, displayBounds.y);
  const x2 = Math.min(bar.x + bar.width, displayBounds.x + displayBounds.width);
  const y2 = Math.min(bar.y + bar.height, displayBounds.y + displayBounds.height);
  if (x2 <= x1 || y2 <= y1) return null;
  const r = (v) => Math.round(v * 10000) / 10000;
  return [
    r((x1 - displayBounds.x) / displayBounds.width),
    r((y1 - displayBounds.y) / displayBounds.height),
    r((x2 - x1) / displayBounds.width),
    r((y2 - y1) / displayBounds.height),
  ];
}

/**
 * The captured display's rect in the coordinate space global input hooks report:
 * macOS uses points (= Electron DIP), Windows physical pixels (via screen.dipToScreenRect),
 * X11 physical pixels (DIP * scaleFactor).
 */
function inputRect(display, platform, dipToScreenRect = null) {
  const b = display.bounds;
  if (platform === 'darwin') return { ...b };
  if (platform === 'win32' && dipToScreenRect) return dipToScreenRect(b);
  const s = display.scaleFactor || 1;
  return { x: Math.round(b.x * s), y: Math.round(b.y * s), width: Math.round(b.width * s), height: Math.round(b.height * s) };
}

/** Top-right placement for the control bar on a display's work area. */
function barPosition(workArea, size, margin = 16) {
  return {
    x: Math.round(workArea.x + workArea.width - size.width - margin),
    y: Math.round(workArea.y + margin),
    width: size.width,
    height: size.height,
  };
}

module.exports = { physicalSize, matchDisplay, overlayRect, inputRect, barPosition };
