"""Render Figure 5: median per-turn entropy + similarity with 95% bootstrap CIs.

Needs the 'plots' extra (matplotlib). Two rows (entropy, similarity) x three
columns (ambiguity types), one line per condition.
"""

from __future__ import annotations

from .run_benchmark import RunRow, aggregate

_TYPES = ["attachment", "vague", "scope"]


def plot_figure5(rows: list[RunRow], out_path: str = "figure5.png") -> str:  # pragma: no cover
    import matplotlib.pyplot as plt

    agg = aggregate(rows)
    conditions = sorted({r.condition for r in rows})
    types = [t for t in _TYPES if any(r.ambiguity_type == t for r in rows)]
    turns = sorted({r.turn for r in rows})

    fig, axes = plt.subplots(2, len(types), figsize=(4 * len(types), 7), squeeze=False)
    for col, atype in enumerate(types):
        for row_i, metric in enumerate(("entropy", "similarity")):
            ax = axes[row_i][col]
            for cond in conditions:
                med, lo, hi = [], [], []
                xs = []
                for t in turns:
                    key = (cond, atype, t)
                    if key not in agg:
                        continue
                    m, l, h = agg[key][metric]
                    xs.append(t)
                    med.append(m)
                    lo.append(l)
                    hi.append(h)
                if xs:
                    ax.plot(xs, med, label=cond, linewidth=1.5)
                    ax.fill_between(xs, lo, hi, alpha=0.15)
            ax.set_title(f"{atype} — {metric}")
            ax.set_xlabel("Turn index")
            ax.set_ylabel(f"Median {metric}")
    axes[0][0].legend(fontsize=6, loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


__all__ = ["plot_figure5"]
