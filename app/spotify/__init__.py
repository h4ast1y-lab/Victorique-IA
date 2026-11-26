"""
Victorique in Spotify: she walks on its player bar, panels, tabs and covers
(layout.py), and comments on the track playing (watcher.py).

Where the data comes from, best first:
- the Spicetify bridge (bridge.py + victorique.js): exact element positions
  and the track, sent by a small extension inside Spotify;
- Windows' media controls (SMTC, optional `winrt` packages): the track;
- the Spotify window: its size gives the panels by proportion, its title
  ("Artist - Song") the track.
"""
