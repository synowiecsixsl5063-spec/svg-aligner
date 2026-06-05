"""test_integration.py - Integration / stress tests for svg_aligner.

Constructs complex multi-page SVG scenarios to verify the aligner
handles deep nesting, mixed text-anchor combinations, and the
threshold-guard (large offsets must be left untouched).
"""

import unittest
from svg_aligner import process_svg, ALIGN_THRESHOLD
from svg_aligner.core import _parse_svg_string


SVG_NS = "http://www.w3.org/2000/svg"


def _find_elem(root, tag, elem_id):
    """Find an element by tag name and id."""
    ns = "{" + SVG_NS + "}"
    for elem in root.iter(ns + tag):
        if elem.get("id") == elem_id:
            return elem
    return None


# =============================================================================
# Integration Test 1: Deeply Nested (3-level <g> transforms)
# =============================================================================

class TestDeepNesting(unittest.TestCase):
    """
    Three layers of nested <g transform="translate(...)">:
      g1: translate(100, 100)
        g2: translate(30, 30)
          g3: translate(20, 20)
            rect_a: x=50, y=50  => absolute x_min = 100+30+20+50 = 200

      rect_b: x=203, y=250  => absolute x_min = 203

    Range = 3 < 5 => LEFT alignment triggered, both snap to x_min=200.
    After correction: rect_a stays at local x=50, rect_b x becomes 200.
    """

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400">\n'
        '  <g transform="translate(100, 100)">\n'
        '    <g transform="translate(30, 30)">\n'
        '      <g transform="translate(20, 20)">\n'
        '        <rect x="50" y="50" width="40" height="30" id="deep_rect_a"/>\n'
        '      </g>\n'
        '    </g>\n'
        '  </g>\n'
        '  <rect x="203" y="250" width="40" height="30" id="sibling_rect_b"/>\n'
        '</svg>'
    )

    def test_deep_nesting_aligns_correctly(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)

        left_actions = [a for a in log if a["alignment_type"] == "LEFT"]
        self.assertGreaterEqual(len(left_actions), 1,
                                "Deep nesting should still detect LEFT alignment")

        action = left_actions[0]
        self.assertEqual(len(action["affected_nodes"]), 2)
        self.assertAlmostEqual(action["baseline_value"], 200.0, places=1,
                               msg="Baseline should be absolute x_min=200")

    def test_deep_rect_local_x_unchanged(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        deep_rect = _find_elem(root, "rect", "deep_rect_a")
        self.assertIsNotNone(deep_rect, "deep_rect_a must exist")
        local_x = float(deep_rect.get("x"))
        self.assertAlmostEqual(local_x, 50.0, places=1,
                               msg="Deep nested rect local x should remain 50")

    def test_sibling_rect_snapped(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        sib_rect = _find_elem(root, "rect", "sibling_rect_b")
        self.assertIsNotNone(sib_rect, "sibling_rect_b must exist")
        new_x = float(sib_rect.get("x"))
        self.assertAlmostEqual(new_x, 200.0, places=1,
                               msg="Sibling rect x should snap to 200")


# =============================================================================
# Integration Test 2: Mixed Text-Anchor (middle + end)
# =============================================================================

class TestMixedTextAnchor(unittest.TestCase):
    """
    Page 2 with text-anchor="middle" text alongside a rect:
      text_mid: x=300, text-anchor="middle", font-size=20 => width=12, visual_left=294
      rect_c:   x=292, visual_left=292

    Range = 2 < 5 => LEFT alignment triggered, both snap to visual_left = 292.
    For text_mid with middle anchor:
      visual_left = x - width/2  =>  x = visual_left + width/2
      Before: x=300, visual_left=294
      After:  x=298, visual_left=292

    This verifies the adjust_for_text_anchor() path correctly converts
    between visual bbox coordinates and text-anchor-aware attribute values.
    """

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="200">\n'
        '  <text x="300" y="50" text-anchor="middle" font-size="20" id="text_mid">A</text>\n'
        '  <rect x="292" y="40" width="50" height="20" id="rect_c"/>\n'
        '</svg>'
    )

    def test_middle_anchor_adjusted(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        text_mid = _find_elem(root, "text", "text_mid")
        self.assertIsNotNone(text_mid, "text_mid must exist")
        new_x = float(text_mid.get("x"))
        # visual_left 294 -> 292, delta=-2 => x = 300 - 2 = 298
        self.assertAlmostEqual(new_x, 298.0, places=1,
                               msg="text_mid x should be 298 after anchor-aware adjustment")

    def test_rect_snapped(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        rect = _find_elem(root, "rect", "rect_c")
        self.assertIsNotNone(rect, "rect_c must exist")
        new_x = float(rect.get("x"))
        self.assertAlmostEqual(new_x, 292.0, places=1,
                               msg="rect_c x should remain 292 (baseline)")

    def test_alignment_detected(self):
        """LEFT alignment should be detected."""
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        left_actions = [a for a in log if a["alignment_type"] == "LEFT"]
        self.assertGreaterEqual(len(left_actions), 1,
                                "Should detect LEFT alignment")


# =============================================================================
# Integration Test 3: Threshold Guard (large offsets must NOT be modified)
# =============================================================================

class TestThresholdGuard(unittest.TestCase):
    """
    Page 3 with deliberately large offsets (range >> 5px).
    The aligner must NOT modify these elements.

    Three rects with x=10, x=50, x=200:
    x_min range: 200-10=190 >> 5 => NO alignment should be detected.
    """

    SVG_INPUT = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
        '  <rect x="10" y="10" width="30" height="20" id="guard_a"/>\n'
        '  <rect x="50" y="80" width="30" height="20" id="guard_b"/>\n'
        '  <rect x="200" y="150" width="30" height="20" id="guard_c"/>\n'
        '</svg>'
    )

    def test_no_alignment_for_large_offsets(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=True)
        self.assertEqual(len(log), 0,
                         "Elements with large offsets should produce NO actions")

    def test_output_svg_unchanged(self):
        """Dry-run must return identical SVG; also verify dry_run=False preserves it."""
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root_in, _ = _parse_svg_string(self.SVG_INPUT)
        root_out, _ = _parse_svg_string(out_svg)

        # Compare each rect's x attribute
        for elem_id in ("guard_a", "guard_b", "guard_c"):
            in_rect = _find_elem(root_in, "rect", elem_id)
            out_rect = _find_elem(root_out, elem_id if False else "rect", elem_id)
            # Actually let me just re-search properly
            for rect in root_out.iter("{" + SVG_NS + "}rect"):
                if rect.get("id") == elem_id:
                    self.assertEqual(float(rect.get("x")), float(in_rect.get("x")),
                                     msg="{} x should be unchanged".format(elem_id))
                    break

    def test_all_rects_preserved(self):
        out_svg, log = process_svg(self.SVG_INPUT, dry_run=False)
        root, _ = _parse_svg_string(out_svg)

        for elem_id in ("guard_a", "guard_b", "guard_c"):
            elem = _find_elem(root, "rect", elem_id)
            self.assertIsNotNone(elem, "{} must exist in output".format(elem_id))
            original_x = {"guard_a": 10.0, "guard_b": 50.0, "guard_c": 200.0}[elem_id]
            self.assertAlmostEqual(float(elem.get("x")), original_x, places=2,
                                   msg="{} should not have been modified".format(elem_id))


# =============================================================================
# Integration Test 4: Multi-Page Batch Processing
# =============================================================================

class TestMultiPageBatch(unittest.TestCase):
    """
    Process 3 independent SVG strings (simulating 3 PPT pages) in a batch
    and verify: pages 1-2 are corrected, page 3 is untouched.
    """

    PAGES = [
        # Page 1: Deep nesting alignment
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400">\n'
            '  <g transform="translate(100, 100)">\n'
            '    <g transform="translate(30, 30)">\n'
            '      <g transform="translate(20, 20)">\n'
            '        <rect x="50" y="50" width="40" height="30" id="deep_rect_a"/>\n'
            '      </g>\n'
            '    </g>\n'
            '  </g>\n'
            '  <rect x="203" y="250" width="40" height="30" id="sibling_rect_b"/>\n'
            '</svg>',
            "should_be_corrected",
        ),
        # Page 2: Mixed text-anchor alignment
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="200">\n'
            '  <text x="300" y="50" text-anchor="middle" font-size="20" id="text_mid">A</text>\n'
            '  <rect x="292" y="40" width="50" height="20" id="rect_c"/>\n'
            '</svg>',
            "should_be_corrected",
        ),
        # Page 3: Large offsets - must NOT be modified
        (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">\n'
            '  <rect x="10" y="10" width="30" height="20" id="guard_a"/>\n'
            '  <rect x="50" y="80" width="30" height="20" id="guard_b"/>\n'
            '  <rect x="200" y="150" width="30" height="20" id="guard_c"/>\n'
            '</svg>',
            "must_be_untouched",
        ),
    ]

    def test_batch_processing(self):
        """Process all pages and verify each page's expected behavior."""
        for i, (svg_string, expectation) in enumerate(self.PAGES):
            out_svg, log = process_svg(svg_string, dry_run=False)

            if expectation == "should_be_corrected":
                self.assertGreater(len(log), 0,
                                   "Page {} should produce alignment actions".format(i + 1))
            elif expectation == "must_be_untouched":
                self.assertEqual(len(log), 0,
                                 "Page {} must produce NO actions (large offsets)".format(i + 1))
                # Verify the SVG is unchanged
                root_in, _ = _parse_svg_string(svg_string)
                root_out, _ = _parse_svg_string(out_svg)
                for tag in ("rect", "text"):
                    for in_elem in root_in.iter("{" + SVG_NS + "}" + tag):
                        elem_id = in_elem.get("id")
                        if not elem_id:
                            continue
                        for out_elem in root_out.iter("{" + SVG_NS + "}" + tag):
                            if out_elem.get("id") == elem_id:
                                for attr in ("x", "y", "width", "height"):
                                    self.assertEqual(
                                        in_elem.get(attr), out_elem.get(attr),
                                        msg="Page {}: {} attr '{}' should be unchanged".format(
                                            i + 1, elem_id, attr))


if __name__ == "__main__":
    unittest.main()
