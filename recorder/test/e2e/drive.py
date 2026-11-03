#!/usr/bin/env python3
"""Show the demo page full-screen on the virtual display :99 and drive real X input (XTest)."""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from Xlib import X, XK, display
from Xlib.ext import xtest

page_html, out, secs = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), float(sys.argv[3])
d = display.Display(":99")
def move(x, y): xtest.fake_input(d, X.MotionNotify, x=x, y=y); d.sync()
def click(x, y):
    move(x, y); time.sleep(0.05)
    xtest.fake_input(d, X.ButtonPress, 1); d.sync(); time.sleep(0.06)
    xtest.fake_input(d, X.ButtonRelease, 1); d.sync()
def combo(*names):
    codes = [d.keysym_to_keycode(XK.string_to_keysym(n)) for n in names]
    for c in codes: xtest.fake_input(d, X.KeyPress, c); d.sync(); time.sleep(0.03)
    for c in reversed(codes): xtest.fake_input(d, X.KeyRelease, c); d.sync()

script = [(3.0, "click", (520, 180)), (13.5, "click", (700, 420)), (21.0, "combo", ("Control_L", "Shift_L", "k")),
          (30.0, "click", (900, 600)), (39.5, "click", (640, 760))]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False, env={**os.environ, "DISPLAY": ":99"},
                          args=["--window-position=0,0", "--window-size=1920,1080", "--kiosk", "--ozone-platform=x11"])
    pg = b.new_page(no_viewport=True)
    t0 = time.time(); pg.goto(page_html.as_uri())
    out.write_text(json.dumps({"page_loaded_epoch": t0}))
    for at, kind, arg in script:
        time.sleep(max(0, t0 + at - time.time()))
        click(*arg) if kind == "click" else combo(*arg)
    time.sleep(max(0, t0 + secs - time.time()))
    b.close()
print("done")
