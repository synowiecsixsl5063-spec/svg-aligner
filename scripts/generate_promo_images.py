#!/usr/bin/env python3
"""
Generate promotional images for svg-aligner project.

Creates:
  1. before_after_comparison.png — side-by-side alignment fix demo
  2. multi_ai_collaboration.png — multi-AI pipeline flowchart
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Arc
import numpy as np


def generate_before_after():
    """Generate before/after comparison showing alignment correction."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8), facecolor="#0d1117")

    for ax, title, is_corrected in [(ax1, "Before svg-aligner", False),
                                      (ax2, "After svg-aligner", True)]:
        ax.set_xlim(0, 500)
        ax.set_ylim(0, 400)
        ax.set_aspect("equal")
        ax.set_facecolor("#0d1117")

        # Title
        ax.set_title(title, color="white", fontsize=20, fontweight="bold", pad=15)

        # SVG canvas border
        canvas = mpatches.Rectangle((10, 10), 480, 380, fill=False,
                                      edgecolor="#30363d", linewidth=2,
                                      linestyle="--")
        ax.add_patch(canvas)
        ax.text(250, 385, "SVG Canvas (500×400)", color="#8b949e",
                ha="center", fontsize=9)

        # Colors
        colors = ["#58a6ff", "#3fb950", "#f0883e", "#bc8cff"]

        if not is_corrected:
            # BEFORE: misaligned boxes with offset
            boxes_before = [
                (50, 250, 100, 60, colors[0], "Header Box\nx=50"),
                (155, 250, 100, 60, colors[1], "Content Box\nx=155"),
                (257, 250, 100, 60, colors[2], "Side Box\nx=257"),
                (362, 250, 100, 60, colors[3], "Info Box\nx=362"),
            ]

            for x, y, w, h, color, label in boxes_before:
                bbox = FancyBboxPatch((x, y), w, h,
                                       boxstyle="round,pad=3",
                                       facecolor=color, edgecolor="white",
                                       linewidth=1.5, alpha=0.85)
                ax.add_patch(bbox)
                ax.text(x + w/2, y + h/2, label, color="white",
                        ha="center", va="center", fontsize=8, fontweight="bold")

            # Misaligned text items below
            text_items = [
                (48, 180, "Column 1\ntext", colors[0]),
                (51, 180, "Column 2\ntext", colors[1]),
                (52, 180, "Column 3\ntext", colors[2]),
            ]

            for x, y, label, color in text_items:
                bbox = FancyBboxPatch((x, y), 95, 35,
                                       boxstyle="round,pad=2",
                                       facecolor=color, edgecolor="white",
                                       linewidth=1.5, alpha=0.7)
                ax.add_patch(bbox)
                ax.text(x + 47, y + 17, label, color="white",
                        ha="center", va="center", fontsize=7)

            # Red warning markers for misalignment
            for bx in [50, 155, 257, 362]:
                ax.annotate("", xy=(bx, 240), xytext=(bx + 3, 245),
                           arrowprops=dict(arrowstyle="->", color="#f85149",
                                         lw=1.5, alpha=0.7))

            # Misalignment callout
            ax.annotate("2-5px\ndrift!", xy=(180, 280), fontsize=9,
                       color="#f85149", fontweight="bold",
                       ha="center", va="center",
                       bbox=dict(boxstyle="round", facecolor="#1a1a2e",
                                edgecolor="#f85149", alpha=0.9))

            # Red highlighting for text items
            for x in [48, 51, 52]:
                ax.plot([x + 47], [197], marker="x", color="#f85149",
                       markersize=12, mew=2, alpha=0.8)

        else:
            # AFTER: perfectly aligned
            boxes_after = [
                (50, 250, 100, 60, colors[0], "Header Box\nx=50"),
                (150, 250, 100, 60, colors[1], "Content Box\nx=150"),
                (250, 250, 100, 60, colors[2], "Side Box\nx=250"),
                (350, 250, 100, 60, colors[3], "Info Box\nx=350"),
            ]

            for x, y, w, h, color, label in boxes_after:
                bbox = FancyBboxPatch((x, y), w, h,
                                       boxstyle="round,pad=3",
                                       facecolor=color, edgecolor="white",
                                       linewidth=1.5, alpha=0.85)
                ax.add_patch(bbox)
                ax.text(x + w/2, y + h/2, label, color="white",
                        ha="center", va="center", fontsize=8, fontweight="bold")

            # Aligned text items
            text_items = [
                (50, 180, "Column 1\ntext", colors[0]),
                (50, 180, "Column 2\ntext", colors[1]),
                (50, 180, "Column 3\ntext", colors[2]),
            ]

            for x, y, label, color in text_items:
                bbox = FancyBboxPatch((x, y), 95, 35,
                                       boxstyle="round,pad=2",
                                       facecolor=color, edgecolor="white",
                                       linewidth=1.5, alpha=0.7)
                ax.add_patch(bbox)
                ax.text(x + 47, y + 17, label, color="white",
                        ha="center", va="center", fontsize=7)

            # Alignment lines
            for bx in [50, 150, 250, 350]:
                ax.axvline(x=bx, ymin=0.55, ymax=0.75, color="#3fb950",
                          linewidth=1.5, linestyle="--", alpha=0.6)

            # Green checkmarks
            ax.text(250, 290, "[OK] Perfectly Aligned", color="#3fb950",
                   fontsize=14, fontweight="bold", ha="center",
                   bbox=dict(boxstyle="round", facecolor="#1a1a2e",
                            edgecolor="#3fb950", alpha=0.9))

            # Arrow showing spacing is uniform
            for i in range(3):
                x_start = 50 + i * 100
                ax.annotate("", xy=(x_start + 92, 245), xytext=(x_start, 245),
                           arrowprops=dict(arrowstyle="<->", color="#3fb950",
                                         lw=1, alpha=0.5))
            ax.text(250, 232, "Equal 50px spacing", color="#3fb950",
                   fontsize=8, ha="center", alpha=0.7)

        # Legend for alignment
        ax.text(250, 120, "5px threshold algorithm", color="#8b949e",
               fontsize=9, ha="center")

        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    plt.suptitle("svg-aligner: Deterministic SVG Coordinate Correction",
                 color="white", fontsize=24, fontweight="bold", y=0.98)

    fig.text(0.5, 0.06,
             "LLM-generated SVG coordinates drift by 2-5px → svg-aligner detects & snaps to exact alignment",
             ha="center", color="#8b949e", fontsize=12)

    plt.tight_layout(rect=[0, 0.08, 1, 1])
    fig.savefig("C:/Users/20672/svg-aligner/docs/assets/before_after_comparison.png",
                dpi=150, facecolor="#0d1117", bbox_inches="tight")
    plt.close()
    print("[OK] before_after_comparison.png generated")


def generate_collaboration_flow():
    """Generate multi-AI collaboration pipeline flowchart."""
    fig, ax = plt.subplots(1, 1, figsize=(18, 6), facecolor="#0d1117")

    ax.set_xlim(0, 18)
    ax.set_ylim(0, 6)
    ax.set_aspect("equal")
    ax.set_facecolor("#0d1117")

    # Pipeline stages
    stages = [
        {"x": 1.5, "y": 3, "label": "Source\nDocument", "color": "#f0883e",
         "desc": "PDF / DOCX\nMarkdown / URL", "icon": "📄"},
        {"x": 4.5, "y": 3, "label": "Qwen\n(Structure)", "color": "#58a6ff",
         "desc": "Content extraction\n& structuring", "icon": "🧠"},
        {"x": 7.5, "y": 4.5, "label": "GPT\n(Images)", "color": "#3fb950",
         "desc": "AI image\ngeneration", "icon": "🎨"},
        {"x": 7.5, "y": 1.5, "label": "Claude Code\n(SVG Gen)", "color": "#bc8cff",
         "desc": "Complete SVG\nlayout creation", "icon": ""},
        {"x": 11.5, "y": 3, "label": "svg-aligner\n(Post-process)", "color": "#f85149",
         "desc": "5px threshold\nalignment fix", "icon": "🎯"},
        {"x": 15.5, "y": 3, "label": "PPTX\nExport", "color": "#d2a8ff",
         "desc": "Natively editable\nPowerPoint", "icon": "📊"},
    ]

    # Draw stages
    for stage in stages:
        x, y = stage["x"], stage["y"]
        color = stage["color"]

        # Main box
        box = FancyBboxPatch((x - 1.1, y - 0.7), 2.2, 1.4,
                              boxstyle="round,pad=8",
                              facecolor=color, edgecolor="white",
                              linewidth=2, alpha=0.9)
        ax.add_patch(box)

        # Icon
        ax.text(x, y + 0.3, stage["icon"], fontsize=22, ha="center", va="center")

        # Label
        ax.text(x, y - 0.2, stage["label"], color="white",
                fontsize=11, fontweight="bold", ha="center", va="center")

        # Description
        ax.text(x, y - 0.55, stage["desc"], color="white",
                fontsize=7, ha="center", va="center", alpha=0.8)

    # Arrows between stages
    arrows = [
        (2.6, 3, 3.4, 3, "#8b949e"),          # Source → Qwen
        (5.6, 3, 6.4, 4.2, "#8b949e"),         # Qwen → GPT
        (5.6, 3, 6.4, 1.8, "#8b949e"),         # Qwen → Claude
        (8.6, 4.2, 10.4, 3.3, "#8b949e"),      # GPT → svg-aligner
        (8.6, 1.8, 10.4, 2.7, "#8b949e"),      # Claude → svg-aligner
        (12.6, 3, 14.4, 3, "#3fb950"),         # svg-aligner → PPTX
    ]

    for x1, y1, x2, y2, color in arrows:
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                   arrowprops=dict(arrowstyle="->", color=color,
                                 lw=2.5, connectionstyle="arc3,rad=0"))

    # Parallel execution indicator
    parallel_box = FancyBboxPatch((6.2, 0.8), 2.6, 0.7,
                                   boxstyle="round,pad=5",
                                   facecolor="#1a1a2e", edgecolor="#8b949e",
                                   linewidth=1, alpha=0.7)
    ax.add_patch(parallel_box)
    ax.text(7.5, 1.15, " Parallel Execution", color="#8b949e",
            fontsize=8, ha="center", fontweight="bold")

    # Quality gate indicator
    gate_box = FancyBboxPatch((10.2, 5.0), 2.6, 0.6,
                               boxstyle="round,pad=5",
                               facecolor="#f8514920", edgecolor="#f85149",
                               linewidth=1, alpha=0.8)
    ax.add_patch(gate_box)
    ax.text(11.5, 5.3, "🔒 Quality Gate", color="#f85149",
            fontsize=8, ha="center", fontweight="bold")

    # Stats callout
    stats = [
        "[OK] 300+ pages stress-tested",
        "[OK] Zero dependencies",
        "[OK] 8 critical bugs fixed",
        "[OK] < 5px deviation detected",
    ]
    for i, stat in enumerate(stats):
        ax.text(16.8, 5.3 - i * 0.35, stat, color="#3fb950",
                fontsize=7, ha="right", alpha=0.8)

    # Title
    ax.set_title("Multi-AI Collaboration Pipeline with svg-aligner",
                 color="white", fontsize=20, fontweight="bold", pad=20)

    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()
    fig.savefig("C:/Users/20672/svg-aligner/docs/assets/multi_ai_collaboration.png",
                dpi=150, facecolor="#0d1117", bbox_inches="tight")
    plt.close()
    print("[OK] multi_ai_collaboration.png generated")


if __name__ == "__main__":
    import os
    os.makedirs("C:/Users/20672/svg-aligner/docs/assets", exist_ok=True)
    generate_before_after()
    generate_collaboration_flow()
    print("\nAll promotional images generated successfully!")
