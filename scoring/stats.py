"""Small statistics for Step 7, standard library only."""
import math

Z95 = 1.959964


def wilson(k, n, z=Z95):
    """95% Wilson score interval for k successes in n trials, as (low, high). (None, None) when n is 0.

    Better than the normal approximation at the sizes here (n = 40 episodes, 20 pairs), where it stays inside [0, 1]."""
    if not n:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value. b and c count the paired episodes where only one of the two conditions was right."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def cohen_kappa(pairs):
    """Cohen's kappa for a list of (rater_a, rater_b) labels. None when it is undefined (one label only)."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    labels = {x for pair in pairs for x in pair}
    expected = sum((sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n) for lab in labels)
    return None if expected == 1 else (observed - expected) / (1 - expected)
