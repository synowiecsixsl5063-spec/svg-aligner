"""
sample_usage.py - Example usage of svg_aligner as a Python module and CLI.

Demonstrates both programmatic API and command-line usage for correcting
LLM-generated SVG alignment issues.
"""

from svg_aligner import process_svg, ALIGN_THRESHOLD

# =============================================================================
# Example 1: Programmatic API -- basic usage
# =============================================================================

svg_input = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
    '  <g transform="translate(50, 50)">\n'
    '    <rect x="70" y="20" width="30" height="20" id="rect_a"/>\n'
    '  </g>\n'
    '  <rect x="122" y="70" width="30" height="20" id="rect_b"/>\n'
    '</svg>'
)

# Dry-run: inspect what would change without modifying anything
out_svg, log = process_svg(svg_input, dry_run=True)

print("=== Dry-run Log ===")
for action in log:
    print(f"  Type : {action['alignment_type']}")
    print(f"  Nodes: {action['affected_nodes']}")
    print(f"  Before: {action['before_values']}")
    print(f"  After : {action['after_values']}")
    print(f"  Range : {action['range_px']:.1f} px")
    print()

# Apply corrections
corrected_svg, _ = process_svg(svg_input, dry_run=False)

print("=== Corrected SVG (rect elements) ===")
for line in corrected_svg.split("\n"):
    if "<rect" in line:
        print(f"  {line.strip()}")
print()


# =============================================================================
# Example 2: Custom threshold
# =============================================================================

print("=== Custom Threshold (threshold=3) ===")
out_svg, log = process_svg(svg_input, dry_run=True, threshold=3.0)
if log:
    for action in log:
        print(f"  {action['alignment_type']}: {len(action['affected_nodes'])} nodes, "
              f"range={action['range_px']:.1f}px")
else:
    print("  No alignments found at threshold=3 (range 2 < 3, but threshold=3 means "
          "cluster_window=9, still clusters)")


# =============================================================================
# Example 3: CLI usage
# =============================================================================

CLI_HELP = """
=== CLI Usage ===

# Basic correction (overwrites input file in-place):
  python -m svg_aligner.core input.svg -o output.svg

# Dry-run mode (prints JSON log to stdout):
  python -m svg_aligner.core input.svg --dry-run

# Custom threshold (3px instead of default 5px):
  python -m svg_aligner.core input.svg --dry-run --threshold 3

# As a Python module:
  from svg_aligner import process_svg
  corrected_svg, log = process_svg(svg_string, dry_run=False)
"""
print(CLI_HELP)
