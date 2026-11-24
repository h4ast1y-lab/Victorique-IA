"""
Where the desktop mascot can stand: the top of the taskbar (the bottom of the
work area) and the visible top edges of open windows.

Pure geometry, no Windows calls: win32.top_windows() supplies the window
rectangles front to back, and this module turns them into walkable segments.
A window's top edge is walkable where no window in front of it covers the
edge line; a covered stretch splits it into several segments that share the
window's key ("w<hwnd>").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

Area = Tuple[float, float, float, float]   # left, top, right, bottom


@dataclass(frozen=True)
class WindowBox:
    hwnd: int
    left: int
    top: int
    right: int
    bottom: int
    maximized: bool = False


@dataclass(frozen=True)
class Surface:
    key: str            # "ground" or "w<hwnd>"
    left: float         # walkable stretch
    right: float
    y: float            # the line her soles rest on
    kind: str = "ground"
    wall_left: float = 0.0     # the window's sides and bottom (for climbing)
    wall_right: float = 0.0
    bottom: float = 0.0

    def contains(self, x: float, slack: float = 0.0) -> bool:
        return self.left - slack <= x <= self.right + slack


@dataclass
class World:
    """Everything the behaviour needs to know about the desktop right now."""
    area: Area                          # work area of the monitor she is on
    height: float                       # her standing height, px
    surfaces: List[Surface] = field(default_factory=list)

    @property
    def ground(self) -> Surface:
        for s in self.surfaces:
            if s.key == "ground":
                return s
        left, _, right, bottom = self.area
        return Surface("ground", left, right, bottom, "ground", left, right, bottom)

    def segments(self, key: str) -> List[Surface]:
        return [s for s in self.surfaces if s.key == key]

    def find(self, key: str, x: float, slack: float = 0.0) -> Optional[Surface]:
        for s in self.surfaces:
            if s.key == key and s.contains(x, slack):
                return s
        return None

    def windows(self) -> List[Surface]:
        return [s for s in self.surfaces if s.kind == "window"]

    def landing(self, x: float, y_from: float, y_to: float) -> Optional[Surface]:
        """The highest surface under x whose line lies between y_from and y_to
        (falling from y_from to y_to)."""
        best: Optional[Surface] = None
        for s in self.surfaces:
            if s.contains(x) and y_from - 0.5 <= s.y <= y_to:
                if best is None or s.y < best.y:
                    best = s
        return best


def ground(area: Area) -> Surface:
    left, _, right, bottom = area
    return Surface("ground", left, right, bottom, "ground", left, right, bottom)


def _subtract(segments: List[Tuple[float, float]], lo: float, hi: float) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for a, b in segments:
        if hi <= a or lo >= b:
            out.append((a, b))
            continue
        if lo > a:
            out.append((a, lo))
        if hi < b:
            out.append((hi, b))
    return out


def window_tops(windows: Sequence[WindowBox], area: Area, height: float) -> List[Surface]:
    """Visible, roomy top edges of `windows` (front to back) on this monitor."""
    left, top, right, bottom = area
    out: List[Surface] = []
    for i, w in enumerate(windows):
        if w.maximized or w.right - w.left < height * 0.9 or w.bottom - w.top < height * 0.35:
            continue
        if w.top < top + height * 0.65 or w.top > bottom - height * 0.5:
            continue    # no room above it for her, or it is down at the taskbar
        if w.right <= left or w.left >= right:
            continue
        segments = [(float(max(w.left, left)), float(min(w.right, right)))]
        for above in windows[:i]:
            if above.top <= w.top + 1 < above.bottom:
                segments = _subtract(segments, above.left, above.right)
                if not segments:
                    break
        for a, b in segments:
            if b - a >= height * 0.45:
                out.append(Surface(f"w{w.hwnd}", a, b, float(w.top), "window",
                                   float(w.left), float(w.right), float(w.bottom)))
    return out


def build_world(area: Area, height: float, windows: Iterable[WindowBox] = ()) -> World:
    surfaces = [ground(area)] + window_tops(list(windows), area, height)
    return World(area=area, height=height, surfaces=surfaces)
