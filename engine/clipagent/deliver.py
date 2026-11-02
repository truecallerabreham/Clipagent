"""Deliverables: everything a finished Session hands back.

  deliverables/final.mp4        the main video
  deliverables/shorts/*.mp4     vertical 9:16 cut-downs of the agent-picked moments
  deliverables/thumbnail.png    1280x720 thumbnail
  deliverables/captions.srt     captions on the edited timeline
  deliverables/chapters.txt     YouTube chapter list
  deliverables/copy.md          titles, description, LinkedIn and X posts
  deliverables/report.md        what was done, what to check
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import cv2
import numpy as np

from .common import FFMPEG, Timeline, load_json, probe, run
from .effects import FONT_DIR, text_image, paste_bgra
from .inserts.build import load_manifest, word_index


def ts_srt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def ts_yt(t):
    t = int(t)
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _src(ref, words):
    if isinstance(ref, (int, float)):
        return float(ref)
    return words[ref]["s"]


def _src_end(ref, words):
    if isinstance(ref, (int, float)):
        return float(ref)
    return words[ref]["e"]


def write_srt(words_list, tl: Timeline, path: Path, per=7):
    from .overlays import apply_caption_edits, apply_glossary
    lines, cur, n = [], [], 0
    mapped = []
    for w in words_list:
        if w.get("filler"):
            continue
        s, e = tl.to_out(w["s"], "next"), tl.to_out(w["e"], "prev")
        if e - s > 0.02:
            mapped.append((s, e, w["w"].strip()))
    chunks = []
    for m in mapped:
        if cur and (len(cur) >= per or m[0] - cur[-1][1] > 0.7 or re.search(r"[.!?]$", cur[-1][2])):
            chunks.append(cur)
            cur = []
        cur.append(m)
    if cur:
        chunks.append(cur)
    for c in chunks:
        n += 1
        lines += [str(n), f"{ts_srt(c[0][0])} --> {ts_srt(c[-1][1] + 0.2)}", " ".join(x[2] for x in c), ""]
    path.write_text("\n".join(lines))
    return n


def make_short(final: Path, a: float, b: float, title: str, out: Path):
    """Landscape → 9:16: blurred fill, the video centred, the title on top."""
    out.parent.mkdir(parents=True, exist_ok=True)
    font = str(FONT_DIR / "Inter-ExtraBold.ttf").replace(":", "\\:")
    safe = title.replace("\\", "").replace("'", "’").replace(":", "\\:")
    vf = ("[0:v]split=2[bg][fg];"
          "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.18[bgb];"
          "[fg]scale=1080:-2[fgs];"
          "[bgb][fgs]overlay=(W-w)/2:(H-h)/2-80,"
          f"drawtext=fontfile='{font}':text='{safe}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=300:"
          "box=1:boxcolor=black@0.55:boxborderw=28[v]")
    run([FFMPEG, "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(final),
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "19", "-preset", "faster",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])


def make_thumbnail(final: Path, t: float, text: str, accent: str, out: Path):
    tmp = out.with_suffix(".raw.png")
    run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(final), "-frames:v", "1", "-vf", "scale=1280:720", str(tmp)])
    img = cv2.imread(str(tmp))
    tmp.unlink(missing_ok=True)
    if img is None:
        return False
    # left-to-right darkening so the headline reads on any frame
    grad = np.linspace(0.78, 0.15, img.shape[1])[None, :, None]
    img = (img * (1 - grad)).astype(np.uint8)
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) > 16 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    y = 360 - len(lines) * 50
    for i, ln in enumerate(lines[:3]):
        col = accent if i == len(lines[:3]) - 1 else "#FFFFFF"
        im = text_image(ln.upper(), 86, col, None, pad=4, weight="Black")
        paste_bgra(img, im, 60, y)
        y += im.shape[0] - 6
    cv2.rectangle(img, (60, y + 14), (220, y + 24), tuple(int(accent.lstrip("#")[i:i + 2], 16) for i in (4, 2, 0)), -1)
    cv2.imwrite(str(out), img)
    return True


def deliver(session, edl_path: Path) -> dict:
    edl = load_json(edl_path)
    work = edl_path.parent
    out = session.out
    out.mkdir(exist_ok=True)
    final = Path(edl["output"]["path"])
    if not final.exists():
        raise SystemExit(f"render first: {final} missing (`clipagent render`)")
    if final.parent != out:
        shutil.copy2(final, out / "final.mp4")
        final = out / "final.mp4"
    tr = load_json(work / "transcript.json")
    words = word_index(tr)
    all_words = [w for s in tr["segments"] for w in s["words"]]
    src_dur = probe(edl["inputs"]["screen"])["duration"]
    tl = Timeline(edl["segments"], edl["output"].get("fps", 30), src_dur)
    res = {"final": str(final), "duration": probe(final)["duration"]}

    res["captions"] = write_srt(all_words, tl, out / "captions.srt")
    chap = ["0:00 Intro"] + [f"{ts_yt(tl.to_out(c['at']))} {c['text']}" for c in edl.get("chapters", []) if tl.to_out(c["at"]) > 5]
    (out / "chapters.txt").write_text("\n".join(chap) + "\n")

    shorts = []
    for i, sh in enumerate(edl.get("shorts", []), 1):
        try:
            a, b = tl.to_out(_src(sh["start"], words), "next"), tl.to_out(_src_end(sh["end"], words), "prev")
        except KeyError as e:
            print(f"short {i}: unknown word {e}; skipped")
            continue
        if b - a < 5:
            continue
        p = out / "shorts" / f"short_{i:02d}_{re.sub(r'[^a-z0-9]+', '-', sh.get('title', 'clip').lower()).strip('-')[:30]}.mp4"
        print(f"short {i}: {b - a:.1f}s -> {p.name}", flush=True)
        make_short(final, a, b, sh.get("title", ""), p)
        shorts.append(str(p))
    res["shorts"] = shorts

    th = edl.get("thumbnail") or {}
    t = tl.to_out(_src(th["at"], words)) if th.get("at") is not None else res["duration"] * 0.3
    title = th.get("text") or (edl.get("titles") or [{}])[0].get("text") or session.meta().get("title") or "Watch this"
    if make_thumbnail(final, t, title, edl.get("style", {}).get("accent", "#D97757"), out / "thumbnail.png"):
        res["thumbnail"] = str(out / "thumbnail.png")

    pub = edl.get("publish") or {}
    copy = [f"# {pub.get('title') or title}", ""]
    if pub.get("description"):
        copy += ["## YouTube description", "", pub["description"], "", "Chapters:", *chap, ""]
    if pub.get("tags"):
        copy += ["## Tags", "", ", ".join(pub["tags"]), ""]
    if pub.get("linkedin"):
        copy += ["## LinkedIn post", "", pub["linkedin"], ""]
    if pub.get("x"):
        copy += ["## X / Twitter post", "", pub["x"], ""]
    (out / "copy.md").write_text("\n".join(copy) + "\n")

    write_report(session, edl, work, tl, res, src_dur)
    return res


def write_report(session, edl, work, tl, res, src_dur):
    manifest = load_manifest(work)
    qa = load_json(work / "qa.json") if (work / "qa.json").exists() else None
    low = []
    for s in load_json(work / "transcript.json")["segments"]:
        for w in s["words"]:
            if w.get("p", 1) < 0.45 and not w.get("filler"):
                low.append(f"{w['w']} ({w['s']:.1f}s)")
    ins = manifest.get("inserts", [])
    ok = [i for i in ins if i["status"] in ("rendered", "cached")]
    L = [f"# ClipAgent report: {session.meta().get('title') or session.path.name}", "",
         f"- **Final video:** `{res['final']}` ({res['duration']:.1f}s, from {src_dur:.1f}s raw)",
         f"- **Look:** {edl.get('look')}",
         f"- **Cuts:** {len(tl.segments)} kept segments, {sum(1 for s in edl['segments'] if s.get('speed', 1) > 1)} speed-ups, "
         f"{len(edl.get('_draft_scratched', []))} Scratch Marker cuts",
         f"- **Inserts:** {len(ok)} rendered of {len(edl.get('inserts', []))} planned",
         f"- **Zooms:** {len(edl.get('zooms', []))}, **chapters:** {len(edl.get('chapters', []))}, "
         f"**annotations:** {len(edl.get('annotations', []))}",
         f"- **Camera:** {edl.get('camera', {}).get('quality') or 'n/a'} quality, voice denoise `{edl.get('voice', {}).get('denoise')}`",
         f"- **Shorts:** {len(res.get('shorts', []))}, **thumbnail:** {'yes' if res.get('thumbnail') else 'no'}, "
         f"**captions:** {res.get('captions', 0)} lines", ""]
    if edl.get("mismatches"):
        L += ["## Mismatches (you said X, your Context Pack shows Y)", ""]
        L += [f"- {m.get('at', '?')}: said “{m.get('said', '')}”, context shows “{m.get('context', '')}”" for m in edl["mismatches"]]
        L.append("")
    dropped = [i for i in ins if i["status"] not in ("rendered", "cached")]
    if dropped or manifest.get("warnings"):
        L += ["## Inserts dropped or adjusted", ""]
        L += [f"- {i['id']}: {i['status']}" for i in dropped]
        L += [f"- {w}" for w in manifest.get("warnings", [])]
        L.append("")
    if qa:
        bad = [r for r in qa["inserts"] if not r.get("pass")]
        L += ["## Self-check", "", f"QA {'passed' if qa['pass'] else 'flagged ' + str(len(bad)) + ' Insert(s)'}.", ""]
        L += [f"- {r['id']}: " + "; ".join(i["kind"] + " " + i["text"] for i in r["issues"]) for r in bad]
        L.append("")
    if edl.get("redact"):
        L += ["## Redacted", ""] + [f"- {r.get('note', 'region')} {r['rect']}" for r in edl["redact"]] + [""]
    if low:
        L += ["## Words the transcriber was unsure of", "", ", ".join(low[:60]), ""]
    L += ["## Tweak and re-render", "",
          "Edit `work/edl.json`, then `clipagent inserts && clipagent render && clipagent deliver`. "
          "Text, zoom and Insert changes skip the slow cutting pass.", ""]
    (session.out / "report.md").write_text("\n".join(L))
