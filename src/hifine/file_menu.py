"""Show file actions for the image under the pointer."""

import sys

from PySide6.QtCore import QProcess, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu, QMessageBox


def _reveal_file(window, path):
    folder = QUrl.fromLocalFile(str(path.parent))
    if sys.platform == "darwin":
        started, _ = QProcess.startDetached("/usr/bin/open", ["-R", str(path)])
        if not started:
            QDesktopServices.openUrl(folder)
        return

    from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher

    service = "org.freedesktop.FileManager1"
    message = QDBusMessage.createMethodCall(service, "/org/freedesktop/FileManager1", service, "ShowItems")
    message.setArguments([[path.as_uri()], ""])
    call = QDBusConnection.sessionBus().asyncCall(message)
    watcher = QDBusPendingCallWatcher(call, window)

    def finished():
        if watcher.isError():
            QDesktopServices.openUrl(folder)
        watcher.deleteLater()

    if watcher.isFinished():
        finished()
    else:
        watcher.finished.connect(finished)


def show_file_menu(window, path, global_pos):
    if path is None or not path.is_file():
        return False
    if sys.platform == "win32":
        from .windows_menu import show_shell_menu

        try:
            return show_shell_menu(window, path, global_pos)
        except OSError as exc:
            if exc.winerror not in (-2147023673, -2147467260):  # ERROR_CANCELLED, E_ABORT
                QMessageBox.warning(window, "文件操作", f"{path.name}\n{exc}")
            return False

    menu = QMenu(window)
    reveal = menu.addAction("在 Finder 中显示" if sys.platform == "darwin" else "在文件管理器中显示")
    selected = menu.exec(global_pos) is reveal
    menu.deleteLater()
    if selected:
        _reveal_file(window, path)
    return selected
