'use strict';
// Floating control bar: timer, pause/resume, stop, mic level, Scratch Marker flash.

const B = window.bar;
const el = {
  bar: document.getElementById('bar'),
  time: document.getElementById('time'),
  meter: document.getElementById('meter'),
  pause: document.getElementById('pause'),
  stop: document.getElementById('stop'),
  toast: document.getElementById('toast'),
};
const bars = [...el.meter.querySelectorAll('i')];

function fmt(sec) {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const pad = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${pad(m)}:${pad(s % 60)}`;
}

B.onState((s) => {
  el.bar.dataset.status = s.status;
  el.time.textContent = fmt(s.elapsed);
  el.meter.classList.toggle('off', !s.mic);
  el.pause.setAttribute('aria-label', s.status === 'paused' ? 'Resume' : 'Pause');
});

B.onLevel((v) => {
  const lit = Math.round(v * bars.length * 1.2);
  bars.forEach((b, i) => {
    b.classList.toggle('on', i < lit);
    b.classList.toggle('hot', i === bars.length - 1 && i < lit);
  });
});

let flashTimer = null;
B.onFlash((kind) => {
  el.toast.textContent = kind === 'scratch' ? 'Scratch marked' : 'Marked';
  el.bar.classList.add('flash');
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => el.bar.classList.remove('flash'), 700);
});

el.pause.addEventListener('click', () => B.pause());
el.stop.addEventListener('click', () => B.stop());
