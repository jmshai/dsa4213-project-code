"""config.toml and the repo root, read once. Paths inside config.toml are relative to ROOT."""
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG = tomllib.loads((ROOT / "config.toml").read_text())
