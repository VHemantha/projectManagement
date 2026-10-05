"""Job folders whose documents sit inside a zip in Drive."""
import io
import shutil
import zipfile

from precheck_agent.archives import display_name, members
from precheck_agent.config import get_settings
from precheck_agent.store import get_store

from .conftest import make_job_folder


def zip_folder(env, name: str, inner_dir: str = "Year end FY25/", extra: dict | None = None, **folder_kwargs):
    """A Drive folder that holds a single Documents.zip with the usual job files inside."""
    src = make_job_folder(env.tmp / "src", f"{name}-src", **folder_kwargs)
    folder = env.drive_root / name
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(folder / "Documents.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(src.iterdir()):
            z.write(path, inner_dir + path.name)
        z.writestr("__MACOSX/._junk", b"x")
        z.writestr(inner_dir + ".DS_Store", b"x")
        for member, content in (extra or {}).items():
            z.writestr(member, content)
    shutil.rmtree(src)
    return folder


def test_documents_inside_a_zip_are_read_like_loose_files(env):
    zip_folder(env, "zipped")
    env.pm.add_job("1", "client-zip", "zipped")
    result = env.run("1")
    assert result["status"] == "complete"
    read = result["trail"]["read"]
    assert read["documents"] == 5 and read["label"] == "5 documents, all new"
    names = [d["name"] for d in read["detail"]]
    assert "Trial Balance FY25.xlsx (in Documents.zip)" in names and not any("junk" in n or "DS_Store" in n for n in names)
    assert {d["kind"] for d in read["detail"]} >= {"trial balance", "reconciliation", "schedule", "tax computation"}

    # The checks done by code work on the documents inside the zip.
    checks = result["trail"]["checked"]["detail"]
    rule = next(c for c in checks if "does not agree to the trial balance" in c["label"])
    assert not rule["passed"] and "112,400" in rule["note"]
    # The trial balance inside the zip counts as last year's workpaper; the questionnaire is missing.
    found = {k["role"]: k for k in result["precheck"]["key_documents"]}
    assert found["last_year_workpapers"]["found"] and found["last_year_workpapers"]["files"][0]["name"].endswith("(in Documents.zip)")
    assert not found["questionnaire"]["found"]
    ev = result["precheck"]["evidence"][found["last_year_workpapers"]["files"][0]["evidence_id"]]
    assert ev["drive_url"] and ev["location"] == "file in the task folder"


KEY_DOCS = {"Client Questionnaire.txt": "Client questionnaire\nDid anything change this year? No.\n",
            "Year end FY25/Financial Statements FY25.txt": "Financial Statements\nFor the year ended 31 March 2025\nTrade debtors 118,900 60,000\n"}


def test_unchanged_zip_costs_nothing_and_a_changed_file_inside_is_reread(env):
    zip_folder(env, "zipped", extra=KEY_DOCS)
    env.pm.add_job("1", "client-zip", "zipped")
    first = env.run("1")
    assert first["precheck"]["decision"]["state"] != "blocked" and len(env.precheck.calls) == 1
    second = env.run("1")
    assert len(env.precheck.calls) == 1 and second["usage"]["model_calls"] == 0
    assert second["trail"]["read"]["label"] == "7 documents, 0 changed since last run"

    # Re-upload the zip with one document edited: only that document is re-read.
    path = env.drive_root / "zipped" / "Documents.zip"
    with zipfile.ZipFile(path) as z:
        content = {i.filename: z.read(i) for i in z.infolist()}
    tax = "Year end FY25/Tax computation.txt"
    content[tax] = content[tax].replace(b"57,500", b"58,000")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for member, data in content.items():
            z.writestr(member, data)
    third = env.run("1")
    assert third["trail"]["read"]["changed"] == 1
    changed = [d["name"] for d in third["trail"]["read"]["detail"] if d["changed"]]
    assert changed == ["Tax computation.txt (in Documents.zip)"]
    assert len(env.precheck.calls) == 2  # what the pre-check reads changed, so it runs again


def test_a_document_removed_from_the_zip_disappears(env):
    folder = zip_folder(env, "zipped")
    env.pm.add_job("1", "client-zip", "zipped")
    env.run("1")
    with zipfile.ZipFile(folder / "Documents.zip") as z:
        content = {i.filename: z.read(i) for i in z.infolist() if "Debtors" not in i.filename}
    with zipfile.ZipFile(folder / "Documents.zip", "w") as z:
        for member, data in content.items():
            z.writestr(member, data)
    result = env.run("1")
    assert result["trail"]["read"]["documents"] == 4
    assert not any("does not agree to the trial balance" in c["label"] for c in result["trail"]["checked"]["detail"])
    assert not any("Debtors" in fid for fid in get_store().get_manifest("client-zip", "1"))


def test_zip_next_to_loose_files_and_a_zip_inside_a_zip(env):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("Workpaper - payroll.txt", "Payroll workpaper\nPrepared by AB on 3 May 2025\nConclusion: payroll agrees to the ledger.\n")
    folder = zip_folder(env, "mixed", inner_dir="", extra={"More/Inner.zip": inner.getvalue(), "backup.bak": b"\x00\x01"})
    (folder / "Notes for reviewer.txt").write_text("Engagement notes\nClient year end is 31 March 2025.\n", encoding="utf-8")
    env.pm.add_job("1", "client-zip", "mixed")
    result = env.run("1")
    detail = {d["name"]: d for d in result["trail"]["read"]["detail"]}
    assert "Notes for reviewer.txt" in detail  # a loose file beside the zip
    assert "Workpaper - payroll.txt (in Documents.zip)" in detail  # from the zip inside the zip
    assert detail["backup.bak (in Documents.zip)"]["problem"] == "This file type is not read by the pre-check."
    assert result["trail"]["read"]["documents"] == 8
    # A document inside the zip is stored for this client and task only.
    store = get_store()
    assert any(f["name"] == "Workpaper - payroll.txt" for f in store.get_manifest("client-zip", "1").values())
    assert not store.get_manifest("client-other", "1")


def test_a_broken_or_empty_zip_stops_with_a_plain_reason(env):
    folder = env.drive_root / "broken"
    folder.mkdir()
    (folder / "Documents.zip").write_bytes(b"this is not a zip file")
    env.pm.add_job("1", "client-zip", "broken")
    result = env.run("1")
    assert result["status"] == "failed" and "no documents the pre-check can read" in result["reason"]
    assert not env.precheck.calls

    # A broken zip beside good files is reported, and the rest is still checked.
    good = make_job_folder(env.drive_root, "partly")
    (good / "Extra.zip").write_bytes(b"nope")
    env.pm.add_job("2", "client-zip", "partly")
    result = env.run("2")
    assert result["status"] == "complete"
    problem = next(c for c in result["trail"]["checked"]["detail"] if "Extra.zip" in c["label"])
    assert not problem["passed"] and "could not be opened" in problem["note"]


def test_zip_limits_and_names(env):
    s = get_settings()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in range(s.max_zip_members + 5):
            z.writestr(f"f{n}.txt", "x")
    docs, problem = members(buf.getvalue(), {"id": "Z", "name": "Big.zip", "web_url": "u", "path": ""}, s)
    assert len(docs) == s.max_zip_members and "Only the first" in problem
    assert docs[0]["id"] == "Z!f0.txt" and docs[0]["path"] == "Big.zip/" and docs[0]["version"].endswith("-1")
    assert display_name(docs[0]) == "f0.txt (in Big.zip)" and display_name({"name": "TB.xlsx", "path": "sub/"}) == "TB.xlsx"
    assert members(b"junk", {"id": "Z", "name": "Bad.zip", "web_url": "u"}, s) == ([], "This zip file could not be opened.")
