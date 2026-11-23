"""Exercise the viewer through Qt key, wheel and pointer events."""

import os
from time import monotonic, sleep

from PIL import Image
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMovie, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from hifine.viewer import MainWindow


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(app):
    widget = MainWindow()
    widget.show()
    widget.activateWindow()
    app.processEvents()
    yield widget
    widget._pool.waitForDone()
    widget.close()


def finish_read(app, window):
    deadline = monotonic() + 10
    while window._reader is not None:
        assert monotonic() < deadline, "timed out waiting for the viewer"
        app.processEvents()
        sleep(0.005)


def test_keyboard_navigation_details_and_bad_image(app, window, tmp_path):
    first, second, bad = (tmp_path / name for name in ("图1.png", "图2.png", "图10.jpg"))
    Image.new("RGB", (13, 7), "red").save(first)
    Image.new("RGBA", (7, 4), (10, 25, 45, 125)).save(second)
    bad.write_bytes(b"broken")
    window.open_file(first)
    finish_read(app, window)
    assert window.position.text() == "1 / 3"
    assert not window.prev_button.isEnabled()
    assert window.canvas._image.pixelColor(0, 0).red() == 255
    QTest.keyClick(window, Qt.Key.Key_Tab)
    assert not window.info_panel.isVisible()
    QTest.keyClick(window, Qt.Key.Key_Tab)
    assert window.info_panel.isVisible()
    QTest.keyClick(window, Qt.Key.Key_Right)
    QTest.keyClick(window, Qt.Key.Key_Right)
    finish_read(app, window)
    assert window.current_path == bad
    assert window.state_title.text() == "无法打开这张图片"
    assert not window.next_button.isEnabled()
    QTest.keyClick(window, Qt.Key.Key_Left)
    finish_read(app, window)
    assert window.current_path == second
    assert window.canvas._image.pixelColor(0, 0).alpha() == 125
    assert window.position.text() == "2 / 3"
    QTest.keyClick(window, Qt.Key.Key_F11)
    assert window.isFullScreen()
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.isFullScreen()


def test_pointer_anchored_zoom_and_drag(app, window):
    canvas = window.canvas
    window.stage.setCurrentWidget(canvas)
    image = QImage(3200, 2400, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    canvas.set_image(image)
    QTest.keyClick(window, Qt.Key.Key_1)
    assert canvas.zoom() == 1
    center = QPointF(canvas.width() / 2, canvas.height() / 2)
    anchor = center + QPointF(40, 20)
    wheel = QWheelEvent(anchor, canvas.mapToGlobal(anchor), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(canvas, wheel)
    assert canvas.zoom() == pytest.approx(1.2)
    assert canvas._offset.x() == pytest.approx(-8)
    assert canvas._offset.y() == pytest.approx(-4)
    start = QPoint(100, 110)
    end = QPoint(150, 140)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert canvas._offset == QPointF(42, 26)
    QTest.keyClick(window, Qt.Key.Key_0)
    assert canvas.zoom() == canvas.fit_zoom()
    assert canvas._offset.isNull()


@pytest.mark.parametrize("extension", ["gif", "webp"])
def test_animated_playback_keeps_zoom(app, window, tmp_path, extension):
    path = tmp_path / f"01.{extension}"
    frames = [Image.new("RGB", (320, 240), color) for color in ("red", "lime")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=140, loop=0,
                   lossless=True)
    frames[0].save(tmp_path / "02.png")
    window.open_file(path)
    finish_read(app, window)
    assert window._movie.state() == QMovie.MovieState.Running
    assert window.play_button.isVisible()
    window.canvas.set_zoom(6.0, QPointF(80, 60))
    offset = QPointF(window.canvas._offset)
    deadline = monotonic() + 3
    while window.canvas._image.pixelColor(0, 0).green() < 200:
        assert monotonic() < deadline, "the second frame never reached the canvas"
        app.processEvents()
        sleep(0.005)
    assert window.canvas.zoom() == 6.0
    assert window.canvas._offset == offset
    QTest.keyClick(window, Qt.Key.Key_Space)
    assert window._movie.state() == QMovie.MovieState.Paused
    QTest.qWait(200)
    assert window.canvas._image.pixelColor(0, 0).green() > 200
    window.play_button.click()
    assert window._movie.state() == QMovie.MovieState.Running
    QTest.keyClick(window, Qt.Key.Key_Right)
    finish_read(app, window)
    assert window._movie is None
    assert not window.play_button.isVisible()
