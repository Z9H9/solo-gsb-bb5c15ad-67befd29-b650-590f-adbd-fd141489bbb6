"""Unit tests for the core splitting algorithm.

Standard-library only: runs with ``python3 -m unittest tests.test_splitter``
as well as under pytest.
"""

import random
import unittest
from types import SimpleNamespace as P

from app.splitter import split_fares


def ride(pid, board, alight):
    return P(id=pid, board=board, alight=alight)


class SplitFaresTests(unittest.TestCase):
    def test_even_split_single_segment(self):
        totals, details = split_fares([90], [ride("a", 0, 1), ride("b", 0, 1)])
        self.assertEqual(totals, {"a": 45, "b": 45})
        self.assertEqual(details[0]["shares"], {"a": 45, "b": 45})

    def test_remainder_tie_broken_by_id(self):
        # 10 / 3 -> base 3, remainder 1; all deficits equal, id "a" wins.
        totals, _ = split_fares([10], [ride("c", 0, 1), ride("a", 0, 1), ride("b", 0, 1)])
        self.assertEqual(totals, {"a": 4, "b": 3, "c": 3})

    def test_deficit_beats_id_order(self):
        # seg0: a,b,c share 10 -> a=4 (id tiebreak), b=3, c=3.
        # seg1: a,b share 7 -> base 3 rem 1; b's deficit (5/6) > a's (-1/6),
        # so b gets the extra cent despite "a" < "b".
        passengers = [ride("a", 0, 2), ride("b", 0, 2), ride("c", 0, 1)]
        totals, details = split_fares([10, 7], passengers)
        self.assertEqual(totals, {"a": 7, "b": 7, "c": 3})
        self.assertEqual(details[1]["shares"], {"a": 3, "b": 4})

    def test_remainder_rotates_over_segments(self):
        passengers = [ride("a", 0, 3), ride("b", 0, 3), ride("c", 0, 3)]
        totals, details = split_fares([100, 100, 100], passengers)
        self.assertEqual(totals, {"a": 100, "b": 100, "c": 100})
        self.assertEqual([d["shares"] for d in details], [
            {"a": 34, "b": 33, "c": 33},
            {"a": 33, "b": 34, "c": 33},
            {"a": 33, "b": 33, "c": 34},
        ])

    def test_passengers_only_pay_while_on_board(self):
        passengers = [ride("alice", 0, 3), ride("bob", 1, 3), ride("carol", 0, 1)]
        totals, details = split_fares([100, 251, 80], passengers)
        # seg1: alice and bob tie on deficit -> alice (id) gets the odd cent.
        self.assertEqual(totals, {"alice": 216, "bob": 165, "carol": 50})
        self.assertEqual(details[0]["passengers"], ["alice", "carol"])
        self.assertEqual(details[1]["shares"], {"alice": 126, "bob": 125})
        self.assertEqual(sum(totals.values()), 431)

    def test_zero_cost_empty_segment_is_allowed(self):
        totals, details = split_fares([0, 10], [ride("a", 1, 2)])
        self.assertEqual(totals, {"a": 10})
        self.assertEqual(details[0], {"index": 0, "cost": 0, "passengers": [], "shares": {}})

    def test_integer_ids_sort_numerically_on_ties(self):
        # id 9 < id 10 numerically, so 9 wins the tie (string order would
        # pick "10" first).
        totals, _ = split_fares([10], [ride(10, 0, 1), ride(9, 0, 1), ride(11, 0, 1)])
        self.assertEqual(totals, {9: 4, 10: 3, 11: 3})


class PropertyTests(unittest.TestCase):
    def test_conservation_invariance_and_fairness(self):
        rng = random.Random(20260919)
        for _ in range(500):
            n_seg = rng.randint(1, 8)
            segments = [rng.randint(0, 999) for _ in range(n_seg)]
            passengers = [ride("anchor", 0, n_seg)]  # covers every segment
            for i in range(rng.randint(0, 5)):
                board = rng.randint(0, n_seg - 1)
                alight = rng.randint(board + 1, n_seg)
                passengers.append(ride(f"p{i}", board, alight))

            totals, details = split_fares(segments, passengers)

            # conservation: per segment and overall
            for seg, cost in zip(details, segments):
                self.assertEqual(sum(seg["shares"].values()), cost)
                n = len(seg["passengers"])
                if n:
                    base, rem = divmod(cost, n)
                    # every share is the equal split or the equal split + 1,
                    # and exactly `rem` passengers get the extra cent
                    self.assertEqual(sorted(seg["shares"].values()),
                                     [base] * (n - rem) + [base + 1] * rem)
            self.assertEqual(sum(totals.values()), sum(segments))

            # input-order invariance: shuffling passengers changes nothing
            shuffled = passengers[:]
            rng.shuffle(shuffled)
            totals2, details2 = split_fares(segments, shuffled)
            self.assertEqual(totals, totals2)
            self.assertEqual(details, details2)


if __name__ == "__main__":
    unittest.main()
