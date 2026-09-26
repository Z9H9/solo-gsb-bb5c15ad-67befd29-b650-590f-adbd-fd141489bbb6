"""Debt settlement: turn paid-minus-owed balances into transfers.

Pure standard library. Balances are integer cents (``paid - owed``): a
positive balance means the passenger overpaid and should receive money, a
negative one means they still owe. Every transfer goes from a debtor
(negative balance) to a creditor (positive balance).

For up to ``EXACT_LIMIT`` non-zero balances the globally minimal number of
transfers is computed exactly. The key observation is that a minimal
solution is a forest of debtor->creditor edges whose components are
zero-sum groups, so ``min_transfers = n - (max zero-sum groups)``, found
with a subset DP. Among all minimal solutions the lexicographically
smallest canonical ``(from, to, amount)`` sequence is returned, so the
result is unique and independent of the input order of passengers and
payments. Beyond ``EXACT_LIMIT`` participants a deterministic greedy is
used instead.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .splitter import tie_key

# Up to this many non-zero balances the exact global minimum is computed.
EXACT_LIMIT = 12

Transfer = Tuple[object, object, int]  # (from_id, to_id, amount)


def _zero_sum_groups(vals: List[int]) -> Tuple[List[int], List[int]]:
    """Subset sums and max zero-sum-group counts for the multiset ``vals``.

    Returns ``(sums, groups)`` indexed by bitmask: ``sums[mask]`` is the sum
    of the selected values and ``groups[mask]`` the maximum number of
    zero-sum groups the selected sub-multiset can be partitioned into. The
    ``groups`` entry is only meaningful for masks whose sum is zero (any
    zero-sum mask can be partitioned, at least into itself).
    """
    size = 1 << len(vals)
    sums = [0] * size
    for mask in range(1, size):
        lb = mask & -mask
        sums[mask] = sums[mask ^ lb] + vals[lb.bit_length() - 1]
    groups = [0] * size
    for mask in range(1, size):
        lb = mask & -mask
        best = 0
        sub = mask
        while sub:
            if (sub & lb) and sums[sub] == 0:
                cand = groups[mask ^ sub] + 1
                if cand > best:
                    best = cand
            sub = (sub - 1) & mask
        groups[mask] = best
    return sums, groups


def _exact_edges(bal: List[int]) -> List[Tuple[int, int, int]]:
    """Minimal, canonically smallest transfer sequence for balances ``bal``.

    ``bal`` holds non-zero balances in canonical passenger order (so index
    order == canonical id order). Returns ``(debtor, creditor, amount)``
    index triples in canonical sorted order.

    The sequence is built position by position: the next transfer's ``from``
    is always the smallest remaining debtor (every debtor must pay, so its
    transfers sort first); ``to`` and ``amount`` are then the smallest
    values that still allow a minimal completion. A transfer ``(f, t, a)``
    admits a minimal completion iff the remaining state gains exactly one
    zero-sum group, which — with ``U`` ranging over subsets of the other
    participants — is equivalent to ``a = debt - sum(S)`` for some
    ``S ⊆ U`` with ``sum(U) = debt - credit`` and the rest partitionable
    into ``groups - 1`` zero-sum groups.
    """
    state = list(bal)
    _, groups = _zero_sum_groups(state)
    budget = len(state) - groups[(1 << len(state)) - 1]  # transfers still needed
    edges: List[Tuple[int, int, int]] = []

    while budget:
        nonzero = [i for i, b in enumerate(state) if b != 0]
        max_groups = len(nonzero) - budget  # zero-sum groups of current state
        f = next(i for i in nonzero if state[i] < 0)  # smallest debtor
        debt = -state[f]

        for t in nonzero:
            credit = state[t]
            if credit <= 0:
                continue
            cap = min(debt, credit)
            others = [i for i in nonzero if i != f and i != t]
            sums, g2 = _zero_sum_groups([state[i] for i in others])
            full = (1 << len(others)) - 1
            target = debt - credit  # required sum of U = f's and t's group-mates
            best_a = None
            for u in range(full + 1):
                if sums[u] != target or g2[full ^ u] != max_groups - 1:
                    continue
                s = u
                while True:
                    a = debt - sums[s]
                    if 1 <= a <= cap and (best_a is None or a < best_a):
                        best_a = a
                    if s == 0:
                        break
                    s = (s - 1) & u
                if best_a == 1:  # cannot do better
                    break
            if best_a is not None:
                edges.append((f, t, best_a))
                state[f] += best_a
                state[t] -= best_a
                budget -= 1
                break
        else:  # pragma: no cover - unreachable when balances sum to zero
            raise RuntimeError("no feasible transfer found; balances must sum to zero")

    return edges


def _greedy_edges(bal: List[int]) -> List[Tuple[int, int, int]]:
    """Deterministic settlement for groups too large for the exact search.

    Repeatedly pairs the canonically smallest debtor with the smallest
    creditor and transfers the larger settleable amount, so at least one
    side is settled per transfer (<= n - 1 transfers).
    """
    state = list(bal)
    edges: List[Tuple[int, int, int]] = []
    while True:
        debtor = creditor = None
        for i, b in enumerate(state):
            if b < 0 and debtor is None:
                debtor = i
            elif b > 0 and creditor is None:
                creditor = i
        if debtor is None or creditor is None:
            return edges
        amount = min(-state[debtor], state[creditor])
        edges.append((debtor, creditor, amount))
        state[debtor] += amount
        state[creditor] -= amount


def settle_transfers(balances: Dict) -> List[Transfer]:
    """Turn ``passenger id -> paid - owed`` balances into transfers.

    Returns a list of ``(from_id, to_id, amount)`` triples (integer cents,
    debtor -> creditor) sorted by the canonical id order of ``from`` then
    ``to`` then amount. For at most ``EXACT_LIMIT`` non-zero balances the
    number of transfers is the global minimum and the sequence is the
    canonically smallest among all minimal solutions; the outcome never
    depends on the iteration order of ``balances``.
    """
    people = sorted((pid for pid, b in balances.items() if b != 0), key=tie_key)
    if len(people) < 2:
        return []
    bal = [balances[pid] for pid in people]
    if len(bal) > EXACT_LIMIT:
        edges = _greedy_edges(bal)
    else:
        edges = _exact_edges(bal)
    edges.sort()
    return [(people[d], people[c], amount) for d, c, amount in edges]
