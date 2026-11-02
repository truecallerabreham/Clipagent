"""Fast unit tests for the engine's pure logic (no media, no browser)."""
from clipagent import events as EV
from clipagent.common import Timeline
from clipagent.inserts.build import insert_box, resolve

WORDS = [
    {"id": "w0", "w": "The", "s": 0.0, "e": 0.2}, {"id": "w1", "w": "gateway", "s": 0.25, "e": 0.7},
    {"id": "w2", "w": "checks.", "s": 0.75, "e": 1.2},
    {"id": "w3", "w": "It", "s": 2.0, "e": 2.2}, {"id": "w4", "w": "uses", "s": 2.25, "e": 2.5},
    {"id": "w5", "w": "Redis.", "s": 2.55, "e": 3.0},
    {"id": "w6", "w": "Cut", "s": 3.1, "e": 3.3}, {"id": "w7", "w": "that.", "s": 3.35, "e": 3.6},
    {"id": "w8", "w": "It", "s": 4.5, "e": 4.7}, {"id": "w9", "w": "validates", "s": 4.75, "e": 5.4},
    {"id": "w10", "w": "tokens.", "s": 5.45, "e": 6.0},
]
TRANSCRIPT = {"segments": [{"s": 0, "e": 6, "text": "", "words": WORDS}]}


def test_spoken_scratch_cuts_previous_sentence():
    segs = [{"start": 0.0, "end": 6.2, "speed": 1}]
    spoken = EV.spoken_scratches(WORDS)
    assert spoken == [(3.1, 3.6)]
    out, removed = EV.apply_scratches(segs, WORDS, [], spoken)
    assert removed[0][0] < 2.0 + 0.01 and removed[0][1] >= 3.6
    kept = [(s["start"], s["end"]) for s in out]
    assert kept[0][1] <= 2.0 and kept[1][0] >= 3.6


def test_hotkey_marker_cuts_sentence_before_it():
    out, removed = EV.apply_scratches([{"start": 0.0, "end": 6.2, "speed": 1}], WORDS, [3.05], [])
    assert removed and abs(removed[0][0] - 1.95) < 0.01


def test_privacy_typing_has_no_characters(tmp_path):
    from clipagent.ingest import load_events
    f = tmp_path / "events.jsonl"
    f.write_text('{"t": 1, "type": "typing", "char": "p"}\n{"t": 2, "type": "shortcut", "keys": ["Ctrl", "S"]}\n{"t": 3, "type": "cl')
    ev = load_events(f)
    assert len(ev) == 2 and "char" not in ev[0]


def test_click_zooms_group_and_clamp():
    clk = [{"t": 1.0, "x": 0.02, "y": 0.02}, {"t": 2.0, "x": 0.05, "y": 0.04}, {"t": 30.0, "x": 0.9, "y": 0.9}]
    z = EV.click_zooms(clk)
    assert len(z) == 2
    for zz in z:
        x, y, w, h = zz["rect"]
        assert 0 <= x and 0 <= y and x + w <= 1.0001 and y + h <= 1.0001
        assert 1 / 1.6 - 1e-3 <= w <= 1 / 1.2 + 1e-3


def test_beats_follow_words_through_cuts():
    # cut 1.3-4.4 away: "It validates" moves earlier in output time
    tl = Timeline([{"start": 0.0, "end": 1.3, "speed": 1}, {"start": 4.4, "end": 6.2, "speed": 1}], 30)
    edl = {"look": "architecture-flow", "output": {"format": "landscape", "fps": 30},
           "inserts": [{"id": "a", "start": "w0", "end": "w10", "mode": "full",
                        "beats": [{"word": "w9", "action": "validate", "target": "db"}]}]}
    specs, warnings = resolve(edl, TRANSCRIPT, tl)
    assert len(specs) == 1
    beat_out = specs[0]["_placement"]["out_start"] + specs[0]["beats"][0]["at"]
    assert abs(beat_out - tl.to_out(4.75)) < 0.02
    assert abs(tl.to_out(4.75) - (1.3 + 0.35)) < 0.05


def test_beat_in_cut_warns():
    tl = Timeline([{"start": 0.0, "end": 1.3, "speed": 1}, {"start": 4.4, "end": 6.2, "speed": 1}], 30)
    edl = {"look": "architecture-flow", "output": {"format": "landscape", "fps": 30},
           "inserts": [{"id": "a", "start": "w0", "end": "w10", "beats": [{"word": "w5", "action": "x"}]}]}
    _, warnings = resolve(edl, TRANSCRIPT, tl)
    assert any("cut" in w for w in warnings)


def test_insert_boxes_inside_canvas():
    for fmt, (W, H) in (("landscape", (1920, 1080)), ("vertical", (1080, 1920))):
        for mode in ("full", "split", "overlay"):
            x, y, w, h = insert_box(mode, W, H, None, fmt)
            assert x >= 0 and y >= 0 and x + w <= W and y + h <= H
