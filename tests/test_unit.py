"""test_unit.py - Unit tests for svg_aligner.core.

Constructs real SVG strings, runs process_svg, and verifies that the
core alignment algorithm correctly handles nested transforms, text-anchor
perception, and multi-element equal-spacing distribution.
"""

import unittest
from svg_aligner import process_svg, ALIGN_THRESHOLD
from svg_aligner.core import _parse_svg_string


# =============================================================================
# Test Case 1: Nested + Transform Alignment
# =============================================================================

class TestNestedTransformAlignment(unittest.TestCase):
    """
    SVG structure:
      <g transform="translate(50,50)">
        <rect x="70" y="20" width="30" height="20" id="rect_in_group"/>
      </g>
      <rect x="122" y="70" width="30" height="20" id="rect_sibling"/>

    rect_in_group: local x=70 inside translate(50,50) => absolute x_min = 120
    rect_sibling:  absolute x_min = 122
    Range = 2 < 5 => LEFT alignment group, snap both to x_min = 120
    """

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
        '  <g transform="translate(50,50)">\n'
        '    <rect x="70" y="20" width="30" height="20" id="rect_in_group"/>\n'
        '  </g>\n'
        '  <rect x="122" y="70" width="30" height="20" id="rect_sibling"/>\n'
        '</svg>'
    )

    def test_detects_left_alignment(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        self.assertEqual(out_svg, self.SVG_INPUT, "dry_run must not modify SVG")
        self.assertGreaterEqual(len(log), 1, "Should detect at least one alignment action")

        left_actions = [a for a in log if a["alignment_type"] == "LEFT"]
        self.assertEqual(len(left_actions), 1, "Should find exactly one LEFT alignment")

        action = left_actions[0]
        self.assertEqual(len(action["affected_nodes"]), 2)
        self.assertLess(action["range_px"], ALIGN_THRESHOLD)
        self.assertAlmostEqual(action["baseline_value"], 120.0, places=1)

    def test_corrects_sibling_x(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        sibling_rect = root.find(
            ".//{http://www.w3.org/2000/svg}rect[@id='rect_sibling']"
        )
        self.assertIsNotNone(sibling_rect, "rect_sibling must exist in output")
        new_x = float(sibling_rect.get("x"))
        self.assertAlmostEqual(new_x, 120.0, msg="rect_sibling x should be snapped to 120", places=1)

    def test_preserves_nested_rect_local_x(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        group = root.find(".//{http://www.w3.org/2000/svg}g")
        self.assertIsNotNone(group)
        nested_rect = group.find(
            ".//{http://www.w3.org/2000/svg}rect[@id='rect_in_group']"
        )
        self.assertIsNotNone(nested_rect, "rect_in_group must exist in output")
        local_x = float(nested_rect.get("x"))
        self.assertAlmostEqual(local_x, 70.0, msg="rect_in_group local x should remain 70", places=1)


# =============================================================================
# Test Case 2: Text-Anchor Awareness
# =============================================================================

class TestTextAnchorAwareness(unittest.TestCase):
    """
    <text x="200" y="30" text-anchor="middle" font-size="20">A</text>
    <rect x="192" y="20" width="40" height="20" id="rect_near_text"/>

    Text 'A' width = 0.6 * 20 = 12, visual left = 200 - 6 = 194
    Rect left = 192, range = 2 < 5 => LEFT alignment triggered.
    Both snap to visual left = 192 => text x becomes 198.
    """

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
        '  <text x="200" y="30" text-anchor="middle" font-size="20" id="text_mid">A</text>\n'
        '  <rect x="192" y="20" width="40" height="20" id="rect_near_text"/>\n'
        '</svg>'
    )

    def test_detects_alignment_with_text_anchor(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        left_actions = [a for a in log if a["alignment_type"] == "LEFT"]
        self.assertGreaterEqual(len(left_actions), 1,
                                "Should detect LEFT alignment between text and rect")

    def test_text_x_adjusted_for_anchor(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        text_elem = root.find(
            ".//{http://www.w3.org/2000/svg}text[@id='text_mid']"
        )
        self.assertIsNotNone(text_elem, "text element must exist")
        new_x = float(text_elem.get("x"))
        self.assertAlmostEqual(new_x, 198.0, msg="text x should be adjusted by -2", places=1)

    def test_rect_x_snapped(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        rect_elem = root.find(
            ".//{http://www.w3.org/2000/svg}rect[@id='rect_near_text']"
        )
        self.assertIsNotNone(rect_elem, "rect must exist")
        new_x = float(rect_elem.get("x"))
        self.assertAlmostEqual(new_x, 192.0, msg="rect x should be snapped to 192", places=1)


# =============================================================================
# Test Case 3: Multi-Element Equal-Spacing Distribution
# =============================================================================

class TestMultiElementDistribution(unittest.TestCase):
    """
    4 narrow rects (w=1), tightly packed near x=50:
      elem_0: x=48, elem_1: x=51, elem_2: x=55, elem_3: x=57
    center_x range: 9 < 15 => DISTRIBUTE_H cluster ✓
    Gaps: 2, 3, 1 => range=2 < 5 => distribution ✓
    target_gap = 2.0 => Expected: 48, 51.0, 54.0, 57.0
    """

    SVG_NS = "http://www.w3.org/2000/svg"

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="30">\n'
        '  <rect x="48" y="10" width="1" height="10" id="elem_0"/>\n'
        '  <rect x="51" y="10" width="1" height="10" id="elem_1"/>\n'
        '  <rect x="55" y="10" width="1" height="10" id="elem_2"/>\n'
        '  <rect x="57" y="10" width="1" height="10" id="elem_3"/>\n'
        '</svg>'
    )

    def _find_rect(self, root, elem_id):
        ns = "{" + self.SVG_NS + "}"
        for rect in root.iter(ns + "rect"):
            if rect.get("id") == elem_id:
                return rect
        return None

    def test_detects_distribution(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        dist_actions = [a for a in log if a["alignment_type"] == "DISTRIBUTE_H"]
        self.assertEqual(len(dist_actions), 1,
                         "Should detect exactly one DISTRIBUTE_H action")
        self.assertEqual(len(dist_actions[0]["affected_nodes"]), 4,
                         "All 4 elements should be in the distribution group")

    def test_distributes_to_equal_spacing(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        expected_x = [48.0, 51.0, 54.0, 57.0]
        for i, exp in enumerate(expected_x):
            elem = self._find_rect(root, "elem_{}".format(i))
            self.assertIsNotNone(elem, "elem_{} must exist".format(i))
            new_x = float(elem.get("x"))
            self.assertAlmostEqual(new_x, exp,
                                   msg="elem_{} x should be ~{}, got {}".format(i, exp, new_x),
                                   places=1)

    def test_action_log_records_distribution(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        dist_action = [a for a in log if a["alignment_type"] == "DISTRIBUTE_H"][0]
        self.assertAlmostEqual(dist_action["baseline_value"], 2.0,
                               msg="Baseline (target gap) should be 2.0", places=1)


# =============================================================================
# Test Case 4: Edge case -- no alignment needed
# =============================================================================

class TestNoAlignment(unittest.TestCase):
    """Elements that are clearly NOT aligned should not be modified."""

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
        '  <rect x="10" y="10" width="30" height="20" id="far_1"/>\n'
        '  <rect x="200" y="200" width="30" height="20" id="far_2"/>\n'
        '</svg>'
    )

    def test_no_false_positives(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        self.assertEqual(len(log), 0,
                         "Elements far apart should not trigger alignment")


# =============================================================================
# Test Case 5: Dry-run mode must not modify SVG
# =============================================================================

class TestDryRun(unittest.TestCase):
    """Dry-run mode should return identical SVG and produce a log."""

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">\n'
        '  <rect x="10" y="10" width="10" height="10" id="a"/>\n'
        '  <rect x="12" y="10" width="10" height="10" id="b"/>\n'
        '  <rect x="14" y="10" width="10" height="10" id="c"/>\n'
        '</svg>'
    )

    def test_dry_run_returns_unchanged_svg(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        self.assertEqual(out_svg, self.SVG_INPUT,
                         "dry_run=True must return the input SVG unchanged")
        self.assertGreater(len(log), 0, "dry_run should still produce a log")


if __name__ == "__main__":
    unittest.main()
