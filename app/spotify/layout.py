"""
The ledges inside the Spotify window she can stand on (screen pixels).

With the Spicetify bridge, each panel, tab, cover and track row it reports
becomes a ledge at its top edge, mapped from the page's CSS pixels to the
window's visible frame (that ratio also takes care of DPI and zoom). Without
it, or when the report does not match the window (a miniplayer, a stale
report), the panels come from Spotify's usual layout: a navigation bar on
top and the player bar at the bottom.
"""
from __future__ import annotations

from typing import List, Optional

from app.mascot.surfaces import Ledge, WindowBox
from app.spotify.bridge import Bridge, View, bridge as default_bridge

TOP_BAR = 64        # logical px: Spotify's navigation bar
PLAYER_BAR = 72     # logical px: the player bar
GAP = 8             # logical px: the gutter around the panels
ASPECT_SLACK = 0.12


def default_ledges(box: WindowBox, dpi: float) -> List[Ledge]:
    dpi = dpi or 1.0
    top = box.top + TOP_BAR * dpi
    player = box.bottom - PLAYER_BAR * dpi
    out: List[Ledge] = []
    if player - top >= 120 * dpi:
        out.append(Ledge("paineis", box.left + GAP * dpi, box.right - GAP * dpi, top, player - GAP * dpi))
    if player > box.top:
        out.append(Ledge("player", box.left, box.right, player, box.bottom))
    return out


def bridge_ledges(box: WindowBox, view: View) -> Optional[List[Ledge]]:
    """The reported elements on screen, or None when the report does not fit this window."""
    width, height = box.right - box.left, box.bottom - box.top
    if width <= 0 or height <= 0:
        return None
    sx, sy = width / view.width, height / view.height
    if abs(sx - sy) > ASPECT_SLACK * max(sx, sy):
        return None
    out: List[Ledge] = []
    for el in view.elements:
        left = box.left + el.x * sx
        right = box.left + (el.x + el.w) * sx
        y = box.top + el.y * sy
        bottom = box.top + (el.y + el.h) * sy
        if right <= box.left or left >= box.right or y < box.top or y >= box.bottom:
            continue
        out.append(Ledge(f"{el.kind}:{el.id}", max(left, box.left), min(right, box.right), y,
                         min(bottom, box.bottom)))
    return out


def ledges_for(box: WindowBox, dpi: float, bridge: Optional[Bridge] = None) -> List[Ledge]:
    """Ledges of a Spotify window; none for any other window."""
    if box.app != "spotify":
        return []
    view = (bridge or default_bridge).view()
    if view is not None:
        ledges = bridge_ledges(box, view)
        if ledges:
            return ledges
    return default_ledges(box, dpi)
