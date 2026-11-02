'use strict';
// Key naming, privacy classification and hotkey matching (pure).
//
// Raw key names follow uiohook-napi's UiohookKey names ("A", "Escape", "CtrlRight", "ArrowUp", ...).
// The evdev table below maps Linux keycodes to the same names so both sources share one path.

const MODIFIERS = {
  Ctrl: 'ctrl', CtrlRight: 'ctrl',
  Alt: 'alt', AltRight: 'alt',
  Shift: 'shift', ShiftRight: 'shift',
  Meta: 'meta', MetaRight: 'meta',
};

// Linux input-event-codes.h -> uiohook-style names.
const EVDEV_KEYS = {
  1: 'Escape', 2: '1', 3: '2', 4: '3', 5: '4', 6: '5', 7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
  12: 'Minus', 13: 'Equal', 14: 'Backspace', 15: 'Tab',
  16: 'Q', 17: 'W', 18: 'E', 19: 'R', 20: 'T', 21: 'Y', 22: 'U', 23: 'I', 24: 'O', 25: 'P',
  26: 'BracketLeft', 27: 'BracketRight', 28: 'Enter', 29: 'Ctrl',
  30: 'A', 31: 'S', 32: 'D', 33: 'F', 34: 'G', 35: 'H', 36: 'J', 37: 'K', 38: 'L',
  39: 'Semicolon', 40: 'Quote', 41: 'Backquote', 42: 'Shift', 43: 'Backslash',
  44: 'Z', 45: 'X', 46: 'C', 47: 'V', 48: 'B', 49: 'N', 50: 'M',
  51: 'Comma', 52: 'Period', 53: 'Slash', 54: 'ShiftRight', 55: 'NumpadMultiply', 56: 'Alt', 57: 'Space',
  58: 'CapsLock', 59: 'F1', 60: 'F2', 61: 'F3', 62: 'F4', 63: 'F5', 64: 'F6', 65: 'F7', 66: 'F8', 67: 'F9', 68: 'F10',
  69: 'NumLock', 70: 'ScrollLock',
  71: 'Numpad7', 72: 'Numpad8', 73: 'Numpad9', 74: 'NumpadSubtract', 75: 'Numpad4', 76: 'Numpad5', 77: 'Numpad6',
  78: 'NumpadAdd', 79: 'Numpad1', 80: 'Numpad2', 81: 'Numpad3', 82: 'Numpad0', 83: 'NumpadDecimal',
  87: 'F11', 88: 'F12', 96: 'NumpadEnter', 97: 'CtrlRight', 98: 'NumpadDivide', 99: 'PrintScreen', 100: 'AltRight',
  102: 'Home', 103: 'ArrowUp', 104: 'PageUp', 105: 'ArrowLeft', 106: 'ArrowRight', 107: 'End', 108: 'ArrowDown',
  109: 'PageDown', 110: 'Insert', 111: 'Delete', 125: 'Meta', 126: 'MetaRight',
  183: 'F13', 184: 'F14', 185: 'F15', 186: 'F16', 187: 'F17', 188: 'F18', 189: 'F19', 190: 'F20',
  191: 'F21', 192: 'F22', 193: 'F23', 194: 'F24',
};

const EVDEV_BUTTONS = { 0x110: 'left', 0x111: 'right', 0x112: 'middle', 0x113: 'back', 0x114: 'forward' };

// Display names used in "shortcut" events.
const DISPLAY = {
  Escape: 'Esc', Enter: 'Enter', NumpadEnter: 'Enter', Tab: 'Tab', Space: 'Space', Backspace: 'Backspace',
  Delete: 'Delete', Insert: 'Insert', Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown',
  ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right', CapsLock: 'CapsLock',
  Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Semicolon: ';', Quote: "'", Backquote: '`',
  Backslash: '\\', Comma: ',', Period: '.', Slash: '/', PrintScreen: 'PrintScreen',
  NumpadMultiply: '*', NumpadAdd: '+', NumpadSubtract: '-', NumpadDecimal: '.', NumpadDivide: '/',
};

const MOD_LABELS = {
  darwin: { ctrl: 'Ctrl', alt: 'Option', shift: 'Shift', meta: 'Cmd' },
  win32: { ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', meta: 'Win' },
  linux: { ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', meta: 'Super' },
};

function isModifier(name) { return Object.prototype.hasOwnProperty.call(MODIFIERS, name); }
function modifierOf(name) { return MODIFIERS[name] || null; }

function displayName(name) {
  if (DISPLAY[name]) return DISPLAY[name];
  const m = /^Numpad(\d)$/.exec(name);
  if (m) return m[1];
  return name;
}

/** F1-F24, Esc, Enter, Tab: recorded as shortcuts even without a modifier. */
function isSpecialKey(name) {
  return /^F([1-9]|1\d|2[0-4])$/.test(name) || name === 'Escape' || name === 'Enter' || name === 'NumpadEnter' || name === 'Tab';
}

/**
 * Privacy filter for one key press.
 * name: uiohook-style key name (or null if unknown); mods: {ctrl, alt, shift, meta}.
 * Returns {type:'shortcut', keys:[...]}, {type:'typing'}, or null (bare modifier press: nothing to record).
 * Plain typing never yields the key: Shift alone does not make a shortcut (Shift+A is just a capital A).
 */
function classifyKey(name, mods, platform = process.platform) {
  if (name && isModifier(name)) return null;
  const strong = !!(mods.ctrl || mods.alt || mods.meta);
  if (!name) return { type: 'typing' };
  if (!strong && !isSpecialKey(name)) return { type: 'typing' };
  const labels = MOD_LABELS[platform] || MOD_LABELS.linux;
  const keys = [];
  for (const m of ['ctrl', 'alt', 'shift', 'meta']) if (mods[m]) keys.push(labels[m]);
  keys.push(displayName(name));
  return { type: 'shortcut', keys };
}

/** Recorder hotkeys: stop Ctrl+Alt+S (Cmd+Option+S on macOS), pause Ctrl+Alt+P, Scratch Marker Ctrl+Alt+X. */
const HOTKEYS = { S: 'stop', P: 'pause', X: 'marker' };
const ACCELERATORS = { stop: 'CommandOrControl+Alt+S', pause: 'CommandOrControl+Alt+P', marker: 'CommandOrControl+Alt+X' };

function matchHotkey(name, mods, platform = process.platform) {
  const primary = platform === 'darwin' ? mods.meta : mods.ctrl;
  const other = platform === 'darwin' ? mods.ctrl : mods.meta;
  if (!primary || !mods.alt || mods.shift || other) return null;
  return HOTKEYS[name] || null;
}

/** Map uiohook-napi's UiohookKey ({name: code}) to {code: name}, preferring the generic names. */
function invertUiohookKeys(UiohookKey) {
  const out = {};
  for (const [name, code] of Object.entries(UiohookKey || {})) if (!(code in out)) out[code] = name;
  return out;
}

module.exports = {
  EVDEV_KEYS, EVDEV_BUTTONS, ACCELERATORS,
  isModifier, modifierOf, isSpecialKey, displayName, classifyKey, matchHotkey, invertUiohookKeys,
};
