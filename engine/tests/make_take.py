"""Build a synthetic Take (what the recorder writes) for end-to-end tests and demos.

usage: uv run python tests/make_take.py SESSION_DIR VOICE.wav [--no-camera]

Writes SESSION_DIR/take/{screen.webm, camera.webm, mic.webm, events.jsonl, take.json, state.json}
with a fake code-editor screen, a placeholder camera, the given voice as the mic,
and input events (clicks, typing, a shortcut, a Scratch Marker).
"""
import argparse
import json
import subprocess
from pathlib import Path

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

CODE = [
    "// src/auth/gateway.ts",
    "export async function login(req: Request) {",
    "  const user = await db.users.find(req.email)",
    "  if (!verify(req.password, user.hash)) throw new Unauthorized()",
    "  const access = sign({ sub: user.id }, { expiresIn: '15m' })",
    "  const refresh = issueRefreshToken(user.id)",
    "  await sessions.put(refresh, user.id)",
    "  return { access, refresh }",
    "}",
]


def esc(s):
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("voice")
    ap.add_argument("--no-camera", action="store_true")
    a = ap.parse_args()
    take = Path(a.session) / "take"
    take.mkdir(parents=True, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.voice],
                               capture_output=True, text=True).stdout) + 1.0

    draws = ["drawbox=x=0:y=0:w=iw:h=56:color=0x1f2430:t=fill",
             f"drawtext=fontfile={MONO}:text='gateway.ts — clipagent-demo':x=24:y=18:fontsize=22:fontcolor=0x9aa4b2",
             "drawbox=x=0:y=56:w=260:h=ih-56:color=0x161a22:t=fill"]
    for i, f in enumerate(["src/", "  auth/", "    gateway.ts", "    tokens.ts", "  orders/", "package.json"]):
        draws.append(f"drawtext=fontfile={MONO}:text='{esc(f)}':x=20:y={90 + i * 34}:fontsize=22:fontcolor=0x7d8796")
    for i, line in enumerate(CODE):
        t0 = 2.0 + i * 2.2
        draws.append(f"drawtext=fontfile={MONO}:text='{esc(line)}':x=300:y={110 + i * 44}:fontsize=28:"
                     f"fontcolor=0xd8dee9:enable='gte(t,{t0:.1f})'")
    draws.append("drawbox=x=290:y=110:w=6:h=34:color=0x61afef:t=fill:enable='lt(mod(t\\,1)\\,0.5)'")
    vf = ",".join(draws)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x0f1218:s=1920x1080:r=30:d={dur:.2f}",
                    "-vf", vf, "-c:v", "libvpx-vp9", "-b:v", "2M", "-deadline", "realtime", "-cpu-used", "8",
                    str(take / "screen.webm")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.voice, "-af", "apad", "-t", f"{dur:.2f}", "-c:a", "libopus", "-b:a", "96k",
                    str(take / "mic.webm")], check=True)
    streams = {"screen": {"file": "screen.webm", "start_offset": 0.0}, "mic": {"file": "mic.webm", "start_offset": 0.0, "label": "test voice"}}
    if not a.no_camera:
        cam_vf = ("drawbox=x=0:y=0:w=iw:h=ih:color=0x3a4a5c:t=fill,"
                  "drawbox=x=520:y=180:w=240:h=300:color=0xd9a77f:t=fill,"
                  "drawbox=x=470:y=480:w=340:h=240:color=0x2b3a8c:t=fill,noise=alls=12:allf=t")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=1280x720:r=30:d={dur:.2f}",
                        "-vf", cam_vf, "-c:v", "libvpx-vp9", "-b:v", "1M", "-deadline", "realtime", "-cpu-used", "8",
                        str(take / "camera.webm")], check=True)
        streams["camera"] = {"file": "camera.webm", "start_offset": 0.0, "label": "test camera"}

    events = [{"t": 1.0, "type": "click", "x": 0.08, "y": 0.135, "button": "left"},
              {"t": 1.6, "type": "click", "x": 0.09, "y": 0.165, "button": "left"},
              {"t": 3.0, "type": "shortcut", "keys": ["Ctrl", "Shift", "P"]}]
    events += [{"t": round(4.0 + k * 0.18, 2), "type": "typing"} for k in range(30)]
    events += [{"t": 14.2, "type": "click", "x": 0.42, "y": 0.42, "button": "left"},
               {"t": 20.0, "type": "click", "x": None, "y": None, "button": "left"}]
    (take / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    (take / "take.json").write_text(json.dumps({
        "version": 1, "app": "make_take.py", "platform": "linux", "started_at": "2026-11-02T20:00:00Z",
        "duration": round(dur, 3), "display": {"width": 1920, "height": 1080, "scale": 1.0}, "streams": streams,
        "input": {"source": "uiohook", "warning": None}, "overlay_rect": None, "pauses": []}, indent=2))
    (take / "state.json").write_text(json.dumps({"status": "done", "error": None, "elapsed": dur}))
    print(f"take written: {take} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
