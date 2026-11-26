"""
A borderless, always-on-top Win32 window with per-pixel alpha (ctypes only).

Why not a pywebview window: WebView2 cannot show the desktop through its
background here (tested with pywebview 6.2: the "transparent" window paints
gray), while a layered window updated with UpdateLayeredWindow is truly
transparent and lets clicks on transparent pixels fall through to whatever
is behind her, as desktop pets do.

The window lives on its own thread with its own message loop. Everything that
touches it runs on that thread: use :meth:`LayeredWindow.call` from elsewhere.
"""
from __future__ import annotations

import ctypes
import logging
import os
import queue
import threading
from ctypes import wintypes
from typing import Callable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

AVAILABLE = os.name == "nt"

if AVAILABLE:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        shcore = ctypes.WinDLL("shcore")
    except OSError:  # pragma: no cover - very old Windows
        shcore = None
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:  # pragma: no cover
        dwmapi = None

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM) if AVAILABLE else None
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, LPARAM) if AVAILABLE else None

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
CS_DBLCLKS = 0x0008
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_MOUSELEAVE = 0x02A3
WM_CAPTURECHANGED = 0x0215
WM_MOUSEACTIVATE = 0x0021
WM_SETCURSOR = 0x0020
WM_NULL = 0x0000
WM_APP = 0x8000
MA_NOACTIVATE = 3
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x2
AC_SRC_OVER = 0x0
AC_SRC_ALPHA = 0x1
BI_RGB = 0
DIB_RGB_COLORS = 0
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
TME_LEAVE = 0x00000002
MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
IDC_HAND = 32649
IDC_ARROW = 32512
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_APPWINDOW = 0x00040000
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# Apps whose inside she can walk on (surfaces.WindowBox.app), by executable.
APP_PROCESSES = {"spotify.exe": "spotify"}
# Shell surfaces that are not windows she can stand on.
SKIP_CLASSES = {"progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
                "windows.ui.core.corewindow", "victoriquemascot"}
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("hwndTrack", wintypes.HWND), ("dwHoverTime", wintypes.DWORD)]


def _signatures() -> None:
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.UpdateLayeredWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT),
                                           ctypes.POINTER(SIZE), wintypes.HDC, ctypes.POINTER(POINT),
                                           wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    user32.LoadCursorW.restype = wintypes.HANDLE
    user32.SetCursor.argtypes = [wintypes.HANDLE]
    user32.EnumWindows.argtypes = [WNDENUMPROC, LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if dwmapi is not None:
        dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    if hasattr(user32, "SetThreadDpiAwarenessContext"):
        user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p


if AVAILABLE:
    _signatures()


def work_area_at(x: int, y: int) -> Tuple[Tuple[int, int, int, int], float]:
    """((left, top, right, bottom) of the work area of the monitor nearest to
    (x, y), DPI scale of that monitor). Physical pixels on a DPI-aware thread."""
    monitor = user32.MonitorFromPoint(POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    rc = info.rcWork
    scale = 1.0
    if shcore is not None:
        dx, dy = wintypes.UINT(), wintypes.UINT()
        if shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)) == 0:
            scale = dx.value / 96.0
    return (rc.left, rc.top, rc.right, rc.bottom), scale


def cursor_pos() -> Tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def window_box(hwnd: int):
    """The window's visible frame (without the invisible resize borders) as a
    surfaces.WindowBox, or None when it is hidden, minimized or cloaked (on
    another virtual desktop, or a suspended UWP app)."""
    from app.mascot.surfaces import WindowBox
    if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    rect = wintypes.RECT()
    if dwmapi is not None:
        cloaked = wintypes.DWORD()
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked),
                                        ctypes.sizeof(cloaked)) == 0 and cloaked.value:
            return None
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect),
                                        ctypes.sizeof(rect)) != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
    else:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if rect.right - rect.left <= 0 or rect.bottom - rect.top <= 0:
        return None
    return WindowBox(int(hwnd), rect.left, rect.top, rect.right, rect.bottom, bool(user32.IsZoomed(hwnd)))


_process_cache: dict = {}


def process_name(hwnd: int) -> str:
    """Lower-case executable name of the process that owns `hwnd` ("" if unknown)."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    cached = _process_cache.get(pid.value)
    if cached is not None:
        return cached
    name = ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            size = wintypes.DWORD(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                name = os.path.basename(buffer.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    if len(_process_cache) > 256:
        _process_cache.clear()
    _process_cache[pid.value] = name
    return name


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def app_windows(process: str) -> List[Tuple[int, str]]:
    """(hwnd, title) of the visible, titled top-level windows of `process`
    (e.g. "spotify.exe"), front to back."""
    found: List[Tuple[int, str]] = []
    process = process.lower()

    def visit(hwnd, _lparam):
        try:
            if hwnd and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0 \
                    and process_name(hwnd) == process:
                found.append((int(hwnd), window_title(hwnd)))
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found


def top_windows(exclude: Sequence[int] = ()) -> list:
    """Visible application windows, front to back (the z-order), as
    surfaces.WindowBox. Untitled, tool and click-through windows and the
    desktop and taskbar are left out. Physical pixels on a DPI-aware thread."""
    from app.mascot.surfaces import WindowBox
    skip = {int(h) for h in exclude if h}
    found: list = []
    name = ctypes.create_unicode_buffer(64)

    def visit(hwnd, _lparam):
        try:
            if not hwnd or int(hwnd) in skip or not user32.IsWindowVisible(hwnd):
                return True
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
            if ex & WS_EX_TRANSPARENT or (ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW):
                return True
            if user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            user32.GetClassNameW(hwnd, name, 64)
            if name.value.lower() in SKIP_CLASSES:
                return True
            box = window_box(hwnd)
            if box is not None:
                if name.value.lower().startswith("chrome_widgetwin"):
                    app = APP_PROCESSES.get(process_name(hwnd), "")
                    if app:
                        box = WindowBox(box.hwnd, box.left, box.top, box.right, box.bottom,
                                        box.maximized, app)
                found.append(box)
        except Exception:
            pass
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    return found


def _lparam_xy(lparam: int) -> Tuple[int, int]:
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    return x, y


MenuItem = Tuple[int, str, int]  # (id, label, flags); id 0 = separator


class LayeredWindow:
    """Owns the HWND. `on_event(name, *args)` receives, on the window thread:
    tick, down(x, y), move(x, y), up(x, y), dblclick(x, y), rclick(x, y),
    leave(), lost_capture(). x, y are client pixels."""

    CLASS_NAME = "VictoriqueMascot"

    def __init__(self, on_event: Callable[..., None], interval_ms: int = 40, title: str = "Victorique"):
        self.on_event = on_event
        self.interval_ms = interval_ms
        self.title = title
        self.hwnd = None
        self.thread: Optional[threading.Thread] = None
        self.ready = threading.Event()
        self._calls: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._proc = WNDPROC(self._wndproc)
        self._tracking = False
        self._visible = False
        self._size = (0, 0)
        self._dib = None
        self.hand_cursor = False
        self.cursor_hidden = False
        self.pos = (0, 0)

    # ----------------- Thread -----------------
    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="victorique-mascot", daemon=True)
        self.thread.start()
        self.ready.wait(5)

    def call(self, fn: Callable[[], None]) -> None:
        """Runs `fn` on the window thread."""
        self._calls.put(fn)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP, 0, 0)

    def close(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def _run(self) -> None:
        try:
            if hasattr(user32, "SetThreadDpiAwarenessContext"):
                user32.SetThreadDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.style = CS_DBLCLKS
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = self.CLASS_NAME
            wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))  # IDC_ARROW
            user32.RegisterClassExW(ctypes.byref(wc))  # fails harmlessly if already registered
            self.hwnd = user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
                self.CLASS_NAME, self.title, WS_POPUP, 0, 0, 1, 1, None, None, hinst, None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            user32.SetTimer(self.hwnd, 1, self.interval_ms, None)
        except Exception:
            logger.exception("Mascote: não consegui criar a janela.")
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self._free_dib()
        self.hwnd = None

    # ----------------- Messages -----------------
    def _emit(self, name: str, *args) -> None:
        try:
            self.on_event(name, *args)
        except Exception:
            logger.exception("Mascote: erro tratando %s", name)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TIMER:
            self._emit("tick")
            return 0
        if msg == WM_APP:
            while True:
                try:
                    fn = self._calls.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    logger.exception("Mascote: erro numa chamada")
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_SETCURSOR and (self.hand_cursor or self.cursor_hidden):
            user32.SetCursor(None if self.cursor_hidden else user32.LoadCursorW(None, ctypes.c_void_p(IDC_HAND)))
            return 1
        if msg == WM_LBUTTONDOWN:
            user32.SetCapture(hwnd)
            self._emit("down", *_lparam_xy(lparam))
            return 0
        if msg == WM_MOUSEMOVE:
            if not self._tracking:
                tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE, hwnd, 0)
                self._tracking = bool(user32.TrackMouseEvent(ctypes.byref(tme)))
            self._emit("move", *_lparam_xy(lparam))
            return 0
        if msg == WM_LBUTTONUP:
            if user32.GetCapture() == hwnd:
                user32.ReleaseCapture()
            self._emit("up", *_lparam_xy(lparam))
            return 0
        if msg == WM_CAPTURECHANGED:
            self._emit("lost_capture")
            return 0
        if msg == WM_LBUTTONDBLCLK:
            self._emit("dblclick", *_lparam_xy(lparam))
            return 0
        if msg == WM_RBUTTONUP:
            self._emit("rclick", *_lparam_xy(lparam))
            return 0
        if msg == WM_MOUSELEAVE:
            self._tracking = False
            self._emit("leave")
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.KillTimer(hwnd, 1)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ----------------- Drawing (window thread only) -----------------
    def _free_dib(self) -> None:
        if self._dib:
            hdc, bmp, old, _bits = self._dib
            gdi32.SelectObject(hdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(hdc)
            self._dib = None

    def update(self, image, x: int, y: int) -> None:
        """Shows `image` (PIL RGBA) with its top-left corner at screen (x, y)."""
        if not self.hwnd:
            return
        w, h = image.size
        if (w, h) != self._size or not self._dib:
            self._free_dib()
            screen = user32.GetDC(None)
            hdc = gdi32.CreateCompatibleDC(screen)
            user32.ReleaseDC(None, screen)
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = w
            bmi.bmiHeader.biHeight = -h  # top-down
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB
            bits = ctypes.c_void_p()
            bmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
            old = gdi32.SelectObject(hdc, bmp)
            self._dib = (hdc, bmp, old, bits)
            self._size = (w, h)
        hdc, _bmp, _old, bits = self._dib
        data = image.convert("RGBa").tobytes("raw", "BGRa")
        ctypes.memmove(bits, data, len(data))
        screen = user32.GetDC(None)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(POINT(int(x), int(y))),
                                   ctypes.byref(SIZE(w, h)), hdc, ctypes.byref(POINT(0, 0)), 0,
                                   ctypes.byref(blend), ULW_ALPHA)
        user32.ReleaseDC(None, screen)
        self.pos = (int(x), int(y))
        if not self._visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self._visible = True

    def set_visible(self, visible: bool) -> None:
        if self.hwnd and visible != self._visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)
            self._visible = visible

    @property
    def visible(self) -> bool:
        return self._visible

    def hide_cursor(self, hidden: bool) -> None:
        """Hides or restores the real cursor (window thread only). Dragged, she
        hangs from the real arrow, so the desktop keeps it visible; ``True`` is
        kept for frames that draw their own cursor."""
        self.cursor_hidden = hidden
        if hidden:
            user32.SetCursor(None)
        else:
            cursor = IDC_HAND if self.hand_cursor else IDC_ARROW
            user32.SetCursor(user32.LoadCursorW(None, ctypes.c_void_p(cursor)))

    def keep_on_top(self) -> None:
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def popup_menu(self, items: Sequence[MenuItem], x: int, y: int) -> int:
        """Native context menu at screen (x, y); returns the chosen id (0 = none)."""
        menu = user32.CreatePopupMenu()
        try:
            for item_id, label, flags in items:
                if item_id == 0:
                    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                else:
                    user32.AppendMenuW(menu, MF_STRING | flags, item_id, label)
            user32.SetForegroundWindow(self.hwnd)
            chosen = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                                           int(x), int(y), 0, self.hwnd, None)
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
            return int(chosen or 0)
        finally:
            user32.DestroyMenu(menu)


def menu_items(entries: List[Tuple[int, str, bool, bool]]) -> List[MenuItem]:
    """[(id, label, checked, enabled)] -> items for popup_menu."""
    out: List[MenuItem] = []
    for item_id, label, checked, enabled in entries:
        flags = (MF_CHECKED if checked else 0) | (0 if enabled else MF_GRAYED)
        out.append((item_id, label, flags))
    return out
