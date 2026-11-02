"""All on-screen text, as one animated ASS subtitle file burned in by libass:
karaoke captions, title cards, chapter labels, callout pills, the speed-up
badge, the brand badge and the outro card. Positions are fractions of the
canvas so the same EDL renders landscape and vertical."""
import re

# Per-format placement (fractions of canvas width / height).
PLACE = {
    "landscape": {"caption_y": 0.915, "caption_size": 0.052, "title_y": 0.44, "title_size": 0.085,
                  "chapter": (0.05, 0.075), "callout_y": 0.07, "speed": (0.05, 0.075), "brand": (0.95, 0.075)},
    "vertical": {"caption_y": 0.535, "caption_size": 0.032, "title_y": 0.40, "title_size": 0.052,
                 "chapter": (0.06, 0.085), "callout_y": 0.11, "speed": (0.06, 0.135), "brand": (0.94, 0.06)},
}


def ass_color(hexstr, alpha=0):
    h = hexstr.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def tag_color(hexstr):
    """Inline override colour: &HBBGGRR&"""
    h = hexstr.lstrip("#").upper()
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"


def ts(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def esc(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def header(W, H, fmt, font, accent):
    P = PLACE[fmt]
    cap = int(H * P["caption_size"]) if fmt == "landscape" else int(W * 0.062)
    title = int(H * P["title_size"]) if fmt == "landscape" else int(W * 0.095)
    s = max(1.0, H / 1080) if fmt == "landscape" else max(1.0, W / 1080)
    white, black, acc = "&H00FFFFFF", "&H00000000", ass_color(accent)
    box = "&H30121212"
    styles = [
        # Name, Font, Size, Primary, Secondary, Outline, Back, Bold, BorderStyle, Outline, Shadow, Align, MarginV
        ("Caption", f"{font} ExtraBold", cap, white, white, black, "&H90000000", 1, 1, 3.2 * s, 2 * s, 2, 0),
        ("Title", f"{font} Black", title, white, white, "&H00101010", "&H80000000", 1, 1, 0, 4 * s, 5, 0),
        ("TitleSub", f"{font} Medium", int(title * 0.42), "&H00E6E6E6", white, black, "&H80000000", 0, 1, 0, 2 * s, 5, 0),
        ("Chapter", f"{font} Bold", int(34 * s), white, white, box, "&H00000000", 1, 3, 16 * s, 0, 7, 0),
        ("Callout", f"{font} Bold", int(36 * s), white, white, acc, "&H00000000", 1, 3, 14 * s, 0, 8, 0),
        ("Badge", f"{font} SemiBold", int(26 * s), white, white, box, "&H00000000", 1, 3, 10 * s, 0, 7, 0),
        ("Shape", font, 20, acc, acc, acc, acc, 0, 1, 0, 0, 7, 0),
    ]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
    ]
    for n, f, sz, pc, sc, oc, bc, b, bs, o, sh, al, mv in styles:
        lines.append(f"Style: {n},{f},{sz},{pc},{sc},{oc},{bc},{-1 if b else 0},0,0,0,100,100,0,0,{bs},{o:.1f},{sh:.1f},{al},40,40,{mv},1")
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    return lines


def ev(layer, a, b, style, text):
    return f"Dialogue: {layer},{ts(a)},{ts(b)},{style},,0,0,0,,{text}"


# ---------------------------------------------------------------- captions

def apply_glossary(words, glossary):
    """Fix Whisper's misses on technical terms, e.g. 'cloud code' -> 'Claude Code'.
    Keys may be multi-word; matching ignores case and punctuation."""
    norm = lambda w: re.sub(r"[^\w']", "", w).lower()
    items = sorted(((k.split(), v.split()) for k, v in glossary.items()), key=lambda kv: -len(kv[0]))
    out, i = [], 0
    while i < len(words):
        for key, rep in items:
            n = len(key)
            if [norm(w["w"]) for w in words[i:i + n]] == [k.lower() for k in key]:
                trail = re.sub(r"^.*?([^\w']*)$", r"\1", words[i + n - 1]["w"])
                span = words[i:i + n]
                if len(rep) == n:
                    out += [{**w, "w": r} for w, r in zip(span, rep)]
                else:
                    out.append({**span[0], "w": " ".join(rep), "e": span[-1]["e"]})
                out[-1]["w"] += trail
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def apply_caption_edits(words, edits):
    """One-off caption corrections: replace the words spoken between source
    times start..end with `text`, timed evenly over the same span. For words
    Whisper misheard because of accent or pronunciation."""
    for ed in sorted(edits, key=lambda e: e["start"]):
        a, b = ed["start"], ed["end"]
        hit = [w for w in words if a <= (w["s"] + w["e"]) / 2 <= b]
        s0, e0 = (hit[0]["s"], hit[-1]["e"]) if hit else (a, b)
        new = ed["text"].split()
        step = (e0 - s0) / max(1, len(new))
        repl = [{"w": t, "s": round(s0 + i * step, 3), "e": round(s0 + (i + 1) * step, 3), "p": 1.0} for i, t in enumerate(new)]
        keep = [w for w in words if w not in hit]
        idx = next((i for i, w in enumerate(keep) if w["s"] >= s0), len(keep))
        words = keep[:idx] + repl + keep[idx:]
    return words


def caption_events(words, timeline, cfg, W, H, fmt, accent):
    """Words (source time) -> karaoke caption events (output time)."""
    P = PLACE[fmt]
    per = cfg.get("words_per_line", 4)
    hl = tag_color(cfg.get("highlight", accent))
    base = tag_color(cfg.get("color", "#FFFFFF"))
    mapped = []
    for w in words:
        if w.get("filler") or not w["w"].strip():
            continue
        s, e = timeline.to_out(w["s"], "next"), timeline.to_out(w["e"], "prev")
        if e - s < 0.02 or timeline.speed_at(s) > 1:
            continue  # word was cut away or sits in a sped-up stretch
        mapped.append({"w": w["w"].strip(), "s": s, "e": e})

    chunks, cur = [], []
    for w in mapped:
        if cur and (len(cur) >= per or w["s"] - cur[-1]["e"] > 0.6 or re.search(r"[.!?]$", cur[-1]["w"])):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    out, x, y = [], W / 2, H * P["caption_y"]
    for ci, ch in enumerate(chunks):
        end = ch[-1]["e"] + 0.25
        if ci + 1 < len(chunks):
            end = min(end, chunks[ci + 1][0]["s"])
        for k, w in enumerate(ch):
            a = w["s"] if k else ch[0]["s"]
            b = ch[k + 1]["s"] if k + 1 < len(ch) else end
            if b - a < 0.01:
                continue
            parts = []
            for j, o in enumerate(ch):
                t = esc(o["w"])
                parts.append(f"{{\\c{hl}\\fscx112\\fscy112}}{t}{{\\r\\c{base}}}" if j == k else t)
            pop = "\\fscx88\\fscy88\\t(0,120,\\fscx100\\fscy100)" if k == 0 else ""
            out.append(ev(10, a, b, "Caption", f"{{\\an2\\pos({x:.0f},{y:.0f})\\c{base}{pop}}}" + " ".join(parts)))
    return out


# ---------------------------------------------------------------- graphics

def title_events(t, dur, text, sub, W, H, fmt, accent):
    P = PLACE[fmt]
    x, y = W / 2, H * P["title_y"]
    out = [ev(20, t, t + dur, "Title",
              f"{{\\an5\\pos({x:.0f},{y:.0f})\\fscx70\\fscy70\\alpha&HFF&\\t(0,220,\\fscx105\\fscy105\\alpha&H00&)"
              f"\\t(220,330,\\fscx100\\fscy100)\\fad(0,280)}}{esc(text)}")]
    bar_w, bar_y = W * (0.16 if fmt == "landscape" else 0.3), y + H * (0.065 if fmt == "landscape" else 0.04)
    out.append(ev(20, t + 0.15, t + dur, "Shape",
                  f"{{\\an7\\pos({x - bar_w / 2:.0f},{bar_y:.0f})\\fscx0\\t(0,350,\\fscx100)\\fad(0,280)\\p1}}"
                  f"m 0 0 l {bar_w:.0f} 0 {bar_w:.0f} {max(6, H // 160)} 0 {max(6, H // 160)}{{\\p0}}"))
    if sub:
        sy = bar_y + H * (0.06 if fmt == "landscape" else 0.035)
        out.append(ev(20, t + 0.25, t + dur, "TitleSub", f"{{\\an5\\pos({x:.0f},{sy:.0f})\\fad(200,280)}}{esc(sub)}"))
    return out


def chapter_events(t, idx, text, W, H, fmt, accent, dur=3.2):
    fx, fy = PLACE[fmt]["chapter"]
    x, y = W * fx, H * fy
    label = f"{{\\c{tag_color(accent)}}}{idx:02d}{{\\c&HFFFFFF&}}  {esc(text)}"
    return [ev(15, t, t + dur, "Chapter",
               f"{{\\an7\\move({x - 80:.0f},{y:.0f},{x:.0f},{y:.0f},0,320)\\fad(180,300)}}{label}")]


def callout_events(t, dur, text, W, H, fmt):
    y = H * PLACE[fmt]["callout_y"]
    return [ev(16, t, t + dur, "Callout",
               f"{{\\an8\\pos({W / 2:.0f},{y:.0f})\\fscx80\\fscy80\\t(0,160,\\fscx104\\fscy104)\\t(160,240,\\fscx100\\fscy100)"
               f"\\fad(120,200)}}{esc(text)}")]


def speed_events(timeline, W, H, fmt):
    fx, fy = PLACE[fmt]["speed"]
    out = []
    for (a, b, sp), off in zip(timeline.segments, timeline.offsets):
        d = (b - a) / sp
        if sp > 1 and d > 0.4:
            out.append(ev(12, off, off + d, "Badge",
                          f"{{\\an7\\pos({W * fx:.0f},{H * fy + (H * 0.07 if fmt == 'landscape' else 0):.0f})\\fad(120,120)}}"
                          f"»  {sp}× speed"))
    return out


def brand_events(text, spans, W, H, fmt, accent):
    fx, fy = PLACE[fmt]["brand"]
    return [ev(14, a, b, "Badge", f"{{\\an9\\pos({W * fx:.0f},{H * fy:.0f})\\fad(250,250)}}"
                                  f"{{\\c{tag_color(accent)}}}●{{\\c&HFFFFFF&}} {esc(text)}") for a, b in spans]


def outro_events(t, dur, text, sub, W, H, fmt, accent):
    return title_events(t + 0.3, dur - 0.3, text, sub, W, H, fmt, accent)


# ---------------------------------------------------------------- Look extras

KEY_GLYPHS = {"Ctrl": "Ctrl", "Control": "Ctrl", "Shift": "⇧", "Alt": "Alt", "Option": "⌥", "Meta": "⌘", "Cmd": "⌘",
              "Super": "❖", "Enter": "↵", "Return": "↵", "Tab": "⇥", "Escape": "Esc", "Esc": "Esc", "Backspace": "⌫",
              "Up": "↑", "Down": "↓", "Left": "←", "Right": "→", "Space": "Space"}


def shortcut_events(shortcuts, timeline, W, H, fmt, badge, hold=1.4):
    """Keycap badges for keyboard shortcuts (plain typing is never shown)."""
    bg, fg = badge.get("bg", "#1E1E1E"), badge.get("fg", "#FFFFFF")
    s = max(1.0, (H if fmt == "landscape" else W) / 1080)
    x, y = W * 0.5, H * (0.80 if fmt == "landscape" else 0.47)
    out, last_end = [], -1.0
    for sc in shortcuts:
        t = timeline.to_out(sc["at"], "next")
        if t < last_end or timeline.speed_at(t) > 1:
            continue
        keys = [KEY_GLYPHS.get(k, k.upper() if len(k) == 1 else k) for k in sc["keys"]]
        label = "  +  ".join(keys)
        text = (f"{{\\an5\\pos({x:.0f},{y:.0f})\\bord{14 * s:.0f}\\3c{tag_color(bg)}\\c{tag_color(fg)}\\shad0"
                f"\\fscx80\\fscy80\\t(0,140,\\fscx104\\fscy104)\\t(140,220,\\fscx100\\fscy100)\\fad(90,220)}}{esc(label)}")
        out.append(ev(17, t, t + hold, "Badge", text))
        last_end = t + hold
    return out


def chapter_card_events(t, text, W, H, card):
    """Look chapter card: black frame, centered all-caps text, wide tracking, slow 1.0 -> 1.08 scale."""
    dur = card.get("duration", 2.0)
    size = int(H * 0.06)
    track = card.get("tracking", 0.3) * size
    fg = tag_color(card.get("fg", "#FFFFFF"))
    ms = int(dur * 1000)
    return [ev(25, t, t + dur, "Title",
               f"{{\\an5\\pos({W / 2:.0f},{H / 2:.0f})\\fs{size}\\fsp{track:.0f}\\c{fg}\\shad0\\bord0"
               f"\\fscx100\\fscy100\\t(0,{ms},\\fscx108\\fscy108)\\fad(160,200)}}{esc(text.upper())}")]
