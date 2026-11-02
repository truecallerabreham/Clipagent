import sys, time, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
html, outdir, secs = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), float(sys.argv[3])
with sync_playwright() as p:
    try: b = p.chromium.launch(channel="chrome")
    except Exception: b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(outdir), record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page(); page.goto(html.as_uri()); time.sleep(secs)
    v = page.video.path(); ctx.close(); b.close()
    shutil.move(v, outdir / "screen.webm"); print(outdir / "screen.webm")
