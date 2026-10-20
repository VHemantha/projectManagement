"""The knowledge store (ChromaDB): every entry tagged team / vendor / project / task, a search
filtered on the tags first and only then by meaning, and documents never leaving their vendor."""
import pytest

from precheck_agent.embeddings import get_embedder
from precheck_agent.knowledge import Scope, ScopeError, get_knowledge, where_for

from .conftest import add_key_documents, make_job_folder

SMITH_1 = Scope(team="team-1", vendor="client-smith", project="project-rentals", task="1")
SMITH_2 = Scope(team="team-1", vendor="client-smith", project="project-rentals", task="2")
SMITH_OTHER_PROJECT = Scope(team="team-1", vendor="client-smith", project="project-gst", task="3")
JONES = Scope(team="team-1", vendor="client-jones", project="project-rentals", task="4")


def chunk(i, text, cls="bank", role="current"):
    return {"id": i, "text": text, "embedding": get_embedder().embed([text])[0], "file_version": "v1", "seq": 0, "location": "line 1",
            "document_class": cls, "content_hash": i, "tokens": 10, "blocks": [{"text": text, "loc": "line 1"}], "year_role": role}


def ids(entries):
    return sorted(e["id"] for e in entries)


def test_a_search_filters_on_the_card_tags_first_and_never_crosses_a_vendor(env):
    kn = get_knowledge()
    text = "Rent received from Barfoot and Thompson 2,390.00"
    for scope, i in ((SMITH_1, "s1"), (SMITH_2, "s2"), (SMITH_OTHER_PROJECT, "s3"), (JONES, "j4")):
        kn.replace_file(scope, f"file-{i}", [chunk(i, text)])
    q = get_embedder().embed([text])[0]

    # The same words are in every task, but each level returns only what its tags allow.
    assert ids(kn.search(SMITH_1, q, 10, level="task")) == ["s1"]
    assert ids(kn.search(SMITH_1, q, 10, level="project")) == ["s1", "s2"]
    assert ids(kn.search(SMITH_1, q, 10, level="vendor")) == ["s1", "s2", "s3"]
    assert "j4" not in ids(kn.search(SMITH_1, q, 10, level="vendor"))  # Jones is another vendor in the same team
    # Documents may not be searched across vendors, whatever is asked.
    for level in ("team", "firm"):
        with pytest.raises(ScopeError):
            kn.search(SMITH_1, q, 10, level=level)
    hit = kn.search(SMITH_1, q, 1)[0]
    assert (hit["team"], hit["vendor"], hit["project"], hit["task"], hit["source_type"]) == ("team-1", "client-smith", "project-rentals", "1", "document")
    assert hit["blocks"][0]["text"] == text and 0.99 < hit["score"] <= 1.0


def test_more_tags_narrow_the_search_before_meaning_is_compared(env):
    kn = get_knowledge()
    kn.replace_file(SMITH_1, "bank-25", [chunk("b25", "ANZ closing balance 4,210.00", "bank", "prior")])
    kn.replace_file(SMITH_1, "bank-26", [chunk("b26", "ANZ closing balance 5,020.00", "bank", "current")])
    kn.replace_file(SMITH_1, "fs-25", [chunk("f25", "Statement of financial position: bank 4,210", "financial_statements", "prior")])
    q = get_embedder().embed(["closing balance of the bank account"])[0]
    assert ids(kn.search(SMITH_1, q, 10, doc_class="bank")) == ["b25", "b26"]
    assert ids(kn.search(SMITH_1, q, 10, doc_class="bank", year_role="prior")) == ["b25"]
    assert ids(kn.search(SMITH_1, q, 10, doc_class=["bank", "financial_statements"], year_role="prior")) == ["b25", "f25"]
    assert where_for(SMITH_1, "task", ["document"], doc_class="bank") == {
        "$and": [{"source_type": {"$in": ["document"]}}, {"vendor": "client-smith"}, {"task": "1"}, {"doc_class": "bank"}]}


def test_shared_skills_reach_other_vendors_in_the_team_and_the_firm(env):
    kn = get_knowledge()
    rule = "Body corporate: always request the levy statement, a bank payment alone is not enough."
    e = get_embedder().embed([rule])[0]
    kn.put(Scope("team-1", "client-smith", "project-rentals", "1"), "skill", [{"id": "k-team", "text": rule, "embedding": e, "meta": {"status": "active"}}])
    kn.put(Scope("team-9", "client-other", "project-x", "9"), "skill", [{"id": "k-other-team", "text": rule, "embedding": e, "meta": {"status": "active"}}])
    assert ids(kn.search(JONES, e, 10, level="team", source_types=["skill"])) == ["k-team"]  # same team, another vendor
    assert ids(kn.search(JONES, e, 10, level="firm", source_types=["skill"])) == ["k-other-team", "k-team"]
    assert ids(kn.search(JONES, e, 10, level="vendor", source_types=["skill"])) == []


def test_a_run_tags_every_chunk_and_forgets_a_removed_file(env):
    folder = add_key_documents(make_job_folder(env.drive_root, "acme"))
    env.pm.add_job("1", "client-acme", "acme")
    assert env.run("1")["status"] == "complete"
    scope = Scope.of(env.pm.jobs["1"])
    chunks = get_knowledge().get(scope)
    assert chunks and {(c["team"], c["vendor"], c["project"], c["task"]) for c in chunks} == {("team-1", "client-acme", "project-client-acme", "1")}
    assert {c["year_role"] for c in chunks} <= {"current", "prior", "older", "unknown"} and all("doc_class" in c for c in chunks)
    tb = [c for c in chunks if c["doc_class"] == "trial_balance"]
    assert tb and tb[0]["location"]

    (folder / "Debtors schedule.xlsx").unlink()
    env.run("1")
    assert not [c for c in get_knowledge().get(scope) if "Debtors schedule" in c["text"]]


def test_files_indexed_before_the_knowledge_store_are_indexed_again_without_reading_images_again(env):
    """Before 12 Oct 2026 chunks were in the SQL store. The manifest says those files are unchanged,
    so they would never reach ChromaDB: a marker per file says which store and embedder hold its
    chunks, and a file without one is indexed again from its cached parse."""
    import io

    from PIL import Image

    from precheck_agent.store import StoreCache, get_store

    folder = add_key_documents(make_job_folder(env.drive_root, "acme"))
    out = io.BytesIO()
    Image.new("RGB", (600, 400), "white").save(out, "PNG")
    (folder / "Board minute.png").write_bytes(out.getvalue())
    env.pm.add_job("1", "client-acme", "acme")
    env.run("1")
    scope = Scope.of(env.pm.jobs["1"])
    before = get_knowledge().count(scope)
    images_read = len(env.vision.calls)
    assert before and images_read == 1

    # As after the upgrade: nothing in the knowledge store, no markers.
    get_knowledge().delete([c["id"] for c in get_knowledge().get(scope)])
    StoreCache(get_store()).clear([("indexed",)])
    assert get_knowledge().count(scope) == 0
    env.run("1")
    assert get_knowledge().count(scope) == before and len(env.vision.calls) == images_read  # the picture was not read again


def test_the_same_text_in_two_folders_is_one_result(env):
    """Landm, 12 Oct 2026: the client saved one loan statement in three folders, and the top three
    results were the same page three times."""
    kn = get_knowledge()
    page = "12 Jun 2025 5.150% $444.45 OD $225,000.00"
    for n, folder in enumerate(("Bank & loan", "Documents", "other banks")):
        kn.replace_file(SMITH_1, f"copy-{n}", [{**chunk(f"c{n}", f"911 to 1 oct.pdf ({folder}) page 2\n{page}")}])
    kn.replace_file(SMITH_1, "other", [chunk("o1", "Loan interest 6.950% $599.79")])
    hits = kn.search(SMITH_1, get_embedder().embed([page])[0], 2)
    assert len(hits) == 2 and hits[0]["id"] in ("c0", "c1", "c2") and hits[1]["id"] == "o1"


def test_the_search_model_is_loaded_only_when_first_used():
    """About 180 MB once loaded, on a 1 GB server: a run that embeds nothing never loads it."""
    from precheck_agent.embeddings import FastEmbedder

    e = FastEmbedder("BAAI/bge-small-en-v1.5", "")
    assert e.name == "fastembed:BAAI/bge-small-en-v1.5" and e._model is None


def test_the_search_model_embeds_a_few_chunks_at_a_time_on_few_threads(monkeypatch):
    """fastembed's default (256 chunks at once, every core) needed gigabytes and sent the server
    into swap; the configured batch and thread limits reach it."""
    import sys
    import types

    import numpy as np

    from precheck_agent import config
    from precheck_agent.embeddings import get_embedder

    seen = {}

    class FakeTextEmbedding:
        def __init__(self, model_name, cache_dir=None, threads=None):
            seen["threads"] = threads

        def embed(self, texts, batch_size=256):
            seen["batch_size"] = batch_size
            return [np.ones(3, dtype=np.float32) for _ in texts]

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    monkeypatch.setenv("PRECHECK_EMBEDDER", "fastembed")
    config.get_settings.cache_clear()
    get_embedder.cache_clear()
    try:
        vectors = get_embedder().embed(["a", "b"])
    finally:
        config.get_settings.cache_clear()
        get_embedder.cache_clear()
    assert seen == {"threads": 2, "batch_size": 8}
    assert vectors.shape == (2, 3) and np.allclose(np.linalg.norm(vectors, axis=1), 1)


def test_a_lost_knowledge_store_is_rebuilt_even_though_the_markers_say_indexed(env):
    """The chroma folder lost or restored from an older backup while the markers in the SQL store
    survive (seen locally on 12 Oct 2026: a run found 0 chunks). Files and zip members with text
    are indexed again from their cached parse."""
    import zipfile

    folder = add_key_documents(make_job_folder(env.drive_root, "acme"))
    with zipfile.ZipFile(folder / "Pack.zip", "w") as z:
        z.writestr("Pack/Notes.txt", "Owner notes: the ASB loan was refinanced in October.\n")
    env.pm.add_job("1", "client-acme", "acme")
    env.run("1")
    scope = Scope.of(env.pm.jobs["1"])
    before = get_knowledge().file_ids(scope)
    assert any("Pack.zip!" in f for f in before)
    get_knowledge().delete([c["id"] for c in get_knowledge().get(scope)])  # the markers stay
    env.run("1")
    assert get_knowledge().file_ids(scope) == before
