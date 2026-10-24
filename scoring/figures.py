"""Step 7 figures: PNGs for the written report, light mode. Needs matplotlib (uv add matplotlib); without it the
report is written without figures, since every figure's numbers are also in summary.md and reports/tables/.

Colors follow the dataviz reference palette and were checked with its validator: three categorical hues for the
scatter (all pairs, since every point can sit next to any other), five in fixed order for the stacked bar (adjacent
pairs), and one sequential blue ramp for the heatmap. Identity never rests on color alone: points are direct-labelled
and shaped by memory system, bars have a legend and in-segment counts where they fit.
"""
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
SEQUENTIAL = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
              "#1c5cab", "#184f95", "#104281", "#0d366b"]
LAYER = {"plain": (BLUE, "Baseline, as shipped"), "write": (ORANGE, "Scope layer, write-time"),
         "read": (AQUA, "Scope layer, read-time"), None: (MUTED, "No memory system")}
MARKER = {"mem0": ("o", "Mem0"), "supermemory": ("s", "Supermemory"), None: ("D", "No memory system")}
STAGE_COLORS = {"correct": "#e1e0d9", "no_memory": "#c3c2b7", "extraction": BLUE, "retrieval": ORANGE,
                "scope_lost": AQUA, "tagging": YELLOW, "reasoning": MAGENTA, "unknown": "#f0efec"}
TYPE_LABELS = {"project_override": "Project\noverride", "single_task_override": "Single-task\noverride",
               "conditional_scope": "Conditional\nscope", "same_scope_supersession": "Same-scope\nsupersession",
               "same_scope_specificity": "Same-scope\nspecificity"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold", "text.color": INK,
                         "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2, "axes.edgecolor": AXIS})
    return plt


def _frame(fig, ax):
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(length=0)


def _title(ax, title, subtitle):
    ax.set_title(title, loc="left", pad=24)
    ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction", xytext=(0, 7), textcoords="offset points", color=INK2,
                fontsize=8.5, va="bottom", ha="left")


def _pct_axis(axis):
    from matplotlib.ticker import FuncFormatter, MultipleLocator
    axis.set_major_locator(MultipleLocator(0.25))
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))


def _kind(info):
    return "plain" if info["system"] and not info["layer"] else info["layer"]


def adherence_vs_retention(adherence, retention, info, path):
    """One point per condition: retention on x, adherence on y, 95% Wilson whiskers on both."""
    plt = _plt()
    from matplotlib.lines import Line2D
    ret = {r["condition"]: r for r in retention}
    pts = [(a, ret[a["condition"]]) for a in adherence
           if a["adherence"] is not None and a["condition"] in ret and ret[a["condition"]]["retention"] is not None]
    if not pts:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 5.6), dpi=200)
    _frame(fig, ax)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for a, t in pts:
        i = info(a["condition"])
        ax.plot([t["ci_low"], t["ci_high"]], [a["adherence"]] * 2, color=GRID, lw=1.2, zorder=2, solid_capstyle="round")
        ax.plot([t["retention"]] * 2, [a["ci_low"], a["ci_high"]], color=GRID, lw=1.2, zorder=2, solid_capstyle="round")
        ax.scatter(t["retention"], a["adherence"], s=70, color=LAYER[_kind(i)][0], marker=MARKER.get(i["system"], MARKER[None])[0],
                   edgecolors=SURFACE, linewidths=2, zorder=4)
    ax.set_xlim(-0.02, 1.04)
    ax.set_ylim(-0.02, 1.04)
    _pct_axis(ax.xaxis)
    _pct_axis(ax.yaxis)
    ax.set_xlabel("Unrelated-memory retention (answers that kept the unrelated preference)")
    ax.set_ylabel("Correction adherence (episodes right)")
    _title(ax, "Correction adherence against unrelated-memory retention",
           f"One point per condition, {max(a['episodes'] for a, _ in pts)} episodes each. Whiskers: 95% Wilson intervals.")
    _label_points(fig, ax, [(t["retention"], a["adherence"], a["condition"]) for a, t in pts])
    kinds = list(dict.fromkeys(_kind(info(a["condition"])) for a, _ in pts))
    systems = list(dict.fromkeys(info(a["condition"])["system"] for a, _ in pts if info(a["condition"])["system"]))
    handles = [Line2D([], [], marker="o", ls="", color=LAYER[k][0], markersize=7, label=LAYER[k][1]) for k in kinds]
    handles += [Line2D([], [], marker=MARKER[s][0], ls="", color=MUTED, markerfacecolor="none", markersize=7, label=MARKER[s][1]) for s in systems]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, frameon=False, fontsize=8, labelcolor=INK2)
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path


def _label_points(fig, ax, points):
    """Direct labels beside each point. Each label takes the nearest free spot on rings around its point, joined to it
    by a hairline when it had to move; a label that finds no free spot takes the one with the least overlap."""
    import math
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    taken = []
    for x, y, _ in points:
        px, py = ax.transData.transform((x, y))
        taken.append(Bbox([[px - 10, py - 10], [px + 10, py + 10]]))
    frame = ax.get_window_extent(renderer)
    angles = (0, math.pi, math.pi / 6, -math.pi / 6, 5 * math.pi / 6, -5 * math.pi / 6, math.pi / 3, -math.pi / 3,
              2 * math.pi / 3, -2 * math.pi / 3)  # never straight up or down, where a leader line would hide in a whisker
    spots = [(r * math.cos(a), r * math.sin(a) * 1.4) for r in (9, 18, 28, 40, 54) for a in angles]

    def area(a, b):
        w, h = min(a.x1, b.x1) - max(a.x0, b.x0), min(a.y1, b.y1) - max(a.y0, b.y0)
        return w * h if w > 0 and h > 0 else 0

    style = {"textcoords": "offset points", "va": "center", "fontsize": 7.5, "color": INK2, "zorder": 5,
             "bbox": {"boxstyle": "round,pad=0.15", "fc": SURFACE, "ec": "none", "alpha": 0.9}}
    for x, y, label in sorted(points, key=lambda p: (-p[1], p[0])):
        best = None  # (clash, dx, dy, ha, box)
        for dx, dy in spots:
            ha = "left" if dx > 1 else "right" if dx < -1 else "center"
            t = ax.annotate(label, (x, y), xytext=(dx, dy), ha=ha, **style)
            box = t.get_window_extent(renderer).expanded(1.04, 1.2)  # measured without a leader line, so text only
            t.remove()
            clash = sum(area(box, o) for o in taken)
            if not (frame.x0 <= box.x0 and box.x1 <= frame.x1 and frame.y0 <= box.y0 and box.y1 <= frame.y1):
                clash += 1e9
            if best is None or clash < best[0]:
                best = (clash, dx, dy, ha, box)
            if clash == 0:
                break
        _, dx, dy, ha, box = best
        moved = math.hypot(dx, dy) > 10
        ax.annotate(label, (x, y), xytext=(dx, dy), ha=ha, **style,
                    arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.6, "shrinkA": 1, "shrinkB": 6} if moved else None)
        taken.append(box)


def adherence_heatmap(by_type, conditions, path):
    """Conditions by conflict type, shaded by adherence, each cell labelled with episodes right of episodes scored."""
    plt = _plt()
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
    types = list(TYPE_LABELS)
    cell = {(r["condition"], r["conflict_type"]): r for r in by_type}
    values = np.array([[cell[(c, t)]["adherence"] if (c, t) in cell and cell[(c, t)]["episodes"] else np.nan for t in types]
                       for c in conditions], dtype=float)
    if np.all(np.isnan(values)):
        return None
    cmap = LinearSegmentedColormap.from_list("sequential_blue", SEQUENTIAL).with_extremes(bad=SURFACE)
    fig, ax = plt.subplots(figsize=(7.4, 0.42 * len(conditions) + 1.9), dpi=200)
    _frame(fig, ax)
    image = ax.imshow(values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i, c in enumerate(conditions):
        for j, t in enumerate(types):
            r = cell.get((c, t))
            v = values[i, j]
            text = "–" if np.isnan(v) else f"{r['correct']}/{r['episodes']}"
            ax.text(j, i, text, ha="center", va="center", fontsize=8, color="white" if not np.isnan(v) and v >= 0.55 else INK)
    ax.set_xticks(range(len(types)), [TYPE_LABELS[t] for t in types], fontsize=8)
    ax.set_yticks(range(len(conditions)), conditions, fontsize=8)
    ax.set_xticks(np.arange(-0.5, len(types)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(conditions)), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    bar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02, ticks=[0, 0.5, 1])
    bar.ax.set_yticklabels(["0%", "50%", "100%"], fontsize=7.5, color=INK2)
    bar.ax.tick_params(length=0)
    bar.outline.set_visible(False)
    _title(ax, "Correction adherence by conflict type", "Episodes right of episodes scored in each cell. Darker is better.")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path


def _ink_for(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lum = 0.2126 * r ** 2.2 + 0.7152 * g ** 2.2 + 0.0722 * b ** 2.2
    return INK if lum > 0.28 else "white"


def failure_stages(stage_rows, path):
    """One stacked bar per condition: right answers, then each failure stage, as episodes."""
    plt = _plt()
    from matplotlib.patches import Patch
    rows = [r for r in stage_rows if r["episodes"]]
    if not rows:
        return None
    present = [s for s in STAGE_COLORS if any(r.get(s) for r in rows)]
    fig, ax = plt.subplots(figsize=(7.6, 0.42 * len(rows) + 1.6), dpi=200)
    _frame(fig, ax)
    ax.spines["left"].set_visible(False)
    names = [r["condition"] for r in rows]
    for i, r in enumerate(rows):
        left = 0
        for s in present:
            n = r.get(s, 0)
            if not n:
                continue
            ax.barh(i, n, left=left, height=0.62, color=STAGE_COLORS[s], edgecolor=SURFACE, linewidth=1.5, zorder=3)
            if n >= 2:
                ax.text(left + n / 2, i, str(n), ha="center", va="center", fontsize=7.5, color=_ink_for(STAGE_COLORS[s]), zorder=4)
            left += n
    ax.set_yticks(range(len(rows)), names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, max(r["episodes"] for r in rows))
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    labels = {"correct": "Right", "no_memory": "No memory (floor)", "extraction": "Extraction", "retrieval": "Retrieval",
              "scope_lost": "Scope lost", "tagging": "Tagging", "reasoning": "Reasoning", "unknown": "Not matched"}
    ax.legend(handles=[Patch(color=STAGE_COLORS[s], label=labels[s]) for s in present], loc="upper left", bbox_to_anchor=(0, 0),
              borderaxespad=2.2, ncol=min(len(present), 4), frameon=False, fontsize=7.5, labelcolor=INK2, handlelength=1, columnspacing=1.2)
    _title(ax, "Where the wrong answers went wrong",
           "Episodes per condition. Each wrong answer is counted once, at the first stage that failed.")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return path
