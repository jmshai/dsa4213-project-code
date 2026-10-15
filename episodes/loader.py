"""Load the suite. `episodes()` yields the 40 episodes (two per pair) in a fixed order."""
import json
from pathlib import Path

PAIRS_DIR = Path(__file__).parent / "pairs"


def load_pairs(pairs_dir=PAIRS_DIR):
    return [json.loads(p.read_text()) for p in sorted(Path(pairs_dir).glob("*.json"))]


def episodes(pairs_dir=PAIRS_DIR):
    """Yield dicts with the episode id, the pair it belongs to, the probe label and the probe.

    Systems may use only `pair["sessions"][i]["text"]` and `probe["text"]`. Everything else is gold.
    """
    for pair in load_pairs(pairs_dir):
        for label in ("A", "B"):
            yield {"episode_id": pair["pair_id"] + label.lower(), "pair": pair, "label": label, "probe": pair["probes"][label]}
