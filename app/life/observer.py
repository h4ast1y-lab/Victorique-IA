"""
Windows presence signals for Victorique's "vida própria", read with ctypes.

Only metadata is read: how long since the last keyboard/mouse input on the
whole PC, and the foreground window's process name and whether it covers its
monitor without a title bar (fullscreen video, game or presentation). No
window titles, screenshots or contents are read. On other systems, or when a
call fails, the functions return None and the policy treats it as unknown.
"""
import ctypes
import os
import sys
from typing import Any, Dict, Optional

_WINDOWS = sys.platform == "win32"

if _WINDOWS:
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetShellWindow.restype = wintypes.HWND
    _user32.GetDesktopWindow.restype = wintypes.HWND
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.GetTickCount64.restype = ctypes.c_ulonglong

_MONITOR_DEFAULTTONEAREST = 2
_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_DESKTOP_CLASSES = {"progman", "workerw", "shell_traywnd"}


def system_idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard or mouse input anywhere on the PC.
    Keeps growing while the session is locked or the screen is off."""
    if not _WINDOWS:
        return None
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    # dwTime is a 32-bit tick count; compare in the same 32-bit space.
    now = _kernel32.GetTickCount64() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


def _process_name(pid: int) -> str:
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(buffer.value).lower()
    finally:
        _kernel32.CloseHandle(handle)


def foreground_window() -> Optional[Dict[str, Any]]:
    """{"process": "name.exe", "fullscreen": bool, "own": bool} for the
    foreground window, or None when there is none (desktop, lock screen)."""
    if not _WINDOWS:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd or hwnd in (_user32.GetShellWindow(), _user32.GetDesktopWindow()):
            return None
        class_buffer = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, class_buffer, 64)
        if class_buffer.value.lower() in _DESKTOP_CLASSES:
            return None

        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        rect = wintypes.RECT()
        fullscreen = False
        if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            monitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if monitor and _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                area = info.rcMonitor
                covers = (rect.left <= area.left and rect.top <= area.top
                          and rect.right >= area.right and rect.bottom >= area.bottom)
                # A maximized ordinary window keeps its title bar; fullscreen
                # video, games and slideshows do not.
                style = _user32.GetWindowLongW(hwnd, _GWL_STYLE) & 0xFFFFFFFF
                fullscreen = covers and (style & _WS_CAPTION) != _WS_CAPTION

        return {
            "process": _process_name(pid.value),
            "fullscreen": fullscreen,
            "own": pid.value == os.getpid(),
        }
    except Exception:
        return None


def snapshot() -> Dict[str, Any]:
    return {"system_idle": system_idle_seconds(), "foreground": foreground_window()}
