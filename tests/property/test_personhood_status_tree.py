"""Proofs for the sorted Merkle status tree: membership + non-membership soundness."""

import pytest

from knitweb.core import crypto
from knitweb.personhood.status_tree import (
    EMPTY_ROOT,
    NonMembershipProof,
    StatusTree,
    verify_membership,
    verify_non_membership,
)


def _ptr(i: int) -> str:
    return crypto.sha256(f"revocation-pointer-{i}".encode()).hex()


@pytest.mark.property
def test_empty_tree_root_and_non_membership():
    tree = StatusTree([])
    assert tree.root() == EMPTY_ROOT
    assert tree.length == 0
    proof = tree.prove_non_membership(_ptr(99))
    assert verify_non_membership(tree.root(), tree.length, proof)
    with pytest.raises(KeyError):
        tree.prove_membership(_ptr(99))


@pytest.mark.property
@pytest.mark.parametrize("size", list(range(0, 18)))
def test_membership_and_non_membership_for_all_sizes(size):
    revoked = [_ptr(i) for i in range(size)]
    tree = StatusTree(revoked)
    root, length = tree.root(), tree.length
    assert length == size

    # every revoked pointer has a verifying membership proof
    for p in revoked:
        mp = tree.prove_membership(p)
        assert verify_membership(root, length, mp)

    # an unrevoked pointer has a verifying non-membership proof
    absent = _ptr(10_000 + size)
    assert not tree.contains(absent)
    nmp = tree.prove_non_membership(absent)
    assert verify_non_membership(root, length, nmp)


@pytest.mark.property
def test_membership_proof_fails_against_wrong_root():
    tree = StatusTree([_ptr(i) for i in range(5)])
    mp = tree.prove_membership(_ptr(2))
    wrong_root = crypto.sha256(b"not-the-root").hex()
    assert not verify_membership(wrong_root, tree.length, mp)


@pytest.mark.property
def test_tampered_membership_path_fails():
    tree = StatusTree([_ptr(i) for i in range(7)])
    mp = tree.prove_membership(_ptr(3))
    assert verify_membership(tree.root(), tree.length, mp)
    if mp.path:
        sib_hex, sib_right = mp.path[0]
        forged_path = [(crypto.sha256(b"forged").hex(), sib_right)] + list(mp.path[1:])
        forged = type(mp)(index=mp.index, length=mp.length, pointer=mp.pointer, path=forged_path)
        assert not verify_membership(tree.root(), tree.length, forged)


@pytest.mark.property
def test_cannot_forge_non_membership_for_an_actual_member():
    revoked = [_ptr(i) for i in range(8)]
    tree = StatusTree(revoked)
    # pick a real member and find its sorted index
    member = tree.revoked[3]
    assert tree.contains(member)
    # the honest API refuses to build a non-membership proof for a member
    with pytest.raises(KeyError):
        tree.prove_non_membership(member)
    # a hand-built "bracket" around the member cannot verify: the adjacent neighbours
    # either are not adjacent or one equals the member (strict inequality fails).
    idx = tree.revoked.index(member)
    lo = tree._membership_at(idx - 1)
    hi = tree._membership_at(idx)  # hi.pointer == member -> member < member is false
    forged = NonMembershipProof(pointer=member, lo=lo, hi=hi)
    assert not verify_non_membership(tree.root(), tree.length, forged)


@pytest.mark.property
def test_non_membership_below_first_and_above_last():
    # Build a tree whose sorted pointers have a known min/max, then query outside both ends.
    revoked = [_ptr(i) for i in range(1, 12)]
    tree = StatusTree(revoked)
    smallest = tree.revoked[0]
    largest = tree.revoked[-1]
    below = (int(smallest, 16) - 1).to_bytes(32, "big").hex()
    above = (int(largest, 16) + 1).to_bytes(32, "big").hex()
    assert not tree.contains(below) and not tree.contains(above)
    assert verify_non_membership(tree.root(), tree.length, tree.prove_non_membership(below))
    assert verify_non_membership(tree.root(), tree.length, tree.prove_non_membership(above))


@pytest.mark.property
def test_dedup_and_order_independence():
    ptrs = [_ptr(i) for i in range(6)]
    a = StatusTree(ptrs + ptrs)  # duplicates
    b = StatusTree(list(reversed(ptrs)))
    assert a.root() == b.root()
    assert a.length == b.length == 6
