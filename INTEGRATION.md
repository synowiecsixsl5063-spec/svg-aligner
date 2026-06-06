# svg-aligner Integration with pptmaster

> How svg-aligner fits into the pptmaster SVG post-processing pipeline, and how to use it in your own AI presentation generation workflow.

## Overview

svg-aligner is integrated into pptmaster's **`finalize_svg`** post-processing step. After the Executor role generates SVG slides, svg-aligner processes each slide to correct pixel-level coordinate drift before the SVGs are converted to PPTX.

## Pipeline Position

```
pptmaster Pipeline:
                                                           svg-aligner
                                                               │
Source → Strategist → Image_Generator → Executor → finalize_svg ─→ svg_to_pptx → .pptx
                                                               │
                                               (coordinate correction gate)
```

svg-aligner runs as a **sub-step inside `finalize_svg`**, processing each SVG page individually before the final export. It acts as a deterministic quality gate — no API calls, no hallucination risk.

## Integration Architecture

### Step 1: SVG Generation (Executor)
The Executor role generates individual SVG files in `projects/<name>/svg_output/`. Each file contains a complete slide layout:

```
projects/<name>/svg_output/
├── slide_01.svg    # Title slide
├── slide_02.svg    # Content slide
├── slide_03.svg    # Content slide
└── ...
```

### Step 2: SVG Post-Processing (finalize_svg + svg-aligner)
`finalize_svg` orchestrates the post-processing pipeline:

1. **SVG Cleanup**: Standardizes viewBox, font families, and color spaces
2. **svg-aligner**: Processes each SVG through the alignment algorithm
3. **Quality Check**: Validates the corrected output
4. **Output**: Writes cleaned files to `projects/<name>/svg_final/`

```python
# Internal: how finalize_svg calls svg-aligner
from svg_aligner import process_svg

def process_slide(svg_path: str, threshold: float = 5.0):
    with open(svg_path, 'r', encoding='utf-8') as f:
        svg_string = f.read()

    corrected_svg, action_log = process_svg(svg_string, threshold=threshold)

    # Log corrections for debugging
    for action in action_log:
        logger.info(
            f"[svg-aligner] {action['alignment_type']}: "
            f"{len(action['affected_nodes'])} nodes, "
            f"range={action['range_px']:.1f}px → baseline={action['baseline_value']:.1f}"
        )

    return corrected_svg, action_log
```

### Step 3: PPTX Export (svg_to_pptx)
The corrected SVGs from `svg_final/` are converted to native PowerPoint shapes:

```bash
# Standard export
python scripts/svg_to_pptx.py projects/<name>

# Clean export (no intermediate files)
python scripts/svg_to_pptx.py projects/<name> --only native -s final
```

## Integration Code Example

Here's a minimal example showing how svg-aligner integrates into any SVG→PPTX pipeline:

```python
"""
Minimal example: integrating svg-aligner into a slide generation pipeline.
"""
from pathlib import Path
from svg_aligner import process_svg

def finalize_slides(project_path: str, threshold: float = 5.0):
    """
    Post-process all SVG slides in a project directory.

    Args:
        project_path: Path to the pptmaster project directory
        threshold: Alignment threshold in pixels (default 5.0)
    """
    svg_output = Path(project_path) / "svg_output"
    svg_final = Path(project_path) / "svg_final"
    svg_final.mkdir(parents=True, exist_ok=True)

    total_corrections = 0

    for svg_file in sorted(svg_output.glob("*.svg")):
        with open(svg_file, 'r', encoding='utf-8') as f:
            svg_string = f.read()

        # svg-aligner: detect and fix coordinate drift
        corrected_svg, action_log = process_svg(
            svg_string,
            threshold=threshold,
            dry_run=False,
        )

        # Write corrected SVG
        output_path = svg_final / svg_file.name
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(corrected_svg)

        # Track corrections
        slide_corrections = sum(
            len(a["affected_nodes"]) for a in action_log
        )
        total_corrections += slide_corrections

        if slide_corrections > 0:
            print(f"  {svg_file.name}: {slide_corrections} nodes corrected")
            for action in action_log:
                print(f"    - {action['alignment_type']}: "
                      f"range={action['range_px']:.1f}px")

    print(f"\nTotal: {total_corrections} nodes corrected across "
          f"{len(list(svg_final.glob('*.svg')))} slides")

    return total_corrections

# Usage
if __name__ == "__main__":
    finalize_slides("projects/my_presentation")
```

## Before/After Example

### Before svg-aligner (raw LLM output)
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540">
  <g transform="translate(80, 100)">
    <rect x="0" y="0" width="200" height="50"/>
    <!-- rect absolute x_min = 80 -->
  </g>
  <rect x="83" y="100" width="200" height="50"/>
  <!-- sibling x_min = 83, range = 3px < 5px threshold -->
  <!-- This will be detected as LEFT alignment drift! -->
</svg>
```

### After svg-aligner (corrected)
```xml
<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540">
  <g transform="translate(80, 100)">
    <rect x="0" y="0" width="200" height="50"/>
    <!-- rect absolute x_min = 80 (unchanged, local x stays 0) -->
  </g>
  <rect x="80" y="100" width="200" height="50"/>
  <!-- sibling x snapped from 83 → 80 (corrected via inverse CTM) -->
</svg>
```

## Performance

| Metric | Value |
|--------|-------|
| Processing speed | ~500 slides/second (single core) |
| Memory per slide | < 5 MB |
| Dependencies | **Zero** (stdlib only) |
| API calls | **Zero** (deterministic) |
| Failure mode | Returns original SVG unchanged |
| Batch processing | Supports multi-page in single call |

## Configuration

### Threshold Tuning

The 5px default works for most cases. Adjust based on your SVG generator:

```python
# Stricter: only fix very close elements (for precise generators like Claude)
process_svg(svg_string, threshold=3.0)

# Looser: fix more aggressively (for less precise generators)
process_svg(svg_string, threshold=8.0)
```

### Dry-Run Mode

Preview corrections without modifying files:

```python
corrected_svg, action_log = process_svg(svg_string, dry_run=True)
for action in action_log:
    print(f"Would fix {action['alignment_type']}: "
          f"{len(action['affected_nodes'])} nodes")
# corrected_svg == svg_string (guaranteed unchanged)
```

## pptmaster Project Structure

When svg-aligner is used within pptmaster:

```
ppt-master/
├── skills/ppt-master/
│   └── scripts/
│       ├── finalize_svg.py        # Orchestrates svg-aligner calls
│       └── svg_to_pptx.py         # SVG → PPTX conversion
├── projects/
│   └── <project_name>/
│       ├── svg_output/            # Raw SVGs from Executor
│       ├── svg_final/             # Post svg-aligner output
│       └── output/                # Final .pptx files
└── README.md
```

## Troubleshooting Integration

### Issue: Cross-column elements being merged

**Symptom**: Elements from different columns get aligned to the same X position.

**Cause**: Columns are too close together (< 20px apart) on the alignment axis.

**Solution**: Ensure column spacing ≥ 20px in your SVG generator prompts.

### Issue: No corrections detected

**Symptom**: Action log is empty but elements look misaligned.

**Causes**:
1. Offsets exceed the 5px threshold — increase threshold or fix generator
2. Elements have no overlapping perpendicular axis — check Y positions for horizontal alignment
3. Singular transform matrices — algorithm skips un-transformable elements

### Issue: Corrections make layout worse

**Symptom**: After correction, some elements move to wrong positions.

**Causes**:
1. Elements that look like they should align are actually in different visual groups
2. Threshold is too loose for this particular layout

**Solution**: Run with `--dry-run` first to audit corrections before applying.

## Related Documentation

- [svg-aligner README](./README.md) — Full API reference and CLI usage
- [svg-aligner README (Chinese)](./README_CN.md) — 中文文档
- [pptmaster README](https://github.com/hugohe3/ppt-master) — AI presentation generation system
- [pptmaster SKILL.md](https://github.com/hugohe3/ppt-master/blob/master/skills/ppt-master/SKILL.md) — Full workflow documentation
