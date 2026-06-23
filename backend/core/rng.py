"""Deterministic PRNG (mulberry32) so a given URL yields stable demo datasets.

Ported from the former frontend services/random.ts.
"""

from __future__ import annotations

MASK = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    return ((a & MASK) * (b & MASK)) & MASK


def hash_string(s: str) -> int:
    h = (1779033703 ^ len(s)) & MASK
    for ch in s:
        h = _imul(h ^ ord(ch), 3432918353)
        h = ((h << 13) | (h >> 19)) & MASK
    return h & MASK


class SeededRandom:
    def __init__(self, seed: "int | str"):
        self.state = hash_string(seed) if isinstance(seed, str) else (seed & MASK)

    def next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & MASK
        a = self.state
        t = _imul(a ^ (a >> 15), 1 | a)
        t = (((t + _imul(t ^ (t >> 7), 61 | t)) & MASK) ^ t) & MASK
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    def randint(self, lo: int, hi: int) -> int:
        return int(self.next() * (hi - lo + 1)) + lo

    def pick(self, arr: list):
        return arr[int(self.next() * len(arr))]

    def weighted(self, items: list, weights: list):
        total = sum(weights)
        r = self.next() * total
        for item, w in zip(items, weights):
            r -= w
            if r <= 0:
                return item
        return items[-1]

    def boolean(self, prob_true: float) -> bool:
        return self.next() < prob_true
