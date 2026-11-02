"""Extract glyph outlines from the KaTeX (Computer Modern) fonts into JS files.

The math-vector Look lays TeX out with KaTeX, then redraws every glyph as an SVG path so it can be
stroke-drawn ("Write"), filled and morphed like Manim's VMobjects. This script produces
``glyphs/<Font>.js`` (one per KaTeX font): ``MV_GLYPHS[name] = {upm, asc, desc, g: {codepoint: [advance, d]}}``
with y pointing DOWN (SVG convention) in font units.

Run (needs fontTools; the KaTeX .ttf files come from the ``katex`` npm package, dist/fonts/):

    uv run --with fonttools python build_glyphs.py <katex>/dist/fonts
"""
import json
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = Path(__file__).resolve().parent / "glyphs"


def extract(ttf: Path) -> dict:
    f = TTFont(ttf)
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    upm = f["head"].unitsPerEm
    out = {}
    for cp, name in sorted(cmap.items()):
        g = gs[name]
        pen = SVGPathPen(gs, ntos=lambda v: str(round(v)))
        g.draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
        out[str(cp)] = [g.width, pen.getCommands()]
    return {"upm": upm, "asc": f["hhea"].ascent, "desc": f["hhea"].descent, "g": out}


def main(src: str) -> None:
    OUT.mkdir(exist_ok=True)
    for ttf in sorted(Path(src).glob("KaTeX_*.ttf")):
        name = ttf.stem.replace("KaTeX_", "")
        data = extract(ttf)
        js = "(window.MV_GLYPHS=window.MV_GLYPHS||{})[%s]=%s;\n" % (json.dumps(name), json.dumps(data, separators=(",", ":")))
        (OUT / f"{name}.js").write_text(js)
        print(f"{name}: {len(data['g'])} glyphs, {len(js) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
