"""math-vector Look: the same scene vocabulary as primitives.js, rendered with ManimCE.

Contract (docs/design.md): reads the resolved Insert spec from env ``CLIPAGENT_SPEC`` and renders a
video of exactly ``spec.duration`` seconds (the caller pads/trims to round(duration * fps) frames),
with every Beat played at its ``at`` time (waits fill the gaps). Background black (or transparent
when rendered with ``-t``). Scene vocabulary: ../PRIMITIVES.md.

    CLIPAGENT_SPEC=spec.json manim render scene.py ClipAgentScene --format png -r 1920,1080 --fps 30

Timing model: Beats are played in time order. Beats sharing an ``at`` play together. When a Beat
would still be running at the next Beat's ``at``, it is compressed to end there, so the edit never
drifts from the spoken words. Without LaTeX on PATH (or CLIPAGENT_NO_LATEX=1), TeX falls back to Text.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
from pathlib import Path

import numpy as np
from manim import (
    BLACK, DOWN, LEFT, ORIGIN, RIGHT, UP, UL, UR, DL, DR,
    AnimationGroup, ApplyMatrix, Arrow, Axes, BraceBetweenPoints, Circle, Circumscribe, Create,
    DashedLine, DecimalNumber, Dot, FadeIn, FadeOut, Flash, GrowArrow, GrowFromCenter, Indicate,
    Line, MathTex, Matrix, NumberPlane, Polygon, ReplacementTransform, Scene, SurroundingRectangle,
    Tex, Text, TracedPath, Transform, TransformMatchingShapes, TransformMatchingTex, Uncreate,
    ValueTracker, VGroup, VMobject, Write, always_redraw, config,
)

LOOK_DIR = Path(__file__).resolve().parents[1]
SPEC = json.loads(Path(os.environ["CLIPAGENT_SPEC"]).read_text())
LOOK = json.loads((LOOK_DIR / "look.json").read_text())
W, H = SPEC.get("size", [1920, 1080])
PX = min(W, H) / 8.0                      # design px per Manim unit: the short side is 8 units
DESIGN = 1080 / 8.0                       # design units (short side 1080) per Manim unit
config.background_color = BLACK
config.frame_rate = SPEC.get("fps", 30)
config.pixel_width, config.pixel_height = W, H
config.frame_height = 8.0 * H / min(W, H)
config.frame_width = 8.0 * W / min(W, H)
FW, FH = config.frame_width, config.frame_height
HAS_LATEX = bool(shutil.which("latex")) and not os.environ.get("CLIPAGENT_NO_LATEX")

GRID = "#29ABCA"
TOKENS = {k.lower(): v for k, v in LOOK.get("tokens", {}).items()}
CONCEPTS = {k.lower(): v for k, v in LOOK.get("semantic", {}).items()}
CONCEPTS.update({k.lower(): v for k, v in SPEC.get("concepts", {}).items()})
DEFAULT_DUR = {
    "enter": 1.0, "write": 1.0, "create": 1.0, "exit": 0.7, "fade_out": 0.6, "move": 1.0, "scale": 0.8,
    "indicate": 0.9, "pulse": 0.9, "circumscribe": 1.5, "highlight": 0.8, "unhighlight": 0.6, "dim": 0.5,
    "undim": 0.5, "morph": 1.4, "play": 1.4, "transform": 1.4, "set_color": 0.6, "apply_matrix": 2.0,
    "reset": 1.5, "orbit": 2.0, "set": 1.2, "shift": 1.2, "flash": 0.7,
}


def color(c, fb="#FFFFFF"):
    if not c:
        return fb
    if isinstance(c, str) and c.startswith("#"):
        return c
    k = str(c).lower().strip()
    return TOKENS.get(k) or CONCEPTS.get(k) or CONCEPTS.get(k.rstrip("s")) or fb


def d2u(px: float) -> float:
    """design px -> Manim units"""
    return px / DESIGN


def frac(x, y):
    return np.array([(x - 0.5) * FW, (0.5 - y) * FH, 0.0])


def tex_colors(tex: str) -> str:
    """\\textcolor{name}{..} / \\color{name} -> xcolor HTML model."""
    def rep(m):
        cmd, name = m.group(1), m.group(2).strip()
        return f"\\{cmd}[HTML]{{{color(name).lstrip('#').upper()}}}"
    return re.sub(r"\\(textcolor|color)\{([^}]+)\}", rep, tex)


MACROS = {r"\ihat": r"\hat{\imath}", r"\jhat": r"\hat{\jmath}", r"\R": r"\mathbb{R}", r"\N": r"\mathbb{N}"}


def make_tex(tex: str, size: float, col="#FFFFFF", colors=None, text=False):
    fs = size * 0.75
    if not HAS_LATEX:
        plain = re.sub(r"\\[a-zA-Z]+|[{}$^_]", "", tex) if not text else tex.replace("$", "")
        return Text(plain or " ", font_size=fs * 0.9, color=col)
    for k, v in MACROS.items():
        tex = tex.replace(k, v)
    tex = tex_colors(tex)
    t2c = {k: color(v) for k, v in (colors or {}).items()}
    if text:
        return Tex(tex.replace("$", "$"), font_size=fs, color=col, tex_to_color_map=t2c or None)
    return MathTex(tex, font_size=fs, color=col, tex_to_color_map=t2c or None)


def text_to_tex(s: str) -> str:
    return "".join(seg[1:-1] if seg.startswith("$") and seg.endswith("$") and len(seg) > 1 else (rf"\text{{{seg}}}" if seg else "")
                   for seg in re.split(r"(\$[^$]*\$)", s))


class Element:
    """One scene element: a Manim mobject plus what the vocabulary needs to address it."""

    def __init__(self, sc: "ClipAgentScene", d: dict):
        self.sc, self.id, self.kind, self.p = sc, d["id"], d["primitive"], dict(d.get("props", {}))
        self.mob: VMobject | None = None
        self.on_plane = True
        self.extra: list = []   # mobjects that come and go with this element (labels, traces)

    # ---- geometry helpers
    @property
    def plane(self):
        pid = self.p.get("plane")
        el = self.sc.els.get(pid) if pid else self.sc.plane
        return el.mob if el else None

    def c2p(self, v):
        pl = self.plane
        v = list(v) + [0] * (3 - len(v))
        if pl is None:
            return frac(v[0], v[1])
        return pl.c2p(v[0], v[1])

    def place(self, mob, w_h=None):
        p = self.p
        if p.get("pos") is not None:
            mob.move_to(self.sc.point(p["pos"], self))
        elif p.get("next_to"):
            n = p["next_to"] if isinstance(p["next_to"], dict) else {"id": p["next_to"]}
            dirs = {"right": RIGHT, "left": LEFT, "up": UP, "top": UP, "down": DOWN, "bottom": DOWN}
            mob.next_to(self.sc.els[n["id"]].mob, dirs.get(n.get("side", "right"), RIGHT), buff=d2u(n.get("buff", 30)))
        elif p.get("to_edge"):
            e = p["to_edge"]
            vec = {"top": UP, "up": UP, "bottom": DOWN, "down": DOWN, "left": LEFT, "right": RIGHT, "ul": UL, "ur": UR, "dl": DL, "dr": DR}.get(e, UP)
            mob.move_to(frac(p.get("x", 0.5), p.get("y", 0.5)))
            mob.to_edge(vec, buff=d2u(p.get("buff", 64)))
        else:
            mob.move_to(frac(p.get("x", 0.5), p.get("y", 0.5)))
        mob.shift(np.array([d2u(p.get("dx", 0)), -d2u(p.get("dy", 0)), 0]))


class ClipAgentScene(Scene):
    def point(self, ref, el: Element | None = None):
        """Point reference -> scene point (see PRIMITIVES.md)."""
        if isinstance(ref, (list, tuple)):
            return (el or self._plane_el()).c2p(ref) if (el or self.plane) else frac(ref[0], ref[1])
        if isinstance(ref, dict):
            return frac(ref["x"], ref["y"])
        eid, _, anchor = str(ref).partition(".")
        e = self.els[eid]
        if e.kind in ("Vector", "Arrow"):
            if anchor == "tail":
                return e.mob.get_start()
            if anchor == "mid":
                return (e.mob.get_start() + e.mob.get_end()) / 2
            return e.mob.get_end()
        if e.kind in ("NumberPlane", "Axes"):
            return e.mob.c2p(0, 0)
        m = e.mob
        return {"left": m.get_left(), "right": m.get_right(), "top": m.get_top(), "bottom": m.get_bottom()}.get(anchor, m.get_center())

    def math(self, ref):
        """Math coords of a reference on the plane (pre-transform), or None."""
        if isinstance(ref, (list, tuple)):
            return [ref[0], ref[1], ref[2] if len(ref) > 2 else 0]
        eid, _, anchor = str(ref).partition(".")
        e = self.els.get(eid)
        if e is None or self.plane is None:
            return None
        pt = self.point(ref)
        return list(self.plane.mob.p2c(pt)) + [0]

    def _plane_el(self):
        return self.plane

    # ------------------------------------------------------------------ build
    def build(self):
        self.els: dict[str, Element] = {}
        self.plane: Element | None = None
        defs = []
        if SPEC.get("scene", {}).get("title"):
            t = SPEC["scene"]["title"]
            defs.append({"id": "title", "primitive": "Title", "props": t if isinstance(t, dict) else {"text": t}})
        defs += SPEC.get("scene", {}).get("elements", [])
        for d in defs:
            e = Element(self, d)
            self.els[e.id] = e
            getattr(self, "b_" + e.kind, self.b_unknown)(e)
            if e.kind in ("NumberPlane", "Axes") and self.plane is None:
                self.plane = e

    def b_unknown(self, e):
        raise ValueError(f'Unknown primitive "{e.kind}" (element "{e.id}")')

    def _ranges(self, e, portrait):
        xr = list(e.p.get("x_range") or ([-4.5, 4.5, 1] if portrait else [-8, 8, 1]))
        yr = list(e.p.get("y_range") or ([-8, 8, 1] if portrait else [-4.5, 4.5, 1]))
        xr += [1] * (3 - len(xr))
        yr += [1] * (3 - len(yr))
        return xr, yr

    def b_NumberPlane(self, e, axes=False):
        p = e.p
        xr, yr = self._ranges(e, H > W * 0.83)
        explicit = any(k in p for k in ("unit", "width", "height", "x", "y"))
        full = p.get("full") is True or (p.get("full") is not False and not axes and not explicit)
        fill = p.get("fill", 1.0 if full else 0.8)
        unit = d2u(p["unit"]) if p.get("unit") else d2u(p["width"]) / (xr[1] - xr[0]) if p.get("width") else d2u(p["height"]) / (yr[1] - yr[0]) if p.get("height") else min(FW * fill / (xr[1] - xr[0]), FH * fill / (yr[1] - yr[0]))
        ext = 2.5 if full else 0
        gx = [xr[0] - ext * (xr[1] - xr[0]) / 2, xr[1] + ext * (xr[1] - xr[0]) / 2, xr[2]]
        gy = [yr[0] - ext * (yr[1] - yr[0]) / 2, yr[1] + ext * (yr[1] - yr[0]) / 2, yr[2]]
        if axes:
            mob = Axes(x_range=xr, y_range=yr, x_length=unit * (xr[1] - xr[0]), y_length=unit * (yr[1] - yr[0]), tips=p.get("tips", True),
                       axis_config={"color": color(p.get("axis_color")), "stroke_width": 2.5, "include_numbers": p.get("numbers", True), "font_size": p.get("number_size", 30) * 0.75})
        else:
            mob = NumberPlane(x_range=gx, y_range=gy, x_length=unit * (gx[1] - gx[0]), y_length=unit * (gy[1] - gy[0]),
                              background_line_style={"stroke_color": color(p.get("color"), GRID), "stroke_width": 2, "stroke_opacity": p.get("opacity", 0.4)},
                              faded_line_ratio=p.get("subdivisions", 2), axis_config={"color": color(p.get("axis_color")), "stroke_width": 2.5})
        center_math = ((xr[0] + xr[1]) / 2, (yr[0] + yr[1]) / 2)
        mob.shift(frac(p.get("x", 0.5), p.get("y", 0.5)) - mob.c2p(*center_math))
        labels = VGroup()
        if p.get("x_label"):
            labels.add(make_tex(p["x_label"], p.get("label_size", 40)).next_to(mob.c2p(xr[1], 0), UP + LEFT, buff=0.15))
        if p.get("y_label"):
            labels.add(make_tex(p["y_label"], p.get("label_size", 40)).next_to(mob.c2p(0, yr[1]), RIGHT, buff=0.15))
        e.mob = mob
        e.extra = [labels] if len(labels) else []
        e.attached = []

    def b_Axes(self, e):
        self.b_NumberPlane(e, axes=True)

    def b_Tex(self, e):
        p = e.p
        e.mob = make_tex(p.get("tex", ""), p.get("size", 56), color(p.get("color")), p.get("colors"))
        e.place(e.mob)
        if p.get("backdrop"):
            e.mob.add_background_rectangle(color=BLACK, opacity=p.get("backdrop_opacity", 0.85), buff=d2u(p.get("backdrop_pad", 26)))

    b_MathTex = b_Tex

    def b_Label(self, e):
        p = e.p
        tex = p.get("tex") or text_to_tex(p.get("text", ""))
        e.mob = make_tex(tex, p.get("size", 42), color(p.get("color")), p.get("colors"))
        e.place(e.mob)

    def b_Title(self, e):
        e.p.setdefault("to_edge", "top")
        e.p.setdefault("buff", 54)
        e.p.setdefault("size", 60)
        self.b_Label(e)
        if e.p.get("underline", True):
            w = max(e.mob.width * 1.25, e.mob.width + d2u(120))
            e.extra = [Line(LEFT * w / 2, RIGHT * w / 2, stroke_width=2, color="#FFFFFF").next_to(e.mob, DOWN, buff=d2u(22))]

    def b_Matrix(self, e):
        p = e.p
        rows = [[str(v) for v in r] for r in p.get("rows", [[1, 0], [0, 1]])]
        br = {"b": ("[", "]"), "p": ("(", ")"), "v": ("|", "|")}.get(p.get("bracket", "b"), ("[", "]"))
        fs = p.get("size", 52) * 0.75
        if HAS_LATEX:
            m = Matrix(rows, left_bracket=br[0], right_bracket=br[1], element_to_mobject_config={"font_size": fs})
        else:
            m = VGroup(*[Text("  ".join(r), font_size=fs * 0.9) for r in rows]).arrange(DOWN)
        if HAS_LATEX and p.get("col_colors"):
            for i, c in enumerate(p["col_colors"]):
                m.get_columns()[i].set_color(color(c))
        parts = [m]
        if p.get("prefix"):
            parts.insert(0, make_tex(p["prefix"], p.get("size", 52)))
        if p.get("suffix"):
            parts.append(make_tex(p["suffix"], p.get("size", 52)))
        e.mob = VGroup(*parts).arrange(RIGHT, buff=0.2)
        e.matrix = m
        e.place(e.mob)
        if p.get("backdrop"):
            e.mob.add_background_rectangle(color=BLACK, opacity=0.85, buff=d2u(26))

    def b_Vector(self, e):
        p = e.p
        c = p.get("coords") or p.get("to") or [1, 1]
        e.col = color(p.get("concept") or p.get("color"), "#FFFF00")
        e.cx, e.cy = ValueTracker(c[0]), ValueTracker(c[1])
        tail = p.get("from") or [0, 0]
        e.tail_ref = tail if isinstance(tail, str) else None
        t0 = self.math(tail) if not isinstance(tail, str) else [0, 0, 0]
        e.tx, e.ty = ValueTracker(t0[0]), ValueTracker(t0[1])
        sw = p.get("stroke", 6)

        def arrow():
            if e.tail_ref:
                tm = self.math(e.tail_ref)
                e.tx.set_value(tm[0]); e.ty.set_value(tm[1])
            a = e.c2p([e.tx.get_value(), e.ty.get_value()])
            b = e.c2p([e.tx.get_value() + e.cx.get_value(), e.ty.get_value() + e.cy.get_value()])
            if np.linalg.norm(b - a) < 1e-4:
                b = a + RIGHT * 1e-3
            return Arrow(a, b, buff=0, color=e.col, stroke_width=sw, max_tip_length_to_length_ratio=0.3,
                         tip_length=d2u(p.get("tip", 30)), max_stroke_width_to_length_ratio=10)
        e.make = arrow
        e.mob = arrow()
        if p.get("label"):
            lab = make_tex(p["label"], p.get("label_size", 46), color(p.get("label_color"), e.col), p.get("label_colors"))

            def place_label(m):
                s, t = e.mob.get_start(), e.mob.get_end()
                u = (t - s) / (np.linalg.norm(t - s) or 1)
                pos = p.get("label_pos", "end")
                if pos in ("left", "right", "mid"):
                    n = np.array([-u[1], u[0], 0]) * (1 if pos != "right" else -1)
                    if pos == "mid" and n[1] < 0:
                        n = -n
                    m.move_to((s + t) / 2 + n * (0.35 + max(m.width, m.height) / 2))
                else:
                    m.move_to(t + u * (0.25 + max(m.width, m.height) / 2))
            lab.add_updater(place_label)
            e.extra = [lab]

    b_Arrow = b_Vector

    def b_Shape(self, e):
        p = e.p
        pl = e.plane
        col = color(p.get("concept") or p.get("color"))
        kind = p.get("kind", "graph")
        if kind in ("graph", "area"):
            f = self.fn(p["fn"])
            xr = p.get("x_range") or [pl.x_range[0], pl.x_range[1]]
            e.fx = f
            graph = pl.plot(f, x_range=[xr[0], xr[1]], color=col, stroke_width=p.get("stroke", 4))
            e.mob = pl.get_area(graph, x_range=xr, color=col, opacity=p.get("fill_opacity", 0.35)) if kind == "area" else graph
            e.graph = graph
        elif kind == "circle":
            r = p.get("radius", 1) * (pl.x_axis.unit_size if pl else 1)
            e.mob = Circle(radius=r, color=col, stroke_width=p.get("stroke", 4)).move_to(self.point(p.get("center", [0, 0]), e))
        elif kind == "polygon":
            e.mob = Polygon(*[self.point(v, e) for v in p["points"]], color=col, stroke_width=p.get("stroke", 4))
        elif kind == "rect":
            c, w, h = p.get("center", [0, 0]), p.get("width", 2), p.get("height", 1)
            e.mob = Polygon(*[self.point(v, e) for v in ([c[0] - w / 2, c[1] + h / 2], [c[0] + w / 2, c[1] + h / 2], [c[0] + w / 2, c[1] - h / 2], [c[0] - w / 2, c[1] - h / 2])], color=col, stroke_width=p.get("stroke", 4))
        elif kind == "line":
            e.mob = Line(self.point(p["from"], e), self.point(p["to"], e), color=col, stroke_width=p.get("stroke", 4))
        elif kind == "curve":
            m = VMobject(color=col, stroke_width=p.get("stroke", 4))
            m.set_points_smoothly([self.point(v, e) for v in p["points"]])
            e.mob = m
        elif kind == "tangent":
            g = self.els[p["graph"]]

            def tangent():
                x0 = self.math(p["dot"])[0] if p.get("dot") else p.get("x", 0)
                k = (g.fx(x0 + 1e-4) - g.fx(x0 - 1e-4)) / 2e-4
                dx = p.get("length", 3) / 2 / math.hypot(1, k)
                return Line(pl.c2p(x0 - dx, g.fx(x0) - k * dx), pl.c2p(x0 + dx, g.fx(x0) + k * dx), color=col, stroke_width=p.get("stroke", 4))
            e.make = tangent
            e.mob = tangent()
        else:
            raise ValueError(f'Shape "{e.id}": unknown kind "{kind}"')
        if p.get("fill") and kind not in ("graph", "area", "line", "tangent"):
            e.mob.set_fill(color(p["fill"]), opacity=p.get("fill_opacity", 0.5))
        if p.get("dashed") and kind not in ("area", "tangent"):
            e.mob = VGroup(*__import__("manim").DashedVMobject(e.mob, num_dashes=max(8, int(e.mob.get_arc_length() / 0.12))))

    @staticmethod
    def fn(src):
        body = str(src).replace("^", "**")
        env = {k: getattr(math, k) for k in ("sin", "cos", "tan", "asin", "acos", "atan", "atan2", "exp", "sqrt", "log", "log2", "log10", "floor", "ceil", "sinh", "cosh", "tanh")}
        env.update(abs=abs, min=min, max=max, pow=pow, pi=math.pi, e=math.e, PI=math.pi, E=math.e, ln=math.log, sign=lambda v: (v > 0) - (v < 0))
        return lambda x: eval(body, {"__builtins__": {}}, dict(env, x=x))  # noqa: S307 (agent-authored expression)

    def b_Dot(self, e):
        p = e.p
        e.col = color(p.get("concept") or p.get("color"))
        r = d2u(p.get("radius", 10))
        if p.get("on"):
            g = self.els[p["on"]]
            e.xt = ValueTracker(p.get("x", 0))
            e.make = lambda: Dot(e.plane.c2p(e.xt.get_value(), g.fx(e.xt.get_value())), radius=r, color=e.col)
        elif p.get("follow"):
            e.make = lambda: Dot(self.point(p["follow"]), radius=r, color=e.col)
        else:
            pos = p.get("pos") or [0, 0]
            e.px, e.py = ValueTracker(pos[0]), ValueTracker(pos[1])
            e.make = lambda: Dot(e.c2p([e.px.get_value(), e.py.get_value()]), radius=r, color=e.col)
        e.mob = e.make()
        if p.get("trace"):
            e.trace = TracedPath(lambda: e.mob.get_center(), stroke_color=color(p.get("trace_color"), e.col), stroke_width=p.get("trace_width", 3))
        if p.get("label"):
            lab = make_tex(p["label"], p.get("label_size", 40), e.col)
            d = {"ur": UR, "ul": UL, "dr": DR, "dl": DL, "up": UP, "down": DOWN, "left": LEFT, "right": RIGHT}.get(p.get("label_dir", "ur"), UR)
            lab.add_updater(lambda m: m.next_to(e.mob, d, buff=0.1))
            e.extra = [lab]

    def b_DashedProjection(self, e):
        p = e.p
        col = color(p.get("color"))

        def lines():
            a = self.point(p["from"])
            to = p.get("to", "both")
            g = VGroup()
            if to in ("x", "y", "both"):
                m = self.math(p["from"])
                pl = self.plane.mob
                if to in ("x", "both"):
                    g.add(DashedLine(a, pl.c2p(m[0], 0), color=col, stroke_width=p.get("stroke", 2.5), stroke_opacity=p.get("opacity", 0.8)))
                if to in ("y", "both"):
                    g.add(DashedLine(a, pl.c2p(0, m[1]), color=col, stroke_width=p.get("stroke", 2.5), stroke_opacity=p.get("opacity", 0.8)))
            else:
                g.add(DashedLine(a, self.point(to), color=col, stroke_width=p.get("stroke", 2.5)))
            return g
        e.make = lines
        e.mob = lines()

    def b_Brace(self, e):
        p = e.p
        col = color(p.get("concept") or p.get("color"))
        dirs = {"down": DOWN, "up": UP, "left": LEFT, "right": RIGHT}

        def brace():
            if p.get("target"):
                t = self.els[p["target"]].mob
                side = p.get("side", "down")
                ends = {"down": (t.get_corner(DL), t.get_corner(DR)), "up": (t.get_corner(UL), t.get_corner(UR)),
                        "left": (t.get_corner(UL), t.get_corner(DL)), "right": (t.get_corner(UR), t.get_corner(DR))}[side]
                a, b = ends
            else:
                a, b = self.point(p["from"]), self.point(p["to"])
                side = p.get("side") or ("down" if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else "right")
            g = BraceBetweenPoints(a, b, direction=dirs[side], buff=d2u(p.get("buff", 12)), color=col)
            if p.get("label"):
                lab = make_tex(p["label"], p.get("label_size", 44), color(p.get("label_color"), col), p.get("label_colors"))
                g.put_at_tip(lab, buff=d2u(p.get("label_buff", 12)))
                return VGroup(g, lab)
            return VGroup(g)
        e.make = brace
        e.mob = brace()

    def b_NumberCounter(self, e):
        p = e.p
        col = color(p.get("concept") or p.get("color"))
        num = DecimalNumber(p.get("value", 0), num_decimal_places=p.get("decimals", 2), font_size=p.get("size", 48) * 0.75, color=col,
                            include_sign=p.get("show_sign", False))
        e.vt = ValueTracker(float(p.get("value", 0)))
        tr = p.get("track")
        if tr:
            tid, _, name = (tr if isinstance(tr, str) else f'{tr["target"]}.{tr.get("value", "x")}').partition(".")
            e.value = lambda: self.value_of(tid, name or "x")
        else:
            e.value = e.vt.get_value
        parts = [num]
        if p.get("prefix"):
            parts.insert(0, make_tex(p["prefix"], p.get("size", 48), col))
        if p.get("suffix"):
            parts.append(make_tex(p["suffix"], p.get("size", 48), col))
        grp = VGroup(*parts).arrange(RIGHT, buff=0.15)
        e.place(grp)
        anchor = grp.get_left().copy()

        def upd(m):
            num.set_value(e.value())
            m.arrange(RIGHT, buff=0.15)
            if p.get("follow"):
                m.next_to(self.point(p["follow"]), UR, buff=0.15)
            else:
                m.move_to(anchor, aligned_edge=LEFT)
        grp.add_updater(upd)
        e.mob = grp

    b_Counter = b_NumberCounter

    def value_of(self, eid, name):
        e = self.els[eid]
        if e.kind in ("Vector", "Arrow"):
            pl = self.plane.mob
            t = pl.p2c(e.mob.get_end())
            s = pl.p2c(e.mob.get_start())
            d = (t[0] - s[0], t[1] - s[1])
            return {"x": t[0], "y": t[1], "dx": d[0], "dy": d[1], "length": math.hypot(*d), "angle": math.degrees(math.atan2(d[1], d[0]))}.get(name, t[0])
        if e.kind == "Dot":
            c = self.plane.mob.p2c(e.mob.get_center())
            if name == "slope" and e.p.get("on"):
                f = self.els[e.p["on"]].fx
                return (f(c[0] + 1e-4) - f(c[0] - 1e-4)) / 2e-4
            return c[1] if name == "y" else c[0]
        return 0.0

    def b_Morph(self, e):
        e.mob = VGroup()

    # ------------------------------------------------------------------ beats -> animations
    def anims_for(self, b):
        a = b.get("args") or {}
        act = b["action"]
        dur = a.get("dur", DEFAULT_DUR.get(act, 1.0))
        out = []
        for tid in (b["target"] if isinstance(b["target"], list) else [b["target"]]):
            if tid == "scene":
                keep = set(a.get("ids", []))
                for e in self.els.values():
                    if e.mob is not None and e.id not in keep:
                        out.append(e.mob.animate.set_opacity(a.get("level", 0.25) if act == "focus" else 1))
                continue
            e = self.els[tid]
            fn = getattr(self, "a_" + act, None)
            if fn is None:
                raise ValueError(f'{e.kind} "{e.id}" has no action "{act}"')
            out += [x for x in fn(e, a) if x is not None]
        return out, dur

    def live(self, e):
        if getattr(e, "make", None) and not getattr(e, "_live", False):
            e._live = True
            e.mob.add_updater(lambda m: m.become(e.make()))

    def a_enter(self, e, a):
        k = e.kind
        self.entered.add(e.id)
        if k in ("NumberPlane", "Axes"):
            res = [Create(e.mob, lag_ratio=0.02)] + [Write(x) for x in e.extra]
        elif k in ("Vector", "Arrow"):
            res = [GrowArrow(e.mob)] + [Write(x) for x in e.extra]
        elif k == "Dot":
            if getattr(e, "trace", None):
                self.add(e.trace)
            res = [GrowFromCenter(e.mob)] + [Write(x) for x in e.extra]
        elif k == "Brace":
            res = [GrowFromCenter(e.mob[0])] + ([Write(e.mob[1])] if len(e.mob) > 1 else [])
        elif k in ("Shape", "DashedProjection"):
            res = [Create(e.mob)]
        else:
            res = [Write(e.mob)] + [Create(x) for x in e.extra]
        self.after.append(lambda: self.live(e))
        return res

    a_write = a_create = a_enter

    def a_exit(self, e, a):
        if a.get("style") == "fade":
            return [FadeOut(e.mob, *e.extra)]
        return [Uncreate(e.mob)] + [FadeOut(x) for x in e.extra]

    def a_fade_out(self, e, a):
        return [FadeOut(e.mob, *e.extra)]

    def a_move(self, e, a):
        if e.kind == "Dot" and e.p.get("on") and "x" in a:
            return [e.xt.animate.set_value(a["x"])]
        if e.kind == "Dot" and a.get("pos") and hasattr(e, "px"):
            return [e.px.animate.set_value(a["pos"][0]), e.py.animate.set_value(a["pos"][1])]
        if a.get("pos") is not None or a.get("to") is not None:
            tgt = self.point(a.get("pos") if a.get("pos") is not None else a["to"], e)
        elif "x" in a or "y" in a:
            c = e.mob.get_center()
            f = frac(a.get("x", 0.5), a.get("y", 0.5))
            tgt = np.array([f[0] if "x" in a else c[0], f[1] if "y" in a else c[1], 0])
        else:
            tgt = e.mob.get_center()
        tgt = tgt + np.array([d2u(a.get("dx", 0)), -d2u(a.get("dy", 0)), 0])
        return [e.mob.animate.move_to(tgt)]

    def a_scale(self, e, a):
        return [e.mob.animate.scale(a.get("by", 1.2))]

    def a_indicate(self, e, a):
        return [Indicate(e.mob, color=color(a.get("color"), "#FFFF00"))]

    a_pulse = a_indicate

    def a_circumscribe(self, e, a):
        mob = e.matrix.get_columns()[a["col"]] if a.get("col") is not None and hasattr(e, "matrix") else e.mob
        return [Circumscribe(mob, color=color(a.get("color"), "#FFFF00"), buff=d2u(a.get("buff", 14)))]

    def a_highlight(self, e, a):
        mob = e.matrix.get_columns()[a["col"]] if a.get("col") is not None and hasattr(e, "matrix") else e.mob
        e.hl = SurroundingRectangle(mob, color=color(a.get("color"), "#FFFF00"), buff=d2u(a.get("buff", 14)))
        return [Create(e.hl)]

    def a_unhighlight(self, e, a):
        return [Uncreate(e.hl)] if getattr(e, "hl", None) else []

    def a_dim(self, e, a):
        return [e.mob.animate.set_opacity(a.get("level", 0.25))]

    def a_undim(self, e, a):
        return [e.mob.animate.set_opacity(1)]

    def a_flash(self, e, a):
        return [Flash(e.mob, color=color(a.get("color"), "#FFFF00"))]

    def a_set(self, e, a):
        if e.kind in ("Vector", "Arrow"):
            c = a.get("coords") or a.get("to")
            self.live(e)
            return [e.cx.animate.set_value(c[0]), e.cy.animate.set_value(c[1])]
        if e.kind in ("NumberCounter", "Counter"):
            return [e.vt.animate.set_value(float(a["value"]))]
        if e.kind == "Shape" and a.get("fn"):
            old = e.mob
            e.p.update(a)
            self.b_Shape(e)
            new = e.mob
            e.mob = old
            return [Transform(old, new)]
        return []

    def a_shift(self, e, a):
        ref = a.get("from") or a.get("to") or [0, 0]
        m = self.math(ref)
        self.live(e)

        def follow():
            e.tail_ref = ref if isinstance(ref, str) else None
        self.after.append(follow)
        return [e.tx.animate.set_value(m[0]), e.ty.animate.set_value(m[1])]

    def a_transform(self, e, a):
        if e.kind == "Matrix" and a.get("rows"):
            ne = Element(self, {"id": e.id + "~", "primitive": "Matrix", "props": dict(e.p, **{k: v for k, v in a.items() if k != "dur"})})
            self.b_Matrix(ne)
            new = ne.mob
        else:
            tex = a.get("tex") or text_to_tex(a.get("text", ""))
            new = make_tex(tex, a.get("size", e.p.get("size", 56)), color(e.p.get("color")), a.get("colors", e.p.get("colors")))
            new.move_to(e.mob)
            if (a.get("align") or e.p.get("align")) == "left":
                new.align_to(e.mob, LEFT)
        old = e.mob
        e.mob = new
        if HAS_LATEX and isinstance(old, MathTex) and isinstance(new, MathTex):
            return [TransformMatchingTex(old, new)]
        return [TransformMatchingShapes(old, new)]

    def a_set_color(self, e, a):
        part = e.mob.get_part_by_tex(a["part"]) if hasattr(e.mob, "get_part_by_tex") else e.mob
        return [part.animate.set_color(color(a.get("color"), "#FFFF00"))]

    def a_morph(self, e, a):
        t = self.els[a["to"]]
        self.entered.add(t.id)
        return [ReplacementTransform(e.mob, t.mob)]

    def a_play(self, e, a):
        return self.a_morph(self.els[e.p["from"]], {"to": e.p["to"]})

    def a_apply_matrix(self, e, a):
        m = np.array(a["matrix"], dtype=float)
        if m.shape == (2, 2):
            m3 = np.identity(3)
            m3[:2, :2] = m
            m = m3
        group = VGroup(e.mob)
        for o in self.els.values():
            if o is e or o.kind not in ("Vector", "Arrow", "Shape", "Dot") or o.p.get("transform") is False or o.id not in self.entered:
                continue
            if getattr(o, "_live", False):
                continue  # live elements recompute from the plane
            group.add(o.mob)
        if a.get("ghost", True) and not getattr(e, "ghost", None):
            e.ghost = e.mob.copy().set_color("#8A8A8A").set_opacity(0.35)
            self.add(e.ghost)
            self.bring_to_back(e.ghost)
        return [ApplyMatrix(m, group, about_point=e.mob.c2p(0, 0))]

    def a_reset(self, e, a):
        return []

    def a_orbit(self, e, a):
        return []  # 2D Manim scene: faux-3D camera moves are HTML-only

    # ------------------------------------------------------------------ timeline
    def construct(self):
        self.build()
        self.entered: set[str] = set()
        self.after: list = []
        total = float(SPEC["duration"])
        beats = sorted(SPEC.get("beats", []), key=lambda b: b["at"])
        # auto-enter elements without an entrance (as the HTML runtime does)
        entered = {t for b in beats if b["action"] in ("enter", "write", "create") for t in (b["target"] if isinstance(b["target"], list) else [b["target"]])}
        morphed = {(b.get("args") or {}).get("to") for b in beats if b["action"] == "morph"}
        morphed |= {e.p.get("to") for e in self.els.values() if e.kind == "Morph"}
        order = 0
        auto = []
        for e in self.els.values():
            if e.id in entered or e.id in morphed or e.p.get("auto") is False or e.kind == "Morph":
                continue
            auto.append({"at": e.p.get("enterAt", 0.15 + order * 0.14), "action": "enter", "target": e.id})
            order += 1
        beats = sorted(beats + auto, key=lambda b: b["at"])
        fps = config.frame_rate
        now = 0.0
        i = 0
        while i < len(beats):
            at = beats[i]["at"]
            group = [beats[i]]
            while i + 1 < len(beats) and beats[i + 1]["at"] - at < 0.5 / fps:
                i += 1
                group.append(beats[i])
            i += 1
            if at - now >= 1 / fps:
                self.wait(at - now)
                now = at
            anims, dur = [], 0.0
            for b in group:
                a, d = self.anims_for(b)
                anims += a
                dur = max(dur, d)
            nxt = beats[i]["at"] if i < len(beats) else total
            dur = max(1 / fps, min(dur, max(nxt - max(now, at), 1 / fps)))
            if anims:
                self.play(AnimationGroup(*anims), run_time=dur)
                now += dur
            for f in self.after:
                f()
            self.after = []
        if total - now >= 1 / fps:
            self.wait(total - now)
