"""Evidence: a quoted place in a document, built by code — never written by a model."""
from .archives import display_name
from .drive import link_to_place
from .textutil import sha


def evidence_from(file: dict, blocks: list[dict], quote: str = "") -> dict:
    """{id, file_id, file_name, location, quote, drive_url} for one or more consecutive blocks."""
    first, last = blocks[0], blocks[-1]
    location = first["loc"] if first is last else f"{first['loc']} to {last['loc'].split(', ')[-1]}"
    quote = (quote or " ".join(b["text"] for b in blocks)).strip()
    if len(quote) > 500:
        quote = quote[:497] + "…"
    return {
        "id": "E-" + sha(file["file_id"], file["version"], location, quote)[:10],
        "file_id": file["file_id"],
        "file_name": display_name(file),
        "location": location,
        "quote": quote,
        "drive_url": link_to_place(file, first),
    }


def file_evidence(file: dict) -> dict:
    """Evidence that a file is in the folder: its name, linked."""
    block = {"text": file["name"], "loc": "file in the task folder", "section": "listing", "sheet": None, "row": None, "a1": None, "page": None}
    return evidence_from(file, [block], display_name(file))
