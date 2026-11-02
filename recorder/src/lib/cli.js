'use strict';
// CLI argument parsing (pure). Used by bin/clipagent-recorder and the Electron main process.
//
//   clipagent-recorder --session <DIR> [--camera <deviceId>|none|default] [--no-mic] [--display <id>]
//   clipagent-recorder --stop <DIR> [--no-wait] [--timeout <s>]
//   clipagent-recorder --list-devices
//   clipagent-recorder --help | --version

const USAGE = `Usage:
  clipagent-recorder --session <DIR> [--camera <deviceId>|none|default] [--no-mic] [--display <id>]
  clipagent-recorder --stop <DIR> [--no-wait] [--timeout <seconds>]
  clipagent-recorder --list-devices
  clipagent-recorder --help | --version

Writes the Take into <DIR>/take/ (screen.webm, camera.webm, mic.webm, events.jsonl, state.json, take.json).
Hotkeys: stop Ctrl+Alt+S (Cmd+Option+S on macOS), pause/resume Ctrl+Alt+P, Scratch Marker Ctrl+Alt+X.`;

class UsageError extends Error {}

// Flags Chromium/Electron/AppImage may inject into argv; ignored silently.
const PASSTHROUGH = /^--(no-sandbox|enable-|disable-|ozone-|inspect|remote-debugging|user-data-dir|lang=|v=|vmodule)/;

function parseArgs(argv) {
  const args = argv.slice();
  const opts = {
    mode: null, // record | stop | list-devices | help | version
    session: null,
    camera: null, // null = not given (use default if one exists), 'none', 'default' or a deviceId
    mic: true,
    display: null,
    wait: true,
    timeout: 60,
    warnings: [],
  };
  const needValue = (flag, i) => {
    const v = args[i + 1];
    if (v === undefined || (v.startsWith('--') && v.length > 2)) throw new UsageError(`${flag} requires a value`);
    return v;
  };
  const setMode = (m) => {
    if (opts.mode && opts.mode !== m) throw new UsageError(`conflicting options: --${opts.mode} and --${m}`);
    opts.mode = m;
  };
  for (let i = 0; i < args.length; i++) {
    let a = args[i];
    if (a === '--') continue;
    let inline = null;
    const eq = a.indexOf('=');
    if (a.startsWith('--') && eq > 0 && !PASSTHROUGH.test(a)) {
      inline = a.slice(eq + 1);
      a = a.slice(0, eq);
    }
    const value = (flag) => {
      if (inline !== null) return inline;
      const v = needValue(flag, i);
      i++;
      return v;
    };
    switch (a) {
      case '--session': setMode('record'); opts.session = value(a); break;
      case '--stop': setMode('stop'); opts.session = value(a); break;
      case '--list-devices': setMode('list-devices'); break;
      case '--help': case '-h': setMode('help'); break;
      case '--version': case '-v': setMode('version'); break;
      case '--camera': opts.camera = value(a); break;
      case '--no-camera': opts.camera = 'none'; break;
      case '--no-mic': opts.mic = false; break;
      case '--display': opts.display = value(a); break;
      case '--no-wait': opts.wait = false; break;
      case '--timeout': {
        const t = Number(value(a));
        if (!Number.isFinite(t) || t < 0) throw new UsageError('--timeout must be a number of seconds');
        opts.timeout = t;
        break;
      }
      default:
        if (PASSTHROUGH.test(a)) break;
        if (a.startsWith('-')) opts.warnings.push(`ignoring unknown option ${a}`);
        else opts.warnings.push(`ignoring unexpected argument ${a}`);
    }
  }
  if (!opts.mode) throw new UsageError('one of --session, --stop or --list-devices is required');
  if ((opts.mode === 'record' || opts.mode === 'stop') && !opts.session) throw new UsageError(`--${opts.mode === 'record' ? 'session' : 'stop'} requires a directory`);
  if (opts.camera === '') throw new UsageError('--camera requires a value');
  return opts;
}

/**
 * argv as the user typed it, for both `electron [switches] <appDir> -- args` (dev) and a packaged binary.
 * Everything after a `--` separator wins; otherwise in dev the first positional (the app dir) is dropped.
 */
function userArgv(processArgv, isPackaged) {
  const rest = processArgv.slice(1);
  const sep = rest.indexOf('--');
  if (sep >= 0) return rest.slice(sep + 1);
  if (isPackaged) return rest;
  const app = rest.findIndex((a) => !a.startsWith('-'));
  return app >= 0 ? [...rest.slice(0, app), ...rest.slice(app + 1)] : rest;
}

module.exports = { parseArgs, userArgv, UsageError, USAGE };
