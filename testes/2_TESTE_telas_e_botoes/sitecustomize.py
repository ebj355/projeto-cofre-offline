"""Keeps automated Tk windows behind the user's active app on Windows."""
import os


if os.name == "nt" and os.environ.get("COFRE_GUI_TESTS_BACKGROUND") == "1":
    import ctypes
    import tkinter as tk
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _get_window_long = _user32.GetWindowLongPtrW
    _get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_window_long.restype = ctypes.c_ssize_t
    _set_window_long = _user32.SetWindowLongPtrW
    _set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _set_window_long.restype = ctypes.c_ssize_t
    _set_window_pos = _user32.SetWindowPos
    _set_window_pos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.UINT,
    ]
    _set_window_pos.restype = wintypes.BOOL

    _GWL_EXSTYLE = -20
    _WS_EX_NOACTIVATE = 0x08000000
    _HWND_BOTTOM = wintypes.HWND(1)
    _SWP_NOSIZE = 0x0001
    _SWP_NOMOVE = 0x0002
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020

    def _send_to_background(window):
        try:
            if not window.winfo_exists():
                return
            raw_hwnd = window.tk.call("wm", "frame", window._w)
        except tk.TclError:
            return

        try:
            hwnd = wintypes.HWND(int(str(raw_hwnd), 0))
        except ValueError as exc:
            raise RuntimeError("Could not resolve Tk window handle for background GUI tests.") from exc

        style = _get_window_long(hwnd, _GWL_EXSTYLE)
        ctypes.set_last_error(0)
        if _set_window_long(hwnd, _GWL_EXSTYLE, style | _WS_EX_NOACTIVATE) == 0:
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
        flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_FRAMECHANGED
        if not _set_window_pos(hwnd, _HWND_BOTTOM, 0, 0, 0, 0, flags):
            raise ctypes.WinError(ctypes.get_last_error())

    def _wrap_constructor(window_type):
        original = window_type.__init__

        def init_background_window(self, *args, **kwargs):
            original(self, *args, **kwargs)
            _send_to_background(self)
            self.bind(
                "<Map>",
                lambda event, window=self: (
                    _send_to_background(window) if event.widget is window else None
                ),
                add="+",
            )

        window_type.__init__ = init_background_window

    _wrap_constructor(tk.Tk)
    _wrap_constructor(tk.Toplevel)

    _original_deiconify = tk.Wm.wm_deiconify

    def _deiconify_in_background(self, *args):
        result = _original_deiconify(self, *args)
        _send_to_background(self)
        return result

    tk.Wm.wm_deiconify = tk.Wm.deiconify = _deiconify_in_background

    _original_attributes = tk.Wm.wm_attributes

    def _background_attributes(self, *args):
        if len(args) >= 2 and args[0] == "-topmost" and bool(args[1]):
            args = (args[0], False, *args[2:])
        result = _original_attributes(self, *args)
        _send_to_background(self)
        return result

    tk.Wm.wm_attributes = tk.Wm.attributes = _background_attributes

    def _focus_without_activation(self):
        result = self.focus_set()
        _send_to_background(self.winfo_toplevel())
        return result

    tk.Misc.focus_force = _focus_without_activation
