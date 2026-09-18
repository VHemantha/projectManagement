"""Simplified LexoRank-style lexicographic ranking.

Ranks are base-36 strings ("0"-"9", "A"-"Z"). `rank_between(prev, nxt)` returns a
string that sorts strictly between `prev` and `nxt` (either may be None to mean
"start of list" / "end of list"), so drag-and-drop reordering only ever rewrites
the rank of the moved row, never its neighbors.
"""

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)
_MAX_DEPTH = 60


def _char_val(c: str) -> int:
    return ALPHABET.index(c)


def rank_between(prev: str | None, nxt: str | None) -> str:
    prev = prev or ""
    nxt = nxt or ""
    if prev and nxt and prev >= nxt:
        raise ValueError(f"prev rank {prev!r} must sort before nxt rank {nxt!r}")

    result = []
    i = 0
    while True:
        p = _char_val(prev[i]) if i < len(prev) else 0
        n = _char_val(nxt[i]) if i < len(nxt) else BASE
        if p == n:
            result.append(ALPHABET[p])
            i += 1
            continue
        if n - p > 1:
            result.append(ALPHABET[(p + n) // 2])
            break
        # adjacent characters: keep prev's digit and go one level deeper
        result.append(ALPHABET[p])
        i += 1
        if i > _MAX_DEPTH:
            result.append(ALPHABET[BASE // 2])
            break
    return "".join(result)


def rank_first() -> str:
    return rank_between(None, None)


def rank_after(prev: str) -> str:
    return rank_between(prev, None)


def rank_before(nxt: str) -> str:
    return rank_between(None, nxt)
