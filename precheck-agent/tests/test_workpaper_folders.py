"""Reading every workpaper (AFIT, 18 Nov 2026): last year's workpapers are everything in a workpapers
folder and all its subfolders, whatever each file looks like; every one is shown to the pre-check; a
folder too big to list in full is said to be so (and nothing it did not reach is forgotten); and the WP
Agent reads every file, subfolders included."""
from precheck_agent import config, keydocs
from precheck_agent.gst import sources as gst_sources

from .test_precheck import ready_folder


def nested(env):
    """Last year's pack with workpapers two folders down, one of them a bank statement."""
    root = ready_folder(env)
    deep = root / "2025" / "Workpapers" / "Bank" / "ANZ"
    deep.mkdir(parents=True)
    (deep / "ANZ March 2025 statement.txt").write_text("ANZ Bank statement\nAccount 01-0123-0456789-00\nClosing balance 4,210.00\n", encoding="utf-8")
    (root / "2025" / "Workpapers" / "Fixed asset register.txt").write_text("Fixed asset register\nHeat pump 3,200.00\n", encoding="utf-8")
    env.pm.add_job("1", "client-s", "smith", direction=[])
    return root


def test_everything_in_a_workpapers_folder_and_its_subfolders_is_a_workpaper(env):
    nested(env)
    result = env.run("1")
    body = env.precheck.calls[0]["messages"][-1].content
    section = body.split("== LAST YEAR'S WORKPAPERS", 1)[1].split("\n== ", 1)[0]
    assert "ANZ March 2025 statement.txt [2025/Workpapers/Bank/ANZ]" in section  # two folders down, a bank statement
    assert "Fixed asset register.txt [2025/Workpapers]" in section
    assert "Final TB 2025.xlsx" in section  # still there too
    wp = next(k for k in result["precheck"]["key_documents"] if k["role"] == "last_year_workpapers")
    assert wp["found"]


def test_which_folders_hold_workpapers():
    for path in ("2025/Workpapers/", "2025/Workpapers/Bank/ANZ/", "FY25 Working Papers/Fixed assets/", "2025/WP/", "Workings/"):
        assert keydocs.in_workpapers_folder({"path": path}), path
    for path in ("", "2025/", "2025/Wages/", "2026/Invoices/"):
        assert not keydocs.in_workpapers_folder({"path": path}), path


def test_a_folder_too_big_to_list_says_so_and_forgets_nothing(env, monkeypatch):
    nested(env)
    first = env.run("1")
    assert first["status"] == "complete"
    monkeypatch.setenv("PRECHECK_MAX_FILES_PER_FOLDER", "2")  # the folder holds 3 files (a zip and two)
    config.get_settings.cache_clear()
    env.run("1")
    progress = [e.get("label", "") for e in env.pm.events if e.get("type") == "ai_precheck.progress"]
    assert any("only the first 2 were read" in label for label in progress)
    # What the listing did not reach is not treated as removed from the folder.
    from precheck_agent.store import get_store
    assert len(get_store().get_manifest("client-s", "1")) > 2


def test_the_wp_agent_reads_every_file_and_names_any_it_could_not(env, monkeypatch):
    root = env.drive_root / "many"
    (root / "Sub" / "Deeper").mkdir(parents=True)
    for n in range(5):
        (root / f"Doc {n}.txt").write_text(f"Document {n}\n", encoding="utf-8")
    (root / "Sub" / "Deeper" / "Bank rec.txt").write_text("Bank reconciliation\n", encoding="utf-8")
    got = gst_sources.gather("local://many")
    assert any(s.name == "Bank rec.txt" and s.path == "Sub/Deeper/" and not s.error for s in got)  # read, two folders down
    monkeypatch.setattr(gst_sources, "MAX_FILES", 3)
    got = gst_sources.gather("local://many")
    unread = [s for s in got if s.error.startswith("Not read")]
    assert len(got) == 6 and len(unread) == 3 and unread[0].error == "Not read: the folder has more than 3 files."
