'use strict';
// Child process (ELECTRON_RUN_AS_NODE) that reads keyboards and mice from /dev/input/event*.
// Runs out of the main process because reads on character devices block a libuv threadpool thread each.
// Messages to parent:
//   {type:'ready', devices:[{path,name,kind}], warning}
//   {type:'unavailable', reason, permission:boolean}
//   {type:'events', events:[[ts, type, code, value], ...]}   (EV_KEY and EV_REL only)

const fs = require('fs');
const { parseProcDevices, classifyDevice, InputEventParser, EV_KEY, EV_REL, REL_WHEEL } = require('../lib/evdev');

const send = (m) => { if (process.send) process.send(m); };

function main() {
  // Test hook: CLIPAGENT_EVDEV_PATHS="/path/a:keyboard,/path/b:mouse" bypasses device discovery.
  if (process.env.CLIPAGENT_EVDEV_PATHS) {
    const list = process.env.CLIPAGENT_EVDEV_PATHS.split(',').map((x) => {
      const i = x.lastIndexOf(':');
      return { path: x.slice(0, i), name: 'test', kind: x.slice(i + 1) };
    });
    return openAndRead(list);
  }
  let text;
  try {
    text = fs.readFileSync('/proc/bus/input/devices', 'utf8');
  } catch (e) {
    send({ type: 'unavailable', reason: `cannot read /proc/bus/input/devices (${e.code || e.message})`, permission: false });
    return false;
  }
  const candidates = parseProcDevices(text)
    .map((d) => ({ ...d, kind: classifyDevice(d) }))
    .filter((d) => d.kind);
  if (!candidates.length) {
    send({ type: 'unavailable', reason: 'no keyboard or mouse found in /proc/bus/input/devices', permission: false });
    return false;
  }
  return openAndRead(candidates.map((d) => ({ path: `/dev/input/${d.event}`, name: d.name, kind: d.kind })));
}

function openAndRead(candidates) {
  const opened = [];
  const denied = [];
  for (const d of candidates) {
    const p = d.path;
    try {
      const fd = fs.openSync(p, fs.constants.O_RDONLY);
      opened.push({ fd, path: p, name: d.name, kind: d.kind });
    } catch (e) {
      denied.push(`${p}: ${e.code || e.message}`);
    }
  }
  if (!opened.length) {
    const permission = denied.some((x) => /EACCES|EPERM/.test(x));
    send({ type: 'unavailable', reason: `cannot open input devices (${denied.join(', ')})`, permission });
    return false;
  }
  const kinds = new Set(opened.map((d) => d.kind));
  let warning = null;
  if (!kinds.has('keyboard')) warning = 'no readable keyboard: shortcuts and typing were not recorded';
  else if (!kinds.has('mouse')) warning = 'no readable mouse: clicks were not recorded';
  send({ type: 'ready', devices: opened.map(({ path, name, kind }) => ({ path, name, kind })), warning });

  let pending = [];
  let flushTimer = null;
  const flush = () => { flushTimer = null; if (pending.length) { send({ type: 'events', events: pending }); pending = []; } };

  for (const dev of opened) {
    const parser = new InputEventParser();
    const buf = Buffer.alloc(parser.size * 64);
    const loop = () => {
      fs.read(dev.fd, buf, 0, buf.length, null, (err, n) => {
        if (err || n === 0) {
          send({ type: 'log', message: `${dev.path} closed (${err ? err.code || err.message : 'eof'})` });
          return;
        }
        for (const e of parser.push(buf.subarray(0, n))) {
          if (e.type === EV_KEY || (e.type === EV_REL && e.code === REL_WHEEL)) pending.push([e.ts, e.type, e.code, e.value]);
        }
        if (pending.length && !flushTimer) flushTimer = setTimeout(flush, 5);
        loop();
      });
    };
    loop();
  }
}

process.on('disconnect', () => process.exit(0));
if (main() === false) setTimeout(() => process.exit(0), 200);
