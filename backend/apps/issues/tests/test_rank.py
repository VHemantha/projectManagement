import pytest

from apps.issues.rank import rank_after, rank_before, rank_between, rank_first


def test_rank_first_is_stable_and_nonempty():
    assert rank_first()


def test_rank_between_sorts_strictly_between_neighbors():
    a = rank_first()
    b = rank_after(a)
    assert a < b
    mid = rank_between(a, b)
    assert a < mid < b


def test_rank_before_sorts_before_reference():
    a = rank_first()
    before = rank_before(a)
    assert before < a


def test_repeated_inserts_between_same_neighbors_stay_ordered():
    a = rank_first()
    b = rank_after(a)
    inserted = []
    # insert 20 items between the same pair, each time between the last-inserted
    # value and `b`, and confirm strict ordering is preserved throughout.
    prev = a
    for _ in range(20):
        r = rank_between(prev, b)
        assert prev < r < b
        inserted.append(r)
        prev = r
    ranks = [a, *inserted, b]
    assert ranks == sorted(ranks)


def test_rank_between_rejects_inverted_bounds():
    a = rank_first()
    b = rank_after(a)
    with pytest.raises(ValueError):
        rank_between(b, a)
