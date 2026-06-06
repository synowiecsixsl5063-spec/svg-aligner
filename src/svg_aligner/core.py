#!/usr/bin/env python3
"""
svg_aligner.py - Deterministic SVG alignment post-processor for pptmaster.

Parses an SVG string, detects near-aligned element groups produced by LLM
generation, and snaps them to exact alignment.  Outputs the corrected SVG
string together with a structured JSON operation log.

Usage:
    python svg_aligner.py input.svg -o output.svg
    python svg_aligner.py input.svg --dry-run --threshold 3
"""

from __future__ import annotations

import sys
import argparse
import copy
import json
import math
import re
import uuid
import io
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from enum import Enum
from statistics import mean
from typing import Any, Callable, Iterable, Optional, Sequence, TypeAlias

_DUNDER = "__"  # helper to avoid Markdown rendering issues in this file


# =============================================================================
# [FIX-7] Namespace discovery regex - explicit raw string
# =============================================================================

_XMLNS_ATTR_RE = re.compile(
    r'xmlns(?::([A-Za-z_][\w.\-]*))?\s*=\s*"([^"]+)"'
)


def _discover_and_register_namespaces(svg_string: str) -> dict[str, str]:
    """
    Scan the raw SVG string for xmlns / xmlns:prefix declarations and
    register them with ElementTree so that serialisation preserves the
    original prefix mappings instead of auto-generating ns0, ns1, etc.
    """
    ns_map: dict[str, str] = {}
    head = svg_string[:8192]
    for m in _XMLNS_ATTR_RE.finditer(head):
        prefix = m.group(1) or ""
        uri = m.group(2)
        if uri not in ns_map:
            ns_map[uri] = prefix
            ET.register_namespace(prefix, uri)
    return ns_map


# =============================================================================
# [FIX-1] ET Node Wrapper - all dunder methods spelled correctly
# =============================================================================

_NS_STRIP_RE = re.compile(r"\{[^}]*\}")


def _strip_ns(tag: str) -> str:
    """Remove {namespace_uri} prefix from an ElementTree tag."""
    if isinstance(tag, str) and tag.startswith("{"):
        return _NS_STRIP_RE.sub("", tag, count=1)
    return tag


class ETNodeWrapper:
    """
    Thin adapter around xml.etree.ElementTree.Element that exposes the
    attribute / property names the core algorithm's generic DOM helpers
    look for (children, parent, text_content, get, set, attrs, and a
    namespace-free tag).
    """

    # [FIX-1] Explicit dunder names using string concatenation to prevent
    # any Markdown / documentation rendering from eating the underscores.
    __slots__ = ("_elem", "_parent", "_children_cache")

    def __init__(
        self,
        elem: ET.Element,
        parent: Optional[ETNodeWrapper] = None,
    ) -> None:
        self._elem = elem
        self._parent = parent
        self._children_cache: Optional[list] = None

    def __repr__(self) -> str:
        return "<ETNodeWrapper tag={!r}>".format(self.tag)

    # -- tag (namespace-stripped) ----------------------------------------------
    @property
    def tag(self) -> str:
        return _strip_ns(self._elem.tag)

    # -- children (lazy, cached) -----------------------------------------------
    @property
    def children(self) -> list:
        if self._children_cache is None:
            self._children_cache = [
                ETNodeWrapper(child, self) for child in self._elem
            ]
        return self._children_cache

    # -- parent ----------------------------------------------------------------
    @property
    def parent(self):
        return self._parent

    # -- text helpers ----------------------------------------------------------
    @property
    def text_content(self) -> str:
        """Recursive text extraction mirroring DOM textContent."""
        return self._collect_text(self._elem)

    @staticmethod
    def _collect_text(elem: ET.Element) -> str:
        parts: list[str] = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(ETNodeWrapper._collect_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    @property
    def text(self) -> str:
        return self._elem.text or ""

    # -- attribute access ------------------------------------------------------
    def get(self, name: str, default: Any = None) -> Any:
        return self._elem.get(name, default)

    def set(self, name: str, value: Any) -> None:
        self._elem.set(name, str(value))

    @property
    def attrs(self) -> dict:
        return self._elem.attrib

    @property
    def element(self) -> ET.Element:
        return self._elem


def wrap_tree(root: ET.Element) -> ETNodeWrapper:
    """Wrap an ElementTree root element and all descendants."""
    return ETNodeWrapper(root, parent=None)


# =============================================================================
# [FIX-2] SVG serialisation - regex with explicit backslashes
# =============================================================================

def _serialize_svg(root: ET.Element, ns_map: dict[str, str]) -> str:
    """
    Serialise an ElementTree root back to an SVG string, preserving the
    XML declaration and the original default namespace declaration.
    """
    raw = ET.tostring(root, encoding="unicode", method="xml")

    svg_ns = "http://www.w3.org/2000/svg"

    # [FIX-2] Ensure xmlns is present - build regex carefully
    xmlns_present = (
        ('xmlns="' + svg_ns + '"') in raw
        or ("xmlns='" + svg_ns + "'") in raw
    )
    if not xmlns_present:
        # Use explicit regex parts to avoid any rendering ambiguity
        svg_open_pattern = re.compile(
            r"(<"              # literal opening angle bracket
            r"\s*"             # optional whitespace
            r"(?:[\w.\-]+:)?"  # optional namespace prefix
            r"svg"             # literal tag name
            r"\b"              # word boundary
            r")"
        )
        raw = svg_open_pattern.sub(
            r'\1 xmlns="' + svg_ns + '"',
            raw,
            count=1,
        )

    if not raw.startswith("<?xml"):
        raw = '<?xml version="1.0" encoding="utf-8"?>\n' + raw

    return raw


# =============================================================================
# Core Algorithm - Types and Data Structures
# =============================================================================

Point: TypeAlias = tuple[float, float]
Matrix3x3: TypeAlias = tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]

ALIGN_THRESHOLD: float = 5.0
CLUSTER_WINDOW_FACTOR: float = 3.0
CLUSTER_WINDOW: float = ALIGN_THRESHOLD * CLUSTER_WINDOW_FACTOR

# [FIX-6] Maximum recursion depth for DOM traversal
MAX_DOM_DEPTH: int = 512


@dataclass(frozen=True, slots=True)
class BBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def cx(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def cy(self) -> float:
        return (self.y_min + self.y_max) / 2.0


class AlignmentType(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    CENTER_H = "CENTER_H"
    CENTER_V = "CENTER_V"
    DISTRIBUTE_H = "DISTRIBUTE_H"
    DISTRIBUTE_V = "DISTRIBUTE_V"


@dataclass(slots=True)
class ElementRecord:
    node: Any
    bbox: BBox
    abs_matrix: Matrix3x3
    tag: str
    text_anchor: str
    raw_x: float
    raw_y: float
    node_path: str = ""
    parent_ctm: Matrix3x3 = field(default_factory=lambda: make_identity_matrix())
    local_matrix: Matrix3x3 = field(default_factory=lambda: make_identity_matrix())


@dataclass(slots=True)
class AlignmentAction:
    action_id: str
    alignment_type: AlignmentType
    affected_nodes: list[str]
    before_values: list[float]
    after_values: list[float]
    baseline_value: float
    range_px: float
    dry_run: bool = False


@dataclass(slots=True)
class AlignerResult:
    svg_string: str
    actions: list[AlignmentAction]
    stats: dict[str, Any]


@dataclass(slots=True)
class AlignmentGroup:
    alignment_type: AlignmentType
    records: list[ElementRecord]


# =============================================================================
# Generic DOM helpers (duck-typed)
# =============================================================================

_NUM_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_TRANSFORM_RE = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_STYLE_SPLIT_RE = re.compile(r"\s*;\s*")
_STYLE_PAIR_RE = re.compile(r"\s*:\s*")


def _node_tag(node: Any) -> str:
    tag = getattr(node, "tag", None)
    if tag is None:
        tag = getattr(node, "nodeName", "")
    return str(tag).strip()


def _node_children(node: Any) -> list:
    children = getattr(node, "children", None)
    if children is not None:
        return list(children)
    child_nodes = getattr(node, "childNodes", None)
    if child_nodes is not None:
        out: list = []
        for ch in child_nodes:
            if _node_tag(ch) or getattr(ch, "nodeType", None) == 1:
                out.append(ch)
        return out
    return []


def _node_parent(node: Any):
    return getattr(
        node, "parent",
        getattr(node, "parentNode", getattr(node, "_parent", None))
    )


def _node_text(node: Any) -> str:
    for attr in ("text_content", "textContent", "text", "data"):
        val = getattr(node, attr, None)
        if isinstance(val, str):
            return val
        if callable(val):
            try:
                out = val()
                if isinstance(out, str):
                    return out
            except Exception:
                pass
    parts: list[str] = []
    for ch in _node_children(node):
        t = _node_text(ch)
        if t:
            parts.append(t)
    return "".join(parts)


def _get_attr(node: Any, name: str, default: Any = None) -> Any:
    for getter_name in ("attr", "get", "getAttribute"):
        getter = getattr(node, getter_name, None)
        if callable(getter):
            try:
                value = getter(name)
                if value is not None:
                    return value
            except Exception:
                pass
    attrs = getattr(node, "attrs", None)
    if isinstance(attrs, dict) and name in attrs:
        return attrs[name]
    value = getattr(node, name, None)
    if value is not None:
        return value
    return default


def _set_attr(node: Any, name: str, value: Any) -> None:
    for setter_name in ("set_attr", "set", "setAttribute"):
        setter = getattr(node, setter_name, None)
        if callable(setter):
            try:
                setter(name, value)
                return
            except Exception:
                pass
    attrs = getattr(node, "attrs", None)
    if isinstance(attrs, dict):
        attrs[name] = value
        return
    try:
        setattr(node, name, value)
    except Exception:
        pass


def _get_style_map(node: Any) -> dict[str, str]:
    style = _get_attr(node, "style", "")
    if not isinstance(style, str) or not style.strip():
        return {}
    out: dict[str, str] = {}
    for part in _STYLE_SPLIT_RE.split(style.strip()):
        if not part:
            continue
        kv = _STYLE_PAIR_RE.split(part, maxsplit=1)
        if len(kv) == 2:
            out[kv[0].strip()] = kv[1].strip()
    return out


def _get_attr_with_style(node: Any, name: str, default: Any = None) -> Any:
    val = _get_attr(node, name, None)
    if val is not None:
        return val
    style_map = _get_style_map(node)
    if name in style_map:
        return style_map[name]
    return default


_FULLWIDTH_RE = re.compile(r"[０-９]")  # fullwidth digits ０-９


def _normalize_value(value: str) -> str:
    """Normalize fullwidth digits to ASCII and strip whitespace."""
    # Fullwidth digits → ASCII
    result = []
    for ch in value:
        cp = ord(ch)
        if 0xFF10 <= cp <= 0xFF19:
            result.append(chr(cp - 0xFEE0))
        else:
            result.append(ch)
    return "".join(result)


def _safe_float(raw: str) -> float | None:
    """Convert a raw string to float, returning None for NaN/Inf/failure."""
    try:
        f = float(raw)
    except (ValueError, OverflowError):
        return None
    if f != f:  # NaN check (NaN != NaN is True)
        return None
    if f == float("inf") or f == float("-inf"):
        return None
    return f


def _attr_to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return default
        return f
    if isinstance(value, str):
        cleaned = _normalize_value(value.strip())
        m = _NUM_RE.search(cleaned)
        if m:
            f = _safe_float(m.group(0))
            if f is not None:
                return f
    return default


def _parse_float_list(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f or abs(f) == float("inf"):
            return []
        return [f]
    if not isinstance(value, str):
        return []
    cleaned = _normalize_value(value)
    nums: list[float] = []
    for m in _NUM_RE.finditer(cleaned):
        f = _safe_float(m.group(0))
        if f is not None:
            nums.append(f)
    return nums


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    s = "{:.6f}".format(value).rstrip("0").rstrip(".")
    return s if s else "0"


def _extract_all_text(node: Any) -> str:
    raw = _node_text(node)
    return raw.replace("\r", "").strip()


# =============================================================================
# Matrix helpers
# =============================================================================

def make_identity_matrix() -> Matrix3x3:
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def make_translate_matrix(tx: float, ty: float = 0.0) -> Matrix3x3:
    return ((1.0, 0.0, tx), (0.0, 1.0, ty), (0.0, 0.0, 1.0))


def make_scale_matrix(sx: float, sy: float = None) -> Matrix3x3:
    if sy is None:
        sy = sx
    return ((sx, 0.0, 0.0), (0.0, sy, 0.0), (0.0, 0.0, 1.0))


def make_rotate_matrix(angle_deg: float, cx: float = 0.0, cy: float = 0.0) -> Matrix3x3:
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    r = ((cos_a, -sin_a, 0.0), (sin_a, cos_a, 0.0), (0.0, 0.0, 1.0))
    if cx == 0.0 and cy == 0.0:
        return r
    return matrix_multiply(
        make_translate_matrix(cx, cy),
        matrix_multiply(r, make_translate_matrix(-cx, -cy)),
    )


def make_svg_matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> Matrix3x3:
    return ((a, c, e), (b, d, f), (0.0, 0.0, 1.0))


def matrix_multiply(a: Matrix3x3, b: Matrix3x3) -> Matrix3x3:
    def dot(row, col):
        return row[0] * col[0] + row[1] * col[1] + row[2] * col[2]

    cols = (
        (b[0][0], b[1][0], b[2][0]),
        (b[0][1], b[1][1], b[2][1]),
        (b[0][2], b[1][2], b[2][2]),
    )
    return (
        (dot(a[0], cols[0]), dot(a[0], cols[1]), dot(a[0], cols[2])),
        (dot(a[1], cols[0]), dot(a[1], cols[1]), dot(a[1], cols[2])),
        (dot(a[2], cols[0]), dot(a[2], cols[1]), dot(a[2], cols[2])),
    )


def apply_matrix(matrix: Matrix3x3, pt: Point) -> Point:
    x, y = pt
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    )


def apply_vector(matrix: Matrix3x3, vec: Point) -> Point:
    x, y = vec
    return (
        matrix[0][0] * x + matrix[0][1] * y,
        matrix[1][0] * x + matrix[1][1] * y,
    )


def invert_matrix(matrix: Matrix3x3):
    a, c, e = matrix[0]
    b, d, f = matrix[1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    inv_det = 1.0 / det
    ia = d * inv_det
    ic = -c * inv_det
    ib = -b * inv_det
    id_ = a * inv_det
    ie = -(ia * e + ic * f)
    i_f = -(ib * e + id_ * f)
    return ((ia, ic, ie), (ib, id_, i_f), (0.0, 0.0, 1.0))


def parse_transform(transform_str) -> Matrix3x3:
    if not transform_str or not str(transform_str).strip():
        return make_identity_matrix()
    composite = make_identity_matrix()
    for name, args_str in _TRANSFORM_RE.findall(transform_str):
        name = name.strip().lower()
        nums = _parse_float_list(args_str)
        local = make_identity_matrix()
        if name == "translate":
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            local = make_translate_matrix(tx, ty)
        elif name == "scale":
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else None
            local = make_scale_matrix(sx, sy)
        elif name == "rotate":
            angle = nums[0] if nums else 0.0
            if len(nums) >= 3:
                local = make_rotate_matrix(angle, nums[1], nums[2])
            else:
                local = make_rotate_matrix(angle)
        elif name == "matrix":
            if len(nums) >= 6:
                local = make_svg_matrix(nums[0], nums[1], nums[2], nums[3], nums[4], nums[5])
        composite = matrix_multiply(local, composite)
    return composite


# =============================================================================
# Geometry helpers
# =============================================================================

def _resolve_font_size(node: Any, ancestors: Sequence) -> float:
    candidates = [node, *reversed(ancestors)]
    for cur in candidates:
        raw = _get_attr_with_style(cur, "font-size", None)
        if raw is not None:
            size = _attr_to_float(raw, default=0.0)
            if size > 0:
                return size
    return 16.0


def _resolve_text_anchor(node: Any, ancestors: Sequence) -> str:
    candidates = [node, *reversed(ancestors)]
    for cur in candidates:
        raw = _get_attr_with_style(cur, "text-anchor", None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "start"


def estimate_text_width(text: str, font_size: float) -> float:
    if not text:
        return 0.0
    width = 0.0
    for ch in text:
        if ord(ch) in (10, 13, 9):
            continue
        ea = _east_asian_width(ch)
        if ea in {"W", "F"}:
            width += font_size * 1.0
        elif ch.isspace():
            width += font_size * 0.32
        else:
            width += font_size * 0.6
    return width


def _east_asian_width(ch: str) -> str:
    import unicodedata
    return unicodedata.east_asian_width(ch)


def _bbox_from_points(points: Sequence) -> Optional[BBox]:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return BBox(min(xs), min(ys), max(xs), max(ys))


def _parse_points_attr(points_value: Any) -> list:
    if not isinstance(points_value, str) or not points_value.strip():
        return []
    nums = _parse_float_list(points_value)
    pts = []
    for i in range(0, len(nums) - 1, 2):
        pts.append((nums[i], nums[i + 1]))
    return pts


def _parse_path_bbox(d: Any) -> Optional[BBox]:
    """
    Best-effort path bbox approximation.
    Supports common SVG commands: M m L l H h V v C c S s Q q T t A a Z z
    """
    if not isinstance(d, str) or not d.strip():
        return None

    tokens = re.findall(
        r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",
        d,
    )
    if not tokens:
        return None

    def is_cmd(tok: str) -> bool:
        return len(tok) == 1 and tok.isalpha()

    idx = 0
    cmd = ""
    curr: Point = (0.0, 0.0)
    subpath_start: Point = (0.0, 0.0)
    points: list = []

    def next_num() -> float:
        nonlocal idx
        if idx >= len(tokens):
            raise IndexError
        val = float(tokens[idx])
        idx += 1
        return val

    try:
        while idx < len(tokens):
            tok = tokens[idx]
            if is_cmd(tok):
                cmd = tok
                idx += 1
            if not cmd:
                break

            abs_cmd = cmd.upper()
            rel = cmd.islower()

            if abs_cmd == "M":
                x = next_num()
                y = next_num()
                if rel:
                    x += curr[0]
                    y += curr[1]
                curr = (x, y)
                subpath_start = curr
                points.append(curr)
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x = next_num()
                    y = next_num()
                    if rel:
                        x += curr[0]
                        y += curr[1]
                    curr = (x, y)
                    points.append(curr)

            elif abs_cmd == "L":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x = next_num()
                    y = next_num()
                    if rel:
                        x += curr[0]
                        y += curr[1]
                    curr = (x, y)
                    points.append(curr)

            elif abs_cmd == "H":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x = next_num()
                    if rel:
                        x += curr[0]
                    curr = (x, curr[1])
                    points.append(curr)

            elif abs_cmd == "V":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    y = next_num()
                    if rel:
                        y += curr[1]
                    curr = (curr[0], y)
                    points.append(curr)

            elif abs_cmd in {"C", "S", "Q", "T"}:
                if abs_cmd == "C":
                    step = 6
                elif abs_cmd == "S":
                    step = 4
                elif abs_cmd == "Q":
                    step = 4
                else:
                    step = 2

                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    nums = [next_num() for _ in range(step)]
                    pts = []
                    if abs_cmd == "C":
                        x1, y1, x2, y2, x, y = nums
                        if rel:
                            pts = [
                                (curr[0] + x1, curr[1] + y1),
                                (curr[0] + x2, curr[1] + y2),
                                (curr[0] + x, curr[1] + y),
                            ]
                            curr = (curr[0] + x, curr[1] + y)
                        else:
                            pts = [(x1, y1), (x2, y2), (x, y)]
                            curr = (x, y)
                    elif abs_cmd == "S":
                        x2, y2, x, y = nums
                        if rel:
                            pts = [
                                (curr[0] + x2, curr[1] + y2),
                                (curr[0] + x, curr[1] + y),
                            ]
                            curr = (curr[0] + x, curr[1] + y)
                        else:
                            pts = [(x2, y2), (x, y)]
                            curr = (x, y)
                    elif abs_cmd == "Q":
                        x1, y1, x, y = nums
                        if rel:
                            pts = [
                                (curr[0] + x1, curr[1] + y1),
                                (curr[0] + x, curr[1] + y),
                            ]
                            curr = (curr[0] + x, curr[1] + y)
                        else:
                            pts = [(x1, y1), (x, y)]
                            curr = (x, y)
                    else:  # T
                        x, y = nums
                        if rel:
                            curr = (curr[0] + x, curr[1] + y)
                        else:
                            curr = (x, y)
                        pts = [curr]
                    points.extend(pts)

            elif abs_cmd == "A":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    rx = next_num()
                    ry = next_num()
                    _ = next_num()  # rotation
                    _ = next_num()  # large-arc
                    _ = next_num()  # sweep
                    x = next_num()
                    y = next_num()
                    if rel:
                        x += curr[0]
                        y += curr[1]
                    points.extend([
                        (curr[0] - abs(rx), curr[1] - abs(ry)),
                        (curr[0] + abs(rx), curr[1] + abs(ry)),
                        (x - abs(rx), y - abs(ry)),
                        (x + abs(rx), y + abs(ry)),
                        (x, y),
                    ])
                    curr = (x, y)

            elif abs_cmd == "Z":
                curr = subpath_start
                points.append(curr)

            else:
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    idx += 1

    except (IndexError, ValueError):
        return _bbox_from_points(points)

    return _bbox_from_points(points)


def compute_local_bbox(node: Any, ancestors: Sequence) -> Optional[BBox]:
    tag = _node_tag(node).lower()

    if tag == "g":
        return None

    if tag in {"rect", "image", "foreignobject", "use"}:
        x = _attr_to_float(_get_attr_with_style(node, "x", 0.0), 0.0)
        y = _attr_to_float(_get_attr_with_style(node, "y", 0.0), 0.0)
        w = _attr_to_float(_get_attr_with_style(node, "width", 0.0), 0.0)
        h = _attr_to_float(_get_attr_with_style(node, "height", 0.0), 0.0)
        return BBox(x, y, x + w, y + h)

    if tag == "circle":
        cx = _attr_to_float(_get_attr_with_style(node, "cx", 0.0), 0.0)
        cy = _attr_to_float(_get_attr_with_style(node, "cy", 0.0), 0.0)
        r = abs(_attr_to_float(_get_attr_with_style(node, "r", 0.0), 0.0))
        return BBox(cx - r, cy - r, cx + r, cy + r)

    if tag == "ellipse":
        cx = _attr_to_float(_get_attr_with_style(node, "cx", 0.0), 0.0)
        cy = _attr_to_float(_get_attr_with_style(node, "cy", 0.0), 0.0)
        rx = abs(_attr_to_float(_get_attr_with_style(node, "rx", 0.0), 0.0))
        ry = abs(_attr_to_float(_get_attr_with_style(node, "ry", 0.0), 0.0))
        return BBox(cx - rx, cy - ry, cx + rx, cy + ry)

    if tag == "line":
        x1 = _attr_to_float(_get_attr_with_style(node, "x1", 0.0), 0.0)
        y1 = _attr_to_float(_get_attr_with_style(node, "y1", 0.0), 0.0)
        x2 = _attr_to_float(_get_attr_with_style(node, "x2", 0.0), 0.0)
        y2 = _attr_to_float(_get_attr_with_style(node, "y2", 0.0), 0.0)
        return BBox(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    if tag in {"polygon", "polyline"}:
        pts = _parse_points_attr(_get_attr_with_style(node, "points", ""))
        return _bbox_from_points(pts)

    if tag == "path":
        return _parse_path_bbox(_get_attr_with_style(node, "d", ""))

    if tag == "text":
        anchor_x = _attr_to_float(_get_attr_with_style(node, "x", 0.0), 0.0)
        anchor_y = _attr_to_float(_get_attr_with_style(node, "y", 0.0), 0.0)
        font_size = _resolve_font_size(node, ancestors)
        text_anchor = _resolve_text_anchor(node, ancestors)
        text = _extract_all_text(node)
        estimated_w = estimate_text_width(text, font_size)

        if text_anchor == "middle":
            x_min = anchor_x - estimated_w / 2.0
            x_max = anchor_x + estimated_w / 2.0
        elif text_anchor == "end":
            x_min = anchor_x - estimated_w
            x_max = anchor_x
        else:
            x_min = anchor_x
            x_max = anchor_x + estimated_w

        y_min = anchor_y - font_size * 0.8
        y_max = anchor_y + font_size * 0.2
        return BBox(x_min, y_min, x_max, y_max)

    return None


# =============================================================================
# Core algorithm 1: absolute coordinate calculation
# =============================================================================

def calculate_absolute_bbox(
    node: Any,
    parent_ctm: Matrix3x3,
    ancestors: Sequence = (),
) -> Optional[BBox]:
    local_bbox = compute_local_bbox(node, ancestors)
    if local_bbox is None:
        return None
    local_matrix = parse_transform(_get_attr(node, "transform", None))
    current_ctm = matrix_multiply(parent_ctm, local_matrix)
    corners = [
        (local_bbox.x_min, local_bbox.y_min),
        (local_bbox.x_max, local_bbox.y_min),
        (local_bbox.x_min, local_bbox.y_max),
        (local_bbox.x_max, local_bbox.y_max),
    ]
    abs_corners = [apply_matrix(current_ctm, pt) for pt in corners]
    return BBox(
        x_min=min(p[0] for p in abs_corners),
        y_min=min(p[1] for p in abs_corners),
        x_max=max(p[0] for p in abs_corners),
        y_max=max(p[1] for p in abs_corners),
    )


def _node_identity_path(node: Any, parent_path: str, sibling_index: int) -> str:
    node_id = _get_attr(node, "id", None)
    if isinstance(node_id, str) and node_id.strip():
        return "{}#{}".format(parent_path, node_id.strip())
    tag = _node_tag(node).lower() or "unknown"
    return "{}/{}[{}]".format(parent_path, tag, sibling_index)


def build_element_records(svg_dom: Any) -> list:
    """
    Walk the entire DOM tree and resolve every non-<g> leaf element into
    absolute root-space records.

    [FIX-6] Added depth protection to prevent RecursionError on deeply
    nested SVG structures.
    """
    root = getattr(svg_dom, "root", getattr(svg_dom, "documentElement", svg_dom))
    records: list = []

    def walk(node, parent_ctm, ancestors, path, depth=0):
        # [FIX-6] Depth guard
        if depth > MAX_DOM_DEPTH:
            return

        local_matrix = parse_transform(_get_attr(node, "transform", None))
        current_ctm = matrix_multiply(parent_ctm, local_matrix)
        tag = _node_tag(node).lower()

        if tag == "g":
            children = _node_children(node)
            tag_counts: dict[str, int] = {}
            for child in children:
                child_tag = _node_tag(child).lower() or "unknown"
                tag_counts[child_tag] = tag_counts.get(child_tag, 0) + 1
                child_path = _node_identity_path(child, path, tag_counts[child_tag])
                walk(child, current_ctm, ancestors + [node], child_path, depth + 1)
            return

        local_bbox = compute_local_bbox(node, ancestors)
        if local_bbox is None:
            children = _node_children(node)
            if children:
                tag_counts: dict[str, int] = {}
                for child in children:
                    child_tag = _node_tag(child).lower() or "unknown"
                    tag_counts[child_tag] = tag_counts.get(child_tag, 0) + 1
                    child_path = _node_identity_path(child, path, tag_counts[child_tag])
                    walk(child, current_ctm, ancestors + [node], child_path, depth + 1)
            return

        corners = [
            (local_bbox.x_min, local_bbox.y_min),
            (local_bbox.x_max, local_bbox.y_min),
            (local_bbox.x_min, local_bbox.y_max),
            (local_bbox.x_max, local_bbox.y_max),
        ]
        abs_corners = [apply_matrix(current_ctm, pt) for pt in corners]
        abs_bbox = BBox(
            x_min=min(pt[0] for pt in abs_corners),
            y_min=min(pt[1] for pt in abs_corners),
            x_max=max(pt[0] for pt in abs_corners),
            y_max=max(pt[1] for pt in abs_corners),
        )

        text_anchor = _resolve_text_anchor(node, ancestors) if tag == "text" else "start"
        raw_x = _attr_to_float(
            _get_attr_with_style(node, "x", _get_attr_with_style(node, "cx", 0.0)), 0.0
        )
        raw_y = _attr_to_float(
            _get_attr_with_style(node, "y", _get_attr_with_style(node, "cy", 0.0)), 0.0
        )

        records.append(
            ElementRecord(
                node=node,
                bbox=abs_bbox,
                abs_matrix=current_ctm,
                tag=tag,
                text_anchor=text_anchor,
                raw_x=raw_x,
                raw_y=raw_y,
                node_path=path,
                parent_ctm=parent_ctm,
                local_matrix=local_matrix,
            )
        )

    walk(root, make_identity_matrix(), [], _node_identity_path(root, "", 1))
    return records


# =============================================================================
# Core algorithm 2: alignment detection
# =============================================================================

def _bboxes_share_perpendicular_band(
    a_bbox, b_bbox, axis: str, gap_tolerance: float = 20.0
) -> bool:
    """
    Check whether two bboxes are close enough on the perpendicular axis
    to be considered part of the same visual region.

    axis="y" checks vertical proximity (for LEFT/RIGHT/CENTER_H alignment).
    axis="x" checks horizontal proximity (for TOP/BOTTOM/CENTER_V alignment).

    Two bboxes "share a band" if they overlap OR are within gap_tolerance
    pixels of each other on that axis.  This prevents grouping elements
    that live in completely different columns/rows while still allowing
    elements at moderately different positions (e.g. different rows in the
    same column) to be aligned together.
    """
    if axis == "y":
        # Check vertical proximity: do the Y ranges overlap or come close?
        lo = max(a_bbox.y_min, b_bbox.y_min)
        hi = min(a_bbox.y_max, b_bbox.y_max)
    else:
        # Check horizontal proximity
        lo = max(a_bbox.x_min, b_bbox.x_min)
        hi = min(a_bbox.x_max, b_bbox.x_max)

    # If ranges overlap, they definitely share a band
    if hi >= lo:
        return True

    # If gap is within tolerance, they're "close enough"
    return abs(hi - lo) <= gap_tolerance


def _cluster_with_perp_check(
    sorted_recs: list,
    atype,
    key_fn,
    cluster_window: float,
    min_size: int,
    perp_axis: str,
) -> list:
    """
    Build clusters on the primary alignment axis, but only add an element
    to the current cluster if it also overlaps on the perpendicular axis
    with at least ONE existing member.

    This prevents, for example, grouping three column titles at x=48/51/52
    that live at completely different Y positions into one LEFT-alignment group.

    Rule: the perp check is ONLY applied when the new element would expand
    the cluster's primary-axis range beyond 0.  If all elements in the
    cluster share the same primary coordinate, they are genuinely aligned
    already and should stay grouped regardless of perpendicular overlap.
    """
    groups: list = []
    current_cluster = [sorted_recs[0]]

    for rec in sorted_recs[1:]:
        primary_within = key_fn(rec) - key_fn(current_cluster[0]) <= cluster_window

        # Perp check: only needed when the candidate differs on the primary axis.
        # If key(candidate) == key(cluster[0]) the elements are already aligned —
        # keep them together.
        primary_differs = key_fn(rec) != key_fn(current_cluster[0])

        if not primary_within:
            # Outside cluster window — flush and start new cluster
            if len(current_cluster) >= min_size:
                groups.append(AlignmentGroup(atype, current_cluster.copy()))
            current_cluster = [rec]
        elif not primary_differs:
            # Already on the same primary coordinate — always include
            current_cluster.append(rec)
        else:
            # Within cluster window but different primary coord —
            # require perpendicular overlap to prevent cross-column grouping
            perp_ok = False
            for existing in current_cluster:
                if _bboxes_share_perpendicular_band(rec.bbox, existing.bbox, perp_axis):
                    perp_ok = True
                    break

            if perp_ok:
                current_cluster.append(rec)
            else:
                if len(current_cluster) >= min_size:
                    groups.append(AlignmentGroup(atype, current_cluster.copy()))
                current_cluster = [rec]

    if len(current_cluster) >= min_size:
        groups.append(AlignmentGroup(atype, current_cluster.copy()))

    return groups


def find_candidate_groups(
    records: Sequence, threshold: float = ALIGN_THRESHOLD
) -> list:
    if len(records) < 2:
        return []

    cluster_window = threshold * CLUSTER_WINDOW_FACTOR
    groups: list = []

    coord_fns: dict = {
        AlignmentType.LEFT: lambda r: r.bbox.x_min,
        AlignmentType.RIGHT: lambda r: r.bbox.x_max,
        AlignmentType.TOP: lambda r: r.bbox.y_min,
        AlignmentType.BOTTOM: lambda r: r.bbox.y_max,
        AlignmentType.CENTER_H: lambda r: r.bbox.cx,
        AlignmentType.CENTER_V: lambda r: r.bbox.cy,
        AlignmentType.DISTRIBUTE_H: lambda r: r.bbox.cx,
        AlignmentType.DISTRIBUTE_V: lambda r: r.bbox.cy,
    }

    # For each alignment type, specify which perpendicular axis to check.
    # LEFT/RIGHT/CENTER_H align horizontally → must overlap on Y axis.
    # TOP/BOTTOM/CENTER_V align vertically → must overlap on X axis.
    perp_axis_map: dict = {
        AlignmentType.LEFT: "y",
        AlignmentType.RIGHT: "y",
        AlignmentType.TOP: "x",
        AlignmentType.BOTTOM: "x",
        AlignmentType.CENTER_H: "y",
        AlignmentType.CENTER_V: "x",
        AlignmentType.DISTRIBUTE_H: "y",
        AlignmentType.DISTRIBUTE_V: "x",
    }

    for atype in AlignmentType:
        key_fn = coord_fns[atype]
        sorted_recs = sorted(records, key=key_fn)
        if len(sorted_recs) < 2:
            continue

        min_size = 3 if atype in {
            AlignmentType.DISTRIBUTE_H, AlignmentType.DISTRIBUTE_V
        } else 2

        cluster_groups = _cluster_with_perp_check(
            sorted_recs,
            atype,
            key_fn,
            cluster_window,
            min_size,
            perp_axis_map[atype],
        )
        groups.extend(cluster_groups)

    return groups


def _plan_snap_alignment(members: Sequence, atype: AlignmentType) -> list:
    coord_fn: dict = {
        AlignmentType.LEFT: lambda r: r.bbox.x_min,
        AlignmentType.RIGHT: lambda r: r.bbox.x_max,
        AlignmentType.TOP: lambda r: r.bbox.y_min,
        AlignmentType.BOTTOM: lambda r: r.bbox.y_max,
        AlignmentType.CENTER_H: lambda r: r.bbox.cx,
        AlignmentType.CENTER_V: lambda r: r.bbox.cy,
    }

    values = [coord_fn[atype](r) for r in members]
    val_min = min(values)
    val_max = max(values)
    val_range = val_max - val_min

    if val_range >= ALIGN_THRESHOLD:
        return []

    if atype in {AlignmentType.LEFT, AlignmentType.TOP}:
        baseline = val_min
    elif atype in {AlignmentType.RIGHT, AlignmentType.BOTTOM}:
        baseline = val_max
    else:
        baseline = mean(values)

    return [
        AlignmentAction(
            action_id=str(uuid.uuid4()),
            alignment_type=atype,
            affected_nodes=[r.node_path for r in members],
            before_values=values,
            after_values=[baseline] * len(members),
            baseline_value=baseline,
            range_px=val_range,
            dry_run=False,
        )
    ]


def _plan_distribution(members: Sequence, axis: str) -> list:
    if len(members) < 3:
        return []

    if axis == "horizontal":
        sort_key = lambda r: r.bbox.x_min
        edge_fn = lambda a, b: b.bbox.x_min - a.bbox.x_max
        atype = AlignmentType.DISTRIBUTE_H
    else:
        sort_key = lambda r: r.bbox.y_min
        edge_fn = lambda a, b: b.bbox.y_min - a.bbox.y_max
        atype = AlignmentType.DISTRIBUTE_V

    sorted_members = sorted(members, key=sort_key)
    n = len(sorted_members)
    if n < 3:
        return []

    gaps = [edge_fn(sorted_members[i], sorted_members[i + 1]) for i in range(n - 1)]
    gap_range = max(gaps) - min(gaps)

    if gap_range >= ALIGN_THRESHOLD:
        return []

    target_gap = mean(gaps)
    before_coords = [sort_key(r) for r in sorted_members]
    after_coords = [before_coords[0]]

    for i in range(1, n):
        prev = sorted_members[i - 1]
        prev_after = after_coords[i - 1]
        if axis == "horizontal":
            next_coord = prev_after + prev.bbox.width + target_gap
        else:
            next_coord = prev_after + prev.bbox.height + target_gap
        after_coords.append(next_coord)

    return [
        AlignmentAction(
            action_id=str(uuid.uuid4()),
            alignment_type=atype,
            affected_nodes=[r.node_path for r in sorted_members],
            before_values=before_coords,
            after_values=after_coords,
            baseline_value=target_gap,
            range_px=gap_range,
            dry_run=False,
        )
    ]


def detect_and_plan(groups: Sequence) -> list:
    actions: list = []

    for group in groups:
        atype = group.alignment_type
        members = group.records

        if atype in {
            AlignmentType.LEFT,
            AlignmentType.RIGHT,
            AlignmentType.TOP,
            AlignmentType.BOTTOM,
            AlignmentType.CENTER_H,
            AlignmentType.CENTER_V,
        }:
            actions.extend(_plan_snap_alignment(members, atype))
        elif atype == AlignmentType.DISTRIBUTE_H:
            actions.extend(_plan_distribution(members, axis="horizontal"))
        elif atype == AlignmentType.DISTRIBUTE_V:
            actions.extend(_plan_distribution(members, axis="vertical"))

    return _deduplicate_actions(actions)


# Axis grouping for cross-type deduplication: a node should only be
# touched by at most one action on each axis.
_HORIZONTAL_TYPES: frozenset = frozenset({
    AlignmentType.LEFT,
    AlignmentType.RIGHT,
    AlignmentType.CENTER_H,
    AlignmentType.DISTRIBUTE_H,
})
_VERTICAL_TYPES: frozenset = frozenset({
    AlignmentType.TOP,
    AlignmentType.BOTTOM,
    AlignmentType.CENTER_V,
    AlignmentType.DISTRIBUTE_V,
})


def _deduplicate_actions(actions: Sequence) -> list:
    """
    Keep the smaller-range action when the same node appears in multiple
    actions of the same alignment type.

    Additionally, prevent cross-axis conflicts: a node must not appear in
    more than one HORIZONTAL action or more than one VERTICAL action,
    because applying conflicting corrections would corrupt coordinates.
    """
    ordered = sorted(actions, key=lambda a: a.range_px)
    kept: list = []
    seen_by_type: dict = {atype: set() for atype in AlignmentType}
    # Cross-type tracking: one set per axis
    seen_h_nodes: set = set()
    seen_v_nodes: set = set()

    for action in ordered:
        conflict = False
        # Per-type check (existing behavior)
        seen_nodes = seen_by_type.setdefault(action.alignment_type, set())
        for nid in action.affected_nodes:
            if nid in seen_nodes:
                conflict = True
                break

        # Cross-type axis check
        if not conflict:
            if action.alignment_type in _HORIZONTAL_TYPES:
                axis_seen = seen_h_nodes
            elif action.alignment_type in _VERTICAL_TYPES:
                axis_seen = seen_v_nodes
            else:
                axis_seen = set()

            for nid in action.affected_nodes:
                if nid in axis_seen:
                    conflict = True
                    break

        if conflict:
            continue
        kept.append(action)
        for nid in action.affected_nodes:
            seen_nodes.add(nid)
            if action.alignment_type in _HORIZONTAL_TYPES:
                seen_h_nodes.add(nid)
            elif action.alignment_type in _VERTICAL_TYPES:
                seen_v_nodes.add(nid)

    return kept


def detect_and_fix_alignments(
    records: Sequence,
    threshold: float = ALIGN_THRESHOLD,
) -> list:
    """
    Pure planning function: detect candidate groups and return the
    corrections that should be applied.
    """
    groups = find_candidate_groups(records, threshold=threshold)
    actions = detect_and_plan(groups)
    return actions


# =============================================================================
# Core correction / write-back
# =============================================================================

def adjust_for_text_anchor(rec: ElementRecord, abs_coord: float, axis: str) -> float:
    """
    Convert a visual bbox edge/center coordinate into a text anchor
    coordinate.  This mirrors the pseudo-code contract and is kept as a
    standalone helper.

    [FIX-4] This function must be called in apply_actions() before
    computing the delta for text elements.
    """
    if rec.tag != "text" or axis == "y":
        return abs_coord

    w = rec.bbox.width
    if rec.text_anchor == "middle":
        return abs_coord + w / 2.0
    if rec.text_anchor == "end":
        return abs_coord + w
    return abs_coord


def _translate_points_attr(points_value: str, dx: float, dy: float) -> str:
    if not points_value.strip():
        return points_value
    nums = _parse_float_list(points_value)
    if len(nums) < 2:
        return points_value
    out: list[str] = []
    for i in range(0, len(nums) - 1, 2):
        x = nums[i] + dx
        y = nums[i + 1] + dy
        out.append("{},{}".format(_format_number(x), _format_number(y)))
    return " ".join(out)


def _prepend_translate_transform(node: Any, dx: float, dy: float) -> None:
    old = _get_attr(node, "transform", "")
    translate_str = "translate({},{})".format(_format_number(dx), _format_number(dy))
    if isinstance(old, str) and old.strip():
        new_val = "{} {}".format(translate_str, old.strip())
    else:
        new_val = translate_str
    _set_attr(node, "transform", new_val)


# [FIX-8] Path coordinate translation helper
def _translate_path_d(d_value: str, dx: float, dy: float) -> str:
    """
    Translate all absolute and relative coordinates in an SVG path 'd'
    attribute by (dx, dy).  For absolute commands, we shift the endpoint
    coordinates.  For relative commands, only the initial M/m is shifted
    (subsequent relative moves are unaffected by a global translation).
    """
    if not isinstance(d_value, str) or not d_value.strip():
        return d_value

    tokens = re.findall(
        r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",
        d_value,
    )
    if not tokens:
        return d_value

    def is_cmd(tok: str) -> bool:
        return len(tok) == 1 and tok.isalpha()

    result_tokens: list[str] = []
    idx = 0
    cmd = ""
    first_move = True

    def read_num() -> str:
        nonlocal idx
        if idx >= len(tokens):
            raise IndexError
        tok = tokens[idx]
        idx += 1
        return tok

    def shift_and_format(raw_tok: str, delta: float) -> str:
        try:
            val = float(raw_tok)
            return _format_number(val + delta)
        except (ValueError, TypeError):
            return raw_tok

    try:
        while idx < len(tokens):
            tok = tokens[idx]
            if is_cmd(tok):
                cmd = tok
                idx += 1
                result_tokens.append(cmd)

            abs_cmd = cmd.upper() if cmd else ""
            rel = cmd.islower() if cmd else False

            if abs_cmd == "M":
                # First M command: shift both x and y
                x_tok = read_num()
                y_tok = read_num()
                if first_move:
                    result_tokens.append(shift_and_format(x_tok, dx))
                    result_tokens.append(shift_and_format(y_tok, dy))
                    first_move = False
                else:
                    # Subsequent M coords (implicit L): shift
                    if rel:
                        result_tokens.append(x_tok)
                        result_tokens.append(y_tok)
                    else:
                        result_tokens.append(shift_and_format(x_tok, dx))
                        result_tokens.append(shift_and_format(y_tok, dy))

                # Handle implicit subsequent coordinate pairs
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.append(x_tok)
                        result_tokens.append(y_tok)
                    else:
                        result_tokens.append(shift_and_format(x_tok, dx))
                        result_tokens.append(shift_and_format(y_tok, dy))

            elif abs_cmd == "L":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.append(x_tok)
                        result_tokens.append(y_tok)
                    else:
                        result_tokens.append(shift_and_format(x_tok, dx))
                        result_tokens.append(shift_and_format(y_tok, dy))

            elif abs_cmd == "H":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x_tok = read_num()
                    if rel:
                        result_tokens.append(x_tok)
                    else:
                        result_tokens.append(shift_and_format(x_tok, dx))

            elif abs_cmd == "V":
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    y_tok = read_num()
                    if rel:
                        result_tokens.append(y_tok)
                    else:
                        result_tokens.append(shift_and_format(y_tok, dy))

            elif abs_cmd == "C":
                # x1 y1 x2 y2 x y - only shift endpoint (x,y) for relative
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x1_tok = read_num()
                    y1_tok = read_num()
                    x2_tok = read_num()
                    y2_tok = read_num()
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.extend([x1_tok, y1_tok, x2_tok, y2_tok, x_tok, y_tok])
                    else:
                        result_tokens.extend([
                            shift_and_format(x1_tok, dx),
                            shift_and_format(y1_tok, dy),
                            shift_and_format(x2_tok, dx),
                            shift_and_format(y2_tok, dy),
                            shift_and_format(x_tok, dx),
                            shift_and_format(y_tok, dy),
                        ])

            elif abs_cmd == "S":
                # x2 y2 x y
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x2_tok = read_num()
                    y2_tok = read_num()
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.extend([x2_tok, y2_tok, x_tok, y_tok])
                    else:
                        result_tokens.extend([
                            shift_and_format(x2_tok, dx),
                            shift_and_format(y2_tok, dy),
                            shift_and_format(x_tok, dx),
                            shift_and_format(y_tok, dy),
                        ])

            elif abs_cmd == "Q":
                # x1 y1 x y
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x1_tok = read_num()
                    y1_tok = read_num()
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.extend([x1_tok, y1_tok, x_tok, y_tok])
                    else:
                        result_tokens.extend([
                            shift_and_format(x1_tok, dx),
                            shift_and_format(y1_tok, dy),
                            shift_and_format(x_tok, dx),
                            shift_and_format(y_tok, dy),
                        ])

            elif abs_cmd == "T":
                # x y
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    x_tok = read_num()
                    y_tok = read_num()
                    if rel:
                        result_tokens.extend([x_tok, y_tok])
                    else:
                        result_tokens.extend([
                            shift_and_format(x_tok, dx),
                            shift_and_format(y_tok, dy),
                        ])

            elif abs_cmd == "A":
                # rx ry x-axis-rotation large-arc-flag sweep-flag x y
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    rx_tok = read_num()
                    ry_tok = read_num()
                    rot_tok = read_num()
                    la_tok = read_num()
                    sw_tok = read_num()
                    x_tok = read_num()
                    y_tok = read_num()
                    result_tokens.extend([rx_tok, ry_tok, rot_tok, la_tok, sw_tok])
                    if rel:
                        result_tokens.extend([x_tok, y_tok])
                    else:
                        result_tokens.extend([
                            shift_and_format(x_tok, dx),
                            shift_and_format(y_tok, dy),
                        ])

            elif abs_cmd == "Z":
                pass  # Z has no parameters

            else:
                # Unknown command: pass through remaining tokens until next cmd
                while idx < len(tokens) and not is_cmd(tokens[idx]):
                    result_tokens.append(read_num())

    except (IndexError, ValueError):
        pass

    return " ".join(result_tokens)


def _translate_node_local(node: Any, dx: float, dy: float) -> None:
    """
    Shift a node in its own local coordinate space.
    Fallbacks are conservative and deterministic.

    [FIX-8] Added explicit path handling.
    """
    tag = _node_tag(node).lower()

    if tag in {"rect", "image", "foreignobject", "use", "text"}:
        x = _attr_to_float(_get_attr_with_style(node, "x", 0.0), 0.0)
        y = _attr_to_float(_get_attr_with_style(node, "y", 0.0), 0.0)
        _set_attr(node, "x", _format_number(x + dx))
        _set_attr(node, "y", _format_number(y + dy))
        return

    if tag in {"circle", "ellipse"}:
        cx = _attr_to_float(_get_attr_with_style(node, "cx", 0.0), 0.0)
        cy = _attr_to_float(_get_attr_with_style(node, "cy", 0.0), 0.0)
        _set_attr(node, "cx", _format_number(cx + dx))
        _set_attr(node, "cy", _format_number(cy + dy))
        return

    if tag == "line":
        for attr in ("x1", "x2"):
            val = _attr_to_float(_get_attr_with_style(node, attr, 0.0), 0.0)
            _set_attr(node, attr, _format_number(val + dx))
        for attr in ("y1", "y2"):
            val = _attr_to_float(_get_attr_with_style(node, attr, 0.0), 0.0)
            _set_attr(node, attr, _format_number(val + dy))
        return

    if tag in {"polygon", "polyline"}:
        points_value = _get_attr_with_style(node, "points", "")
        if isinstance(points_value, str) and points_value.strip():
            _set_attr(node, "points", _translate_points_attr(points_value, dx, dy))
            return

    # [FIX-8] Handle path elements by modifying the 'd' attribute directly
    if tag == "path":
        d_value = _get_attr_with_style(node, "d", "")
        if isinstance(d_value, str) and d_value.strip():
            new_d = _translate_path_d(d_value, dx, dy)
            _set_attr(node, "d", new_d)
            return

    # Best-effort fallback for other drawable nodes: add a local translation.
    _prepend_translate_transform(node, dx, dy)


def apply_actions(
    actions: Sequence,
    records: Sequence,
    dry_run: bool = False,
) -> None:
    """
    Apply the planned actions to the underlying live DOM nodes held by records.
    This mutates the provided node objects.

    [FIX-3] Uses full_ctm = parent_ctm * local_matrix for inverse transform
    instead of just parent_ctm, so that elements with their own transform
    attribute (rotate, scale, etc.) are correctly adjusted.

    [FIX-4] Calls adjust_for_text_anchor() before computing delta for text
    elements, so the text-anchor offset is properly accounted for.
    """
    rec_map = {rec.node_path: rec for rec in records}

    for action in actions:
        action.dry_run = dry_run
        if dry_run:
            continue

        for i, node_id in enumerate(action.affected_nodes):
            rec = rec_map.get(node_id)
            if rec is None:
                continue

            before = action.before_values[i]
            after = action.after_values[i]

            # [FIX-4] Adjust for text-anchor before computing delta
            if rec.tag == "text":
                if action.alignment_type in {
                    AlignmentType.LEFT,
                    AlignmentType.RIGHT,
                    AlignmentType.CENTER_H,
                    AlignmentType.DISTRIBUTE_H,
                }:
                    before = adjust_for_text_anchor(rec, before, "x")
                    after = adjust_for_text_anchor(rec, after, "x")
                elif action.alignment_type in {
                    AlignmentType.TOP,
                    AlignmentType.BOTTOM,
                    AlignmentType.CENTER_V,
                    AlignmentType.DISTRIBUTE_V,
                }:
                    before = adjust_for_text_anchor(rec, before, "y")
                    after = adjust_for_text_anchor(rec, after, "y")

            delta_abs = after - before

            if action.alignment_type in {
                AlignmentType.LEFT,
                AlignmentType.RIGHT,
                AlignmentType.CENTER_H,
                AlignmentType.DISTRIBUTE_H,
            }:
                delta_abs_vec = (delta_abs, 0.0)
            else:
                delta_abs_vec = (0.0, delta_abs)

            # [FIX-3] Use full CTM (parent * local) for inverse transform
            # so that elements with their own transform are correctly adjusted.
            full_ctm = matrix_multiply(rec.parent_ctm, rec.local_matrix)
            inv_ctm = invert_matrix(full_ctm)
            if inv_ctm is None:
                # Singular transform: skip rather than introduce undefined behavior.
                continue

            delta_local = apply_vector(inv_ctm, delta_abs_vec)
            _translate_node_local(rec.node, delta_local[0], delta_local[1])


# =============================================================================
# Optional convenience wrapper for a pre-parsed SVG DOM
# =============================================================================

def align_svg_dom(
    svg_dom: Any,
    dry_run: bool = False,
    threshold: float = ALIGN_THRESHOLD,
) -> AlignerResult:
    """
    Convenience entry point for a pre-parsed SVG DOM tree.
    Deep-copies the DOM before any mutation to preserve caller purity.
    """
    dom_copy = copy.deepcopy(svg_dom)
    records = build_element_records(dom_copy)
    groups = find_candidate_groups(records, threshold=threshold)
    actions = detect_and_plan(groups)

    apply_actions(actions, records, dry_run=dry_run)

    stats = {
        "total_elements_scanned": len(records),
        "total_groups_checked": len(groups),
        "corrections_applied": sum(
            1 for a in actions if not a.dry_run and a.range_px < threshold
        ),
        "corrections_skipped_threshold": max(0, len(groups) - len(actions)),
        "dry_run": dry_run,
    }

    return AlignerResult(
        svg_string="",
        actions=actions,
        stats=stats,
    )


# =============================================================================
# Small utility exposed for downstream tooling
# =============================================================================

def dataclass_to_dict(obj: Any) -> Any:
    if hasattr(obj, _DUNDER + "dataclass_fields" + _DUNDER):
        return asdict(obj)
    if isinstance(obj, list):
        return [dataclass_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    return obj


# =============================================================================
# XML Parsing (外围补全)
# =============================================================================

def _repair_malformed_svg(svg_string: str) -> str:
    """
    Attempt best-effort repairs on malformed SVG before parsing.

    Fixes common issues that would otherwise cause ET.ParseError:
    - Unclosed <g> tags at end of document
    - Non-SVG foreign elements (<div>, <span>, etc.)
    - CDATA sections that confuse the parser
    Returns the (possibly repaired) SVG string, or raises if unrecoverable.
    """
    import re as _re

    clean = svg_string.strip()

    # Strip XML declaration (may be malformed)
    if clean.startswith("<?xml"):
        m = _re.match(r"<\?xml.*?\?>", clean, _re.S)
        if m:
            clean = clean[m.end():].lstrip()

    # Remove CDATA sections — they confuse ET iteration but content
    # is not SVG elements anyway
    clean = _re.sub(r"<!\[CDATA\[.*?\]\]>", "", clean, flags=_re.S)

    # Strip known non-SVG foreign elements (<div>, <span>, <style>,
    # <script>, <link>, <meta>) but keep their text content so the
    # rest of the DOM stays intact
    for tag in ("div", "span", "script", "link", "meta", "style", "br", "img"):
        clean = _re.sub(
            r"<" + tag + r"[^>]*>.*?</" + tag + r">",
            "",
            clean,
            flags=_re.S | _re.I,
        )
        # Self-closing variants
        clean = _re.sub(
            r"<" + tag + r"[^>]*/>",
            "",
            clean,
            flags=_re.S | _re.I,
        )

    # Auto-close unclosed <g> tags: count opens vs closes, append missing </g>
    opens = len(_re.findall(r"<g[\s>/]", clean))
    closes = len(_re.findall(r"</g>", clean))
    for _ in range(max(0, opens - closes)):
        # Insert </g> before </svg>
        if "</svg>" in clean.lower():
            clean = clean.replace("</svg>", "</g></svg>", 1)
        else:
            # Last resort: just append
            clean = clean.rstrip() + "</g>"

    return clean


def _parse_svg_string(svg_string: str) -> tuple:
    """
    Parse an SVG string into an ElementTree root element.

    [FIX-5] Uses regex-based XML declaration stripping instead of
    str.index("?>") to avoid ValueError on malformed XML.

    [FIX-7] Calls _discover_and_register_namespaces for proper ns handling.

    [FIX-E2E] Attempts auto-repair of malformed SVG (unclosed tags,
    foreign elements, CDATA) before giving up.
    """
    ns_map = _discover_and_register_namespaces(svg_string)

    clean = _repair_malformed_svg(svg_string)

    root = ET.fromstring(clean)
    return root, ns_map


def _actions_to_log(actions: list) -> list:
    """
    Convert a list of AlignmentAction dataclass instances into plain dicts
    suitable for JSON serialisation.
    """
    log: list = []
    for action in actions:
        entry = {
            "action_id": action.action_id,
            "alignment_type": action.alignment_type.value,
            "affected_nodes": list(action.affected_nodes),
            "before_values": [round(v, 4) for v in action.before_values],
            "after_values": [round(v, 4) for v in action.after_values],
            "baseline_value": round(action.baseline_value, 4),
            "range_px": round(action.range_px, 4),
            "dry_run": action.dry_run,
        }
        log.append(entry)
    return log


# =============================================================================
# Main processing pipeline
# =============================================================================

def process_svg(
    svg_string: str,
    threshold: float = ALIGN_THRESHOLD,
    dry_run: bool = False,
) -> tuple:
    """
    Pure entry point: takes an SVG string, returns (corrected_svg_string,
    action_log) without touching the filesystem.

    Parameters
    ----------
    svg_string : str
        The raw SVG XML content.
    threshold : float
        Maximum pixel deviation to consider elements as "should be aligned".
    dry_run : bool
        If True, no DOM mutations are performed; the returned SVG string
        is identical to the input, but the action log describes what would
        be changed.

    Returns
    -------
    (str, list[dict])
        A 2-tuple of (possibly-modified SVG string, list of action dicts).

    Safety guarantee
    ----------------
    This function NEVER raises uncaught exceptions.  Any parsing error,
    coordinate overflow, or serialisation failure results in the original
    SVG string being returned unchanged with an empty action log.
    """
    try:
        return _process_svg_impl(svg_string, threshold, dry_run)
    except Exception as e:  # pragma: no cover — belt-and-suspenders
        # Last-resort safety net: NEVER crash the caller.
        # Log to stderr so the problem is visible during development.
        import traceback as _tb
        _tb.print_exc()
        return svg_string, []


def _process_svg_impl(
    svg_string: str,
    threshold: float,
    dry_run: bool,
) -> tuple:
    """Internal implementation of process_svg — may raise on fatal errors."""
    # 1. Parse
    et_root, ns_map = _parse_svg_string(svg_string)

    # 2. Wrap for duck-typed compatibility
    wrapped_root = wrap_tree(et_root)

    # 3. Build element records (absolute coordinates)
    records = build_element_records(wrapped_root)

    # 4. Detect alignment groups
    groups = find_candidate_groups(records, threshold=threshold)

    # 5. Plan correction actions
    actions = detect_and_plan(groups)

    # 6. Apply (or dry-run)
    apply_actions(actions, records, dry_run=dry_run)

    # 7. Serialise back
    if dry_run:
        out_svg = svg_string
    else:
        out_svg = _serialize_svg(et_root, ns_map)

    # 8. Build log
    log = _actions_to_log(actions)

    return out_svg, log


# =============================================================================
# CLI
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="svg_aligner",
        description=(
            "Deterministic SVG alignment post-processor.  "
            "Detects near-aligned element groups and snaps them to exact alignment."
        ),
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to the input SVG file.",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help=(
            "Path to the output SVG file.  "
            "If omitted, the input file is overwritten in-place."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Do not modify any file.  "
            "Print the JSON operation log to stdout instead."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=ALIGN_THRESHOLD,
        help=(
            "Maximum pixel deviation to treat elements as aligned "
            "(default: {}).".format(ALIGN_THRESHOLD)
        ),
    )
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_path: str = args.input
    output_path = args.output
    dry_run: bool = args.dry_run
    threshold: float = args.threshold

    # Read input
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            svg_string = f.read()
    except FileNotFoundError:
        print("Error: file not found: {}".format(input_path), file=sys.stderr)
        return 1
    except OSError as exc:
        print("Error reading {}: {}".format(input_path, exc), file=sys.stderr)
        return 1

    # Process
    out_svg, log = process_svg(svg_string, threshold=threshold, dry_run=dry_run)

    # Output
    if dry_run:
        print(json.dumps(log, indent=2, ensure_ascii=False))
    else:
        dest = output_path if output_path else input_path
        try:
            with open(dest, "w", encoding="utf-8") as f:
                f.write(out_svg)
        except OSError as exc:
            print("Error writing {}: {}".format(dest, exc), file=sys.stderr)
            return 1

        n_actions = len(log)
        n_nodes = sum(len(a["affected_nodes"]) for a in log)
        print(
            "[svg_aligner] {} alignment correction(s) applied "
            "to {} element(s) -> {}".format(n_actions, n_nodes, dest),
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
