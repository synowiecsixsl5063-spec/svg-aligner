# svg-aligner

[![PyPI version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/synowiecsixsl5063-spec/svg-aligner)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#installation)

English | [中文](./README_CN.md) | [🌐 Promo Page](https://synowiecsixsl5063-spec.github.io/svg-aligner)

> **Deterministic SVG alignment post-processor for LLM-generated content.**

When LLMs write complete SVG XML by hand (as in [pptmaster](https://github.com/hugohe3/ppt-master)), visually grouped elements often end up with pixel-level coordinate drift — a row of boxes that *should* be left-aligned may have `x="120"`, `x="122"`, `x="119"`. **svg-aligner** detects these near-misses with a deterministic algorithm and snaps them to exact alignment, producing clean, predictable output without requiring a second LLM call.

## Why svg-aligner?

LLMs are **not layout engines**. When generating SVG from scratch, they produce coordinates that are *approximately* correct but drift by 2–4 pixels. This causes:

- Text boxes that look "glued together" instead of properly spaced
- Column headers that zigzag instead of forming a clean line
- Equal-spacing layouts that look "slightly off" to the human eye

svg-aligner fixes this deterministically — no AI hallucination risk, no API costs, predictable results every time.

| Problem | Before svg-aligner | After svg-aligner |
|---------|-------------------|-------------------|
| Left alignment drift | `x="120"`, `x="122"`, `x="119"` | `x="120"`, `x="120"`, `x="120"` |
| Uneven distribution | gaps: 2px, 3px, 1px | gaps: 2px, 2px, 2px |
| Text-anchor confusion | text visually at 194px vs rect at 192px | both snapped to 192px |
| Nested transform drift | deep element off by 3px vs sibling | both at exact same position |

## Core Algorithm

The aligner works in three stages:

1. **Absolute Coordinate Resolution** — Walks the full SVG DOM tree, resolving every leaf element (rect, text, path, …) into absolute root-space bounding boxes by composing ancestor `transform` matrices.  Text elements get special treatment: `text-anchor="middle"` and `"end"` are factored into the visual edge calculation so that alignment compares *what you see*, not just the anchor point.

2. **Range-Based Detection (5 px Hard Threshold)** — For each alignment dimension (LEFT / RIGHT / TOP / BOTTOM / CENTER_H / CENTER_V / DISTRIBUTE_H / DISTRIBUTE_V), elements whose relevant coordinate falls within a **cluster window** (`threshold × 3`) are grouped.  Within each group, the **range** (max − min) of that coordinate is computed.  If `range < ALIGN_THRESHOLD` (default **5 px**), the group is flagged for correction.  For distribution types, the algorithm checks the range of **edge-to-edge gaps** instead.

3. **Inverse-CTM Coordinate Write-Back** — Corrections are applied by computing the delta in absolute space, transforming it back through the inverse of the element's full coordinate transform matrix (`inv(parent_ctm × local_matrix)`), and adjusting the node's local attributes (`x`, `y`, `cx`, `d`, etc.).  A cross-axis deduplication step ensures each element is touched by at most one horizontal and one vertical correction, preventing cascading conflicts.

## Installation

### From source

```bash
git clone https://github.com/synowiecsixsl5063-spec/svg-aligner.git
cd svg-aligner
pip install -e .
```

### Direct install via pip

```bash
pip install git+https://github.com/synowiecsixsl5063-spec/svg-aligner.git
```

### No-install (standalone)

svg-aligner has **zero external dependencies** — it uses only the Python standard library.  You can drop `src/svg_aligner/core.py` into any project and import it directly.

## Quick Start

### CLI Mode

```bash
# Correct an SVG file in-place
svg-aligner input.svg

# Write to a new file
svg-aligner input.svg -o corrected.svg

# Dry-run: see what would change without modifying anything
svg-aligner input.svg --dry-run

# Custom threshold (3 px instead of default 5 px)
svg-aligner input.svg --dry-run --threshold 3
```

### Python Module

```python
from svg_aligner import process_svg

svg_string = open("input.svg").read()

# Dry-run: inspect planned corrections
out_svg, log = process_svg(svg_string, dry_run=True)
for action in log:
    print(f"{action['alignment_type']}: {len(action['affected_nodes'])} nodes, "
          f"range={action['range_px']:.1f}px")

# Apply corrections
corrected_svg, log = process_svg(svg_string, dry_run=False)
open("output.svg", "w").write(corrected_svg)
```

### Custom Threshold

```python
from svg_aligner import process_svg

# Use a stricter 3 px threshold
corrected_svg, log = process_svg(svg_string, threshold=3.0)
```

## Supported Element Types

| Element   | Attributes Modified            |
|-----------|-------------------------------|
| `rect`    | `x`, `y`                      |
| `circle`  | `cx`, `cy`                    |
| `ellipse` | `cx`, `cy`                    |
| `line`    | `x1`, `y1`, `x2`, `y2`        |
| `text`    | `x`, `y` (anchor-aware)       |
| `path`    | `d` (coordinate translation)  |
| `polygon` / `polyline` | `points`         |
| Other     | `transform` (fallback prepend)|

## Tests

```bash
# Run all tests (requires pytest)
pip install pytest
pytest tests/ -v

# Or with the built-in unittest module (no extra dependencies)
python -m unittest discover tests/ -v
```

The test suite covers:

- **Nested transforms** — Elements inside `<g transform="translate(...)">` resolve to correct absolute coordinates
- **Text-anchor awareness** — `middle` and `end` anchors are correctly inverted during write-back
- **Equal-spacing distribution** — Near-evenly-spaced elements are snapped to perfect arithmetic progression
- **Threshold guard** — Elements with offsets ≥ 5 px are left completely untouched
- **Dry-run mode** — SVG string is returned unmodified while still producing an action log
- **Multi-page batch** — Batch processing of multiple independent SVG strings

## Project Structure

```
svg-aligner/
├── src/
│   └── svg_aligner/
│       ├── __init__.py          # Public API exports
│       └── core.py              # Core algorithm (zero dependencies)
├── tests/
│   ├── __init__.py
│   ├── test_unit.py             # Unit tests
│   └── test_integration.py      # Integration / stress tests
├── examples/
│   └── sample_usage.py          # Usage examples
├── scripts/
│   └── generate_promo_images.py # Promotional image generator
├── docs/
│   └── assets/                  # Promotional images
├── README.md                    # English README
├── README_CN.md                 # Chinese README
├── INTEGRATION.md               # pptmaster integration guide
├── SOCIAL_MEDIA.md              # Social media promotional kit
├── LICENSE                      # MIT
├── .gitignore
└── pyproject.toml
```

## Multi-AI Collaboration

svg-aligner was built for and battle-tested in a multi-AI workflow pipeline:

```
Source Document → Qwen (structure extraction) → GPT (image generation)
    → Claude Code (SVG generation) → svg-aligner (coordinate correction)
    → PPTX export
```

In the pptmaster project, svg-aligner serves as the **final quality gate** after SVG generation:

1. **Claude Code** generates complete SVG slides with rich layouts
2. **svg-aligner** processes each slide, detecting and fixing pixel-level drift
3. Cleaned SVGs are converted to natively editable PPTX

This pipeline was **stress-tested with 300+ SVG pages** across multiple document types (research papers, product launches, financial reports) and has proven reliable in production use.

### Integration with pptmaster

svg-aligner is integrated into pptmaster's `finalize_svg` post-processing pipeline. See [INTEGRATION.md](./INTEGRATION.md) for the complete integration guide.

## Bug Fixes History

svg-aligner passed **hell-grade stress testing** with the following critical fixes:

| Fix | Issue | Resolution |
|-----|-------|------------|
| **FIX-1** | ET Node wrapper dunder method collisions | Explicit `__slots__` and string-concatenated dunder names |
| **FIX-2** | SVG serialization losing namespace declarations | Regex-based xmlns detection and restoration |
| **FIX-3** | Inverse-CTM using only parent transform | Full CTM = parent × local matrix for correct inverse |
| **FIX-4** | Text-anchor not accounted for in write-back | `adjust_for_text_anchor()` called before delta computation |
| **FIX-5** | XML declaration parsing with malformed input | Regex-based declaration stripping instead of `str.index()` |
| **FIX-6** | RecursionError on deeply nested SVG | `MAX_DOM_DEPTH = 512` guard on DOM traversal |
| **FIX-7** | Namespace prefix auto-generation | Pre-scan and register all xmlns declarations |
| **FIX-8** | Path element coordinate translation | `_translate_path_d()` for direct `d` attribute modification |

## Troubleshooting & Pitfalls

### ⚠️ SVG Layout Design Constraint (for LLM Prompt Writers)

When generating SVG that will be processed by svg-aligner, ensure that
**elements belonging to different columns/rows are spaced at least 20 px apart**
on the primary alignment axis.

If two columns of text have their X coordinates within 5 px of each other
(e.g. `x="48"`, `x="51"`, `x="52"` all at `y="244"`), the aligner will
correctly interpret them as "elements in the same visual row with minor
drift" and snap them all to the same baseline.  This is the algorithm
working **as designed**, not a bug — it simply cannot know your intent to
create separate columns.

**Correct pattern**: space columns far apart:
```xml
<!-- Column 1: x=48 -->
<text x="48" y="244">Column 1</text>
<!-- Column 2: x=340 (292px gap — safely outside 5px window) -->
<text x="340" y="244">Column 2</text>
<!-- Column 3: x=632 (292px gap) -->
<text x="632" y="244">Column 3</text>
```

**Intentional minor offsets** (2–4 px) for the aligner to correct should be
placed **within the same column group**:
```xml
<!-- Within column 2: title/body at x=343/344 — aligner will snap to 343 -->
<text x="343" y="244" font-weight="bold">Title</text>
<text x="344" y="274">Body text</text>
```

### ⚠️ pptmaster Integration: Clean Up Intermediate Files

When integrating svg-aligner into the **pptmaster** `finalize_svg` pipeline,
the downstream `svg_to_pptx` converter generates compatibility backups
(`backup/<timestamp>/`) and intermediate directories (`svg_final/`,
`svg_output/`) by default.

To produce a clean `.pptx`-only output:

```bash
# Use --only native to skip the SVG-reference backup PPTX
# Use -s final to read from svg_final/ (post-processed)
python scripts/svg_to_pptx.py <project_path> --only native -s final
```

Or programmatically, call `cleanup_intermediates()` after export to remove
`svg_output/`, `svg_final/`, `backup/`, and `.cache/` directories.

## License

MIT — see [LICENSE](LICENSE).
