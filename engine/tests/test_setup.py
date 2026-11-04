"""First-run experience: saved setup, flag defaults from it, and linking the skill into every agent."""
import argparse
import importlib

import pytest


@pytest.fixture
def SU(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPAGENT_HOME", str(tmp_path / "ClipAgent"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")   # no `opencode`/`antigravity` on PATH: detection by folders only
    from clipagent import session, setup
    importlib.reload(session)
    return importlib.reload(setup)


def start_args(**kw):
    base = dict(camera=None, format=None, look=None, context=[], context_paths=[], context_urls=[], web=False,
                no_web=False)
    return argparse.Namespace(**{**base, **kw})


def test_no_prefs_means_sensible_defaults(SU, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = start_args()
    SU.apply_prefs(a)
    assert (a.camera, a.format, a.look, a.web) == ("webcam", "landscape", None, False)
    assert a.context_paths == [str(tmp_path)]          # the current repo is the default Context Pack


def test_saved_prefs_fill_every_flag_and_flags_still_win(SU, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = SU.save_prefs(make="short", camera="none", context="repo+web", look="auto")
    assert p["look"] is None and "9:16 short" in SU.describe_prefs(p)
    a = start_args()
    SU.apply_prefs(a)
    assert (a.camera, a.format, a.web) == ("none", "vertical", True)
    a = start_args(camera="webcam", format="landscape", no_web=True)
    SU.apply_prefs(a)
    assert (a.camera, a.format, a.web) == ("webcam", "landscape", False)


def test_voice_only_prefs_add_no_context(SU, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    SU.save_prefs(make="tutorial", camera="webcam", context="none")
    a = start_args()
    SU.apply_prefs(a)
    assert a.context_paths == [] and a.web is False


def test_bad_pref_value_is_rejected(SU):
    with pytest.raises(SystemExit):
        SU.save_prefs(camera="gopro")


def test_link_adds_skill_to_each_installed_agent(SU, tmp_path):
    home = tmp_path / "home"
    for d in (".claude", ".config/opencode/command", ".gemini/config"):
        (home / d).mkdir(parents=True)
    lines = SU.link_agents()
    assert [l.split(":")[0] for l in lines] == ["Claude Code", "OpenCode", "Antigravity"]
    for d in (".claude/skills", ".config/opencode/skills", ".gemini/config/skills"):
        link = home / d / "screen-record"
        assert (link / "SKILL.md").exists() and link.resolve() == SU.SKILL_DIR.resolve()
    cmd = home / ".config/opencode/command/screen-record.md"   # OpenCode's existing (singular) folder is used
    assert "screen-record" in cmd.read_text() and "$ARGUMENTS" in cmd.read_text()
    assert SU.link_agents() == lines                            # idempotent


def test_link_never_clobbers_someone_elses_folder(SU, tmp_path):
    own = tmp_path / "home" / ".claude" / "skills" / "screen-record"
    own.mkdir(parents=True)
    (own / "notes.txt").write_text("mine")
    assert "FAILED" in SU.link_agents()[0]
    assert (own / "notes.txt").read_text() == "mine"


def test_setup_fast_path_when_ready(SU, monkeypatch):
    SU.S.HOME.mkdir(parents=True)
    SU.SETUP_FILE.write_text('{"ready": true, "items": {}}')
    monkeypatch.setattr(SU, "recorder_ready", lambda: True)
    monkeypatch.setattr(SU, "TASKS", {})                        # any install attempt would KeyError
    assert SU.setup() is True


def test_prefs_command_reports_saved_true(SU, capsys):
    import json as J
    from clipagent import cli
    importlib.reload(cli)
    cli.main(["prefs"])
    assert J.loads(capsys.readouterr().out)["saved"] is False
    cli.main(["prefs", "--make", "tutorial", "--camera", "webcam", "--context", "repo"])
    capsys.readouterr()
    cli.main(["prefs"])
    out = J.loads(capsys.readouterr().out)
    assert out["saved"] is True and out["summary"].startswith("16:9 video")
