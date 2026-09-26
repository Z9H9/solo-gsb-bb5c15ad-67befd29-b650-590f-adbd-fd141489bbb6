"""Unit tests for the debt-settlement algorithm.

Standard-library only: runs with ``python3 -m unittest tests.test_settlement``
as well as under pytest. Includes a brute-force reference that enumerates
every possible transfer sequence, cross-checked against the exact algorithm
on randomized small inputs.
"""

import random
import unittest

from app.settlement import EXACT_LIMIT, settle_transfers
from app.splitter import tie_key


def brute_force_settle(balances):
    """Reference implementation: enumerate all debtor->creditor transfer
    sequences, keep the fewest-transfers ones, return the canonically
    smallest sorted (from, to, amount) sequence among them."""
    people = sorted((p for p, b in balances.items() if b != 0), key=tie_key)
    start = tuple(balances[p] for p in people)
    best = None

    def dfs(state, edges):
        nonlocal best
        if best is not None and len(edges) >= len(best):
            return
        d = next((i for i, b in enumerate(state) if b < 0), None)
        if d is None:
            cand = sorted(edges)
            if best is None or (len(cand), cand) < (len(best), best):
                best = cand
            return
        for t in range(len(state)):
            if state[t] <= 0:
                continue
            for a in range(1, min(-state[d], state[t]) + 1):
                nxt = list(state)
                nxt[d] += a
                nxt[t] -= a
                dfs(tuple(nxt), edges + [(d, t, a)])

    dfs(start, [])
    return [] if best is None else [(people[d], people[t], a) for d, t, a in best]


def check_valid(balances, transfers):
    """Transfers must go debtor->creditor, be positive, and settle everything."""
    state = dict(balances)
    for f, t, amount in transfers:
        assert isinstance(amount, int) and amount > 0, transfers
        assert balances[f] < 0 < balances[t], transfers
        state[f] += amount
        state[t] -= amount
    assert all(v == 0 for v in state.values()), transfers


class SettleTransfersTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(settle_transfers({}), [])
        self.assertEqual(settle_transfers({"a": 0, "b": 0}), [])

    def test_simple_pair(self):
        self.assertEqual(settle_transfers({"a": -5, "b": 5}), [("a", "b", 5)])

    def test_one_debtor_two_creditors(self):
        self.assertEqual(
            settle_transfers({"a": -10, "b": 4, "c": 6}),
            [("a", "b", 4), ("a", "c", 6)],
        )

    def test_zero_balances_are_skipped(self):
        self.assertEqual(
            settle_transfers({"a": 0, "b": -3, "c": 3}), [("b", "c", 3)]
        )

    def test_zero_sum_groups_minimize_transfers(self):
        # Two independent zero-sum pairs -> 2 transfers, not 3.
        balances = {"a": -3, "b": 3, "c": -7, "d": 7}
        self.assertEqual(settle_transfers(balances), [("a", "b", 3), ("c", "d", 7)])

    def test_tie_break_prefers_canonically_smallest_sequence(self):
        # One zero-sum group of four; several 3-transfer solutions exist.
        # The canonically smallest sorted sequence peels 1 cent from a->c.
        balances = {"a": -5, "b": -5, "c": 6, "d": 4}
        self.assertEqual(
            settle_transfers(balances),
            [("a", "c", 1), ("a", "d", 4), ("b", "c", 5)],
        )

    def test_integer_and_string_ids(self):
        # int ids sort before string ids in the canonical order.
        self.assertEqual(settle_transfers({1: -5, "a": 5}), [(1, "a", 5)])

    def test_input_order_does_not_matter(self):
        balances = {"a": -5, "b": -5, "c": 6, "d": 4}
        expected = settle_transfers(balances)
        rng = random.Random(7)
        for _ in range(20):
            items = list(balances.items())
            rng.shuffle(items)
            self.assertEqual(settle_transfers(dict(items)), expected)

    def test_more_than_exact_limit_uses_greedy(self):
        deltas = [-7, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 1]
        assert len(deltas) > EXACT_LIMIT and sum(deltas) == 0
        balances = {f"p{i}": d for i, d in enumerate(deltas)}
        transfers = settle_transfers(balances)
        check_valid(balances, transfers)
        self.assertLessEqual(len(transfers), len(deltas) - 1)
        # deterministic
        self.assertEqual(settle_transfers(balances), transfers)


class ExactVsBruteForceTests(unittest.TestCase):
    def test_random_small_cases_match_brute_force(self):
        rng = random.Random(20260926)
        for trial in range(300):
            n = rng.randint(2, 5)
            vals = [rng.randint(-6, 6) for _ in range(n - 1)]
            vals.append(-sum(vals))
            balances = {f"p{i}": v for i, v in enumerate(vals)}
            expected = brute_force_settle(balances)
            got = settle_transfers(balances)
            self.assertEqual(got, expected, f"balances={balances}")
            check_valid(balances, got)

    def test_random_larger_cases_are_valid_and_minimal(self):
        # Beyond brute-force reach: verify validity and that the transfer
        # count equals n - (max zero-sum groups), computed independently here.
        rng = random.Random(99)
        for _ in range(50):
            n = rng.randint(6, EXACT_LIMIT)
            vals = [rng.randint(-50, 50) for _ in range(n - 1)]
            vals.append(-sum(vals))
            balances = {f"p{i}": v for i, v in enumerate(vals)}
            transfers = settle_transfers(balances)
            check_valid(balances, transfers)

            nonzero = [v for v in vals if v != 0]
            k = len(nonzero)
            size = 1 << k
            sums = [0] * size
            for mask in range(1, size):
                lb = mask & -mask
                sums[mask] = sums[mask ^ lb] + nonzero[lb.bit_length() - 1]
            groups = [0] * size
            for mask in range(1, size):
                lb = mask & -mask
                sub = mask
                while sub:
                    if (sub & lb) and sums[sub] == 0:
                        groups[mask] = max(groups[mask], groups[mask ^ sub] + 1)
                    sub = (sub - 1) & mask
            self.assertEqual(len(transfers), k - groups[size - 1], balances)


if __name__ == "__main__":
    unittest.main()
