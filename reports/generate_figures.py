#!/usr/bin/env python3
"""Recreate five DSA4213 summary figures from the 2026-10-25 scoring report.

Data below are transcribed from reports/summary.md (320 runs, 8 conditions).
Edit TITLES, LABELS, COLORS, and figsize settings to customize.

Usage:
    uv run --with matplotlib --with numpy python reports/generate_figures.py
or:
    python generate_figures.py --output-dir reports/figures
"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

CONDITIONS = ["No memory", "Full transcript", "Mem0", "Mem0 + write", "Mem0 + read", "Supermemory", "Supermemory + write", "Supermemory + read"]
ADHERENCE = np.array([8, 32, 31, 24, 32, 34, 31, 37])
RETRIEVED_RIGHT_WRONG = np.array([0, 8, 9, 9, 8, 6, 8, 3])
IN_SCOPE = np.array([4, 17, 17, 10, 16, 18, 11, 20])
OUT_SCOPE = np.array([4, 15, 14, 14, 16, 16, 20, 17])
CONFLICT_TYPES = ["Project override", "Single-task override", "Conditional scope", "Same-scope supersession", "Same-scope specificity"]
CONFLICT_COUNTS = np.array([
    [4, 2, 2, 0, 0],
    [8, 4, 8, 8, 4],
    [6, 4, 8, 8, 5],
    [5, 2, 8, 4, 5],
    [7, 3, 8, 8, 6],
    [8, 4, 8, 8, 6],
    [5, 4, 7, 8, 7],
    [8, 6, 8, 8, 7],
])
# Failure categories from summary.md section 5, in the displayed order.
FAILURE_NAMES = ["No memory", "Extraction", "Retrieval", "Scope lost", "Tagging", "Reasoning"]
FAILURES = np.array([
    [32, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 8],
    [0, 0, 0, 5, 0, 4],
    [0, 7, 0, 0, 4, 5],
    [0, 0, 0, 4, 0, 4],
    [0, 0, 0, 0, 0, 6],
    [0, 0, 1, 0, 0, 8],
    [0, 0, 0, 0, 1, 2],
])

TITLES = {
    "01": "Correction adherence across experimental conditions",
    "02": "Failures despite retrieval of the expected memory",
    "03": "In-scope versus out-of-scope adherence",
    "04": "Adherence by memory-conflict type",
    "05": "Diagnostic classification of incorrect decisions",
}
COLORS = {"baseline": "#64748b", "write": "#e59a42", "read": "#287f8e", "control": "#a0aec0"}


def setup_style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 13,
                         "axes.labelsize": 10, "figure.dpi": 130, "savefig.dpi": 240,
                         "axes.spines.top": False, "axes.spines.right": False})


def condition_colors():
    return [COLORS["control"], COLORS["control"], COLORS["baseline"], COLORS["write"], COLORS["read"],
            COLORS["baseline"], COLORS["write"], COLORS["read"]]


def save(fig, output_dir, stem):
    fig.savefig(output_dir / f"{stem}.png", bbox_inches="tight", facecolor="white")
    fig.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def overall(output_dir):
    fig, ax = plt.subplots(figsize=(10, 5.4))
    y = np.arange(len(CONDITIONS))
    bars = ax.barh(y, ADHERENCE / 40 * 100, color=condition_colors())
    ax.set_yticks(y, CONDITIONS)
    ax.invert_yaxis()
    ax.set_xlim(0, 105)
    ax.set_xlabel("Correct decisions (%)")
    ax.set_title(TITLES["01"], loc="left", weight="bold", pad=14)
    for bar, n in zip(bars, ADHERENCE):
        ax.text(bar.get_width() + 1.2, bar.get_y() + bar.get_height()/2, f"{n}/40", va="center", fontsize=9)
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output_dir, "01_overall_adherence")


def retrieved(output_dir):
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    indices = list(range(2, 8))
    names = [CONDITIONS[i] for i in indices]
    values = RETRIEVED_RIGHT_WRONG[indices]
    y = np.arange(len(names))
    bars = ax.barh(y, values, color=[condition_colors()[i] for i in indices])
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 11)
    ax.set_xlabel("Runs with expected memory retrieved but wrong action (of 40)")
    ax.set_title(TITLES["02"], loc="left", weight="bold", pad=14)
    for bar, n in zip(bars, values):
        ax.text(n+.15, bar.get_y()+bar.get_height()/2, str(n), va="center")
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output_dir, "02_retrieved_but_wrong")


def in_out(output_dir):
    fig, ax = plt.subplots(figsize=(10.5, 5.3))
    x = np.arange(len(CONDITIONS))
    width = .38
    a = ax.bar(x-width/2, IN_SCOPE/20*100, width, label="In scope (A)", color="#287f8e")
    b = ax.bar(x+width/2, OUT_SCOPE/20*100, width, label="Out of scope (B)", color="#e59a42")
    ax.set_xticks(x, CONDITIONS, rotation=30, ha="right")
    ax.set_ylim(0, 113)
    ax.set_ylabel("Correct decisions (%)")
    ax.set_title(TITLES["03"], loc="left", weight="bold", pad=14)
    ax.legend(frameon=False, ncol=2)
    for bars in (a,b):
        for bar in bars:
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1.5, f"{bar.get_height():.0f}", ha="center", fontsize=8)
    ax.grid(axis="y", alpha=.18)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output_dir, "03_in_scope_vs_out_scope")


def heatmap(output_dir):
    fig, ax = plt.subplots(figsize=(10.5, 5.5))
    im = ax.imshow(CONFLICT_COUNTS/8*100, vmin=0, vmax=100, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(np.arange(len(CONFLICT_TYPES)), CONFLICT_TYPES, rotation=24, ha="right")
    ax.set_yticks(np.arange(len(CONDITIONS)), CONDITIONS)
    ax.set_title(TITLES["04"], loc="left", weight="bold", pad=14)
    for i in range(CONFLICT_COUNTS.shape[0]):
        for j in range(CONFLICT_COUNTS.shape[1]):
            n = CONFLICT_COUNTS[i,j]
            ax.text(j, i, f"{n}/8", ha="center", va="center", fontsize=9,
                    color="white" if n>=6 else "#17212b")
    cb = fig.colorbar(im, ax=ax, fraction=.03, pad=.025)
    cb.set_label("Correct (%)")
    fig.tight_layout()
    save(fig, output_dir, "04_conflict_heatmap")


def failure_stages(output_dir):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    y = np.arange(len(CONDITIONS))
    left = np.zeros(len(CONDITIONS))
    palette = ["#a0aec0", "#c76b4d", "#9467bd", "#e3a34d", "#b65d88", "#287f8e"]
    for j, name in enumerate(FAILURE_NAMES):
        vals = FAILURES[:,j]
        ax.barh(y, vals, left=left, label=name, color=palette[j])
        for i, n in enumerate(vals):
            if n >= 2:
                ax.text(left[i]+n/2, i, str(n), va="center", ha="center", fontsize=9, color="white" if j!=0 else "#17212b")
        left += vals
    ax.set_yticks(y, CONDITIONS)
    ax.invert_yaxis()
    ax.set_xlim(0, 36)
    ax.set_xlabel("Incorrect decisions (of 40)")
    ax.set_title(TITLES["05"], loc="left", weight="bold", pad=14)
    ax.legend(loc="upper center", bbox_to_anchor=(.5,-.13), ncol=3, frameon=False)
    ax.grid(axis="x", alpha=.18)
    ax.set_axisbelow(True)
    fig.tight_layout()
    save(fig, output_dir, "05_failure_stages")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("reports/figures"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    setup_style()
    for fn in (overall, retrieved, in_out, heatmap, failure_stages):
        fn(args.output_dir)
    print(f"Wrote 5 PNG and 5 PDF figures to {args.output_dir}")

if __name__ == "__main__":
    main()
