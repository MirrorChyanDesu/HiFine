"""Exercise the Shell binding without invoking desktop applications on the test machine."""

from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image
import pytest
from PySide6.QtCore import QPoint


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows Shell")
def test_shell_menu_command_and_cancel(monkeypatch, tmp_path):
    import ctypes as c
    from ctypes import wintypes as w
    from hifine import windows_menu as shell

    path = tmp_path / "照片 01.png"
    Image.new("RGB", (5, 7)).save(path)
    # Qt's offscreen plugin has no HWND. A hidden Windows control provides a
    # real owner for Shell extensions and does not take focus from the desktop.
    create = shell._api(shell._user, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR,
                        w.DWORD, c.c_int, c.c_int, c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
    destroy = shell._api(shell._user, "DestroyWindow", w.BOOL, w.HWND)
    count = shell._api(shell._user, "GetMenuItemCount", c.c_int, w.HMENU)
    item_id = shell._api(shell._user, "GetMenuItemID", w.UINT, w.HMENU, c.c_int)
    hwnd = create(0, "STATIC", "HiFine test", 0x80000000, 10, 20, 100, 100, None, None, None, None)
    assert hwnd
    window = SimpleNamespace(winId=lambda: hwnd, devicePixelRatioF=lambda: 1.0, mapFromGlobal=lambda p: p)
    verbs = {}
    invoked = []
    populate = shell._populate

    def read_menu(context, menu, index, first, last, flags):
        # The test replaces TrackPopupMenuEx and its message loop. Finish
        # submenu construction before destroying the test menu and COM apartment.
        result = populate(context, menu, index, first, last, flags | 0x1000)  # CMF_SYNCCASCADEMENU
        for row in range(count(menu)):
            command = item_id(menu, row)
            if first <= command <= last:
                verb = c.create_unicode_buffer(256)
                if shell._get_verb(context, command - first, 4, None, verb, len(verb)) == 0:
                    verbs[verb.value.lower()] = command
        return result

    def invoke(context, info_ptr):
        info = c.cast(info_ptr, c.POINTER(shell._InvokeInfo)).contents
        invoked.append((info.lpVerb, info.lpVerbW, info.hwnd, Path(info.lpDirectoryW)))

    monkeypatch.setattr(shell, "_populate", read_menu)
    monkeypatch.setattr(shell, "_track", lambda *args: verbs["properties"])
    monkeypatch.setattr(shell, "_invoke", invoke)
    try:
        assert shell.show_shell_menu(window, path, QPoint(2, 3))
        assert {"properties", "rename"} <= verbs.keys()
        offset = verbs["properties"] - 1
        assert invoked == [(offset, offset, hwnd, path.parent)]
        monkeypatch.setattr(shell, "_track", lambda *args: 0)
        assert not shell.show_shell_menu(window, path, QPoint(2, 3))
        assert len(invoked) == 1
    finally:
        destroy(hwnd)
