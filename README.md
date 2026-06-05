# svg-aligner

> Deterministic SVG alignment post-processor for LLM-generated content.

When LLMs write complete SVG XML by hand (as in [pptmaster](https://github.com/)), visually grouped elements often end up with pixel-level coordinate drift — a row of boxes that *should* be left-aligned may have `x="120"`, `x="122"`, `x="119"`.  **svg-aligner** detects these near-misses with a deterministic algorithm and snaps them to exact alignment, producing clean, predictable output without requiring a second LLM call.

## Core Algorithm

The aligner works in three stages:

1. **Absolute Coordinate Resolution** — Walks the full SVG DOM tree, resolving every leaf element (rect, text, path, …) into absolute root-space bounding boxes by composing ancestor `transform` matrices.  Text elements get special treatment: `text-anchor="middle"` and `"end"` are factored into the visual edge calculation so that alignment compares *what you see*, not just the anchor point.

2. **Range-Based Detection (5 px Hard Threshold)** — For each alignment dimension (LEFT / RIGHT / TOP / BOTTOM / CENTER_H / CENTER_V / DISTRIBUTE_H / DISTRIBUTE_V), elements whose relevant coordinate falls within a **cluster window** (`threshold × 3`) are grouped.  Within each group, the **range** (max − min) of that coordinate is computed.  If `range < ALIGN_THRESHOLD` (default **5 px**), the group is flagged for correction.  For distribution types, the algorithm checks the range of **edge-to-edge gaps** instead.

3. **Inverse-CTM Coordinate Write-Back** — Corrections are applied by computing the delta in absolute space, transforming it back through the inverse of the element's full coordinate transform matrix (`inv(parent_ctm × local_matrix)`), and adjusting the node's local attributes (`x`, `y`, `cx`, `d`, etc.).  A cross-axis deduplication step ensures each element is touched by at most one horizontal and one vertical correction, preventing cascading conflicts.

## Installation

### From source

```bash
git clone https://github.com/YOUR_USERNAME/svg-aligner.git
cd svg-aligner
pip install -e .
```

### Direct install via pip

```bash
pip install git+https://github.com/YOUR_USERNAME/svg-aligner.git
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
├── README.md
├── LICENSE                      # MIT
├── .gitignore
└── pyproject.toml
```

## License

MIT — see [LICENSE](LICENSE).
