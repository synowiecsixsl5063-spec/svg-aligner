"""
svg_aligner - Deterministic SVG alignment post-processor.

Detects near-aligned element groups in LLM-generated SVG and snaps them
to exact alignment using a 5px hard-threshold algorithm.

Public API
----------
process_svg(svg_string, threshold=5.0, dry_run=False)
    Pure entry point: takes an SVG string, returns (corrected_svg_string, action_log).

align_svg_dom(svg_dom, dry_run=False, threshold=5.0)
    Convenience wrapper for a pre-parsed SVG DOM tree.

detect_and_fix_alignments(records, threshold=5.0)
    Pure planning function: returns correction actions without mutating DOM.
"""

from svg_aligner.core import (
    ALIGN_THRESHOLD,
    AlignmentAction,
    AlignmentType,
    AlignerResult,
    BBox,
    ElementRecord,
    align_svg_dom,
    detect_and_fix_alignments,
    process_svg,
)

__all__ = [
    "ALIGN_THRESHOLD",
    "AlignmentAction",
    "AlignmentType",
    "AlignerResult",
    "BBox",
    "ElementRecord",
    "align_svg_dom",
    "detect_and_fix_alignments",
    "process_svg",
]

__version__ = "0.1.0"
