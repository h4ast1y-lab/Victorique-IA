"""
Where the desktop mascot can stand: the top of the taskbar (the bottom of the
work area) and the visible top edges of open windows.

Pure geometry, no Windows calls: win32.top_windows() supplies the window
rectangles front to back, and this module turns them into walkable segments.
A window's top edge is walkable where no window in front of it covers the
edge line; a covered stretch splits it into several segments that share the
window's key ("w<hwnd>").

Some apps also have ledges inside their window (app/spotify/layout.py: the
player bar, the panels, tabs and covers). They follow the same rule, are kept
even when the window is maximized and use the key "w<hwnd>/<name>", so the
mascot still knows which window she rides on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

Area = Tuple[float, float, float, float]   # left, top, right, bottom


@dataclass(frozen=True)
class WindowBox:
    hwnd: int
    left: int
    top: int
    right: int
    bottom: int
    maximized: bool = False
    app: str = ""       # "spotify" for a window whose inside she can walk on


@dataclass(frozen=True)
class Ledge:
    """A line inside a window she can stand on (screen pixels)."""
    name: str
    left: float
    right: float
    y: float
    bottom: float       # the bottom of the thing whose top is this line


LedgesFn = Callable[[WindowBox], Sequence[Ledge]]


def window_hwnd(key: str) -> Optional[int]:
    """The window handle in a surface key ("w123" or "w123/player")."""
    if not key.startswith("w"):
        return None
    try:
        return int(key[1:].split("/", 1)[0])
    except ValueError:
        return None


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


def _uncovered(segments: List[Tuple[float, float]], front: Sequence[WindowBox],
               y: float) -> List[Tuple[float, float]]:
    """What is left of `segments` on line y once the windows in `front` are drawn over it."""
    for above in front:
        if above.top <= y + 1 < above.bottom:
            segments = _subtract(segments, above.left, above.right)
            if not segments:
                break
    return segments


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
        segments = _uncovered(segments, windows[:i], w.top)
        for a, b in segments:
            if b - a >= height * 0.45:
                out.append(Surface(f"w{w.hwnd}", a, b, float(w.top), "window",
                                   float(w.left), float(w.right), float(w.bottom)))
    return out


def window_ledges(windows: Sequence[WindowBox], area: Area, height: float,
                  ledges_fn: LedgesFn) -> List[Surface]:
    """Visible, roomy ledges inside the `windows` (front to back) on this monitor.
    Unlike the top edges, a maximized window keeps its ledges."""
    left, top, right, bottom = area
    out: List[Surface] = []
    for i, w in enumerate(windows):
        try:
            ledges = ledges_fn(w) or ()
        except Exception:
            continue
        for ledge in ledges:
            y = float(ledge.y)
            if y < top + height * 0.65 or y > bottom - height * 0.3:
                continue    # no room above it for her, or it is down at the taskbar
            if not w.top <= y < w.bottom:
                continue
            a = float(max(ledge.left, w.left, left))
            b = float(min(ledge.right, w.right, right))
            if b - a < height * 0.45:
                continue
            for sa, sb in _uncovered([(a, b)], windows[:i], y):
                if sb - sa >= height * 0.45:
                    out.append(Surface(f"w{w.hwnd}/{ledge.name}", sa, sb, y, "window",
                                       float(ledge.left), float(ledge.right), float(ledge.bottom)))
    return out


def build_world(area: Area, height: float, windows: Iterable[WindowBox] = (),
                ledges: Optional[LedgesFn] = None) -> World:
    windows = list(windows)
    surfaces = [ground(area)] + window_tops(windows, area, height)
    if ledges is not None:
        surfaces += window_ledges(windows, area, height, ledges)
    return World(area=area, height=height, surfaces=surfaces)
