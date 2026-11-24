"""High-DPI image canvas with pointer-anchored zoom."""

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QContextMenuEvent, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class ImageCanvas(QWidget):
    zoom_changed = Signal(float, bool)
    file_menu_requested = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("图片画布")
        self._image = QImage()
        self._fixed_zoom = None
        self._offset = QPointF()
        self._drag_point = None
        self._checker = QPixmap(16, 16)
        self._checker.fill(QColor("#39393b"))
        painter = QPainter(self._checker)
        painter.fillRect(0, 0, 8, 8, QColor("#444446"))
        painter.fillRect(8, 8, 8, 8, QColor("#444446"))
        painter.end()

    def set_image(self, image):
        self._image = image
        self.fit()

    def set_frame(self, image):
        self._image = image
        self.update()

    def fit_zoom(self):
        if self._image.isNull():
            return 1.0
        margin = min(32, self.width() * 0.045, self.height() * 0.05)
        dpr = self.devicePixelRatioF()
        return min(
            1.0,
            max(1, self.width() - margin * 2) * dpr / self._image.width(),
            max(1, self.height() - margin * 2) * dpr / self._image.height(),
        )

    def zoom(self):
        return self._fixed_zoom if self._fixed_zoom is not None else self.fit_zoom()

    def fit(self):
        self._fixed_zoom = None
        self._offset = QPointF()
        self._drag_point = None
        self._refresh()

    def set_zoom(self, value, anchor=None):
        if self._image.isNull():
            return
        value = max(min(0.025, self.fit_zoom()), min(32.0, value))
        center = QRectF(self.rect()).center()
        focus = anchor if anchor is not None else center
        ratio = value / self.zoom()
        self._offset = focus - center - (focus - center - self._offset) * ratio
        self._fixed_zoom = value
        self._refresh()

    def zoom_by(self, factor, anchor=None):
        self.set_zoom(self.zoom() * factor, anchor)

    def _bounds(self):
        scale = self.zoom() / self.devicePixelRatioF()
        return QPointF(
            max(0.0, (self._image.width() * scale - self.width()) / 2),
            max(0.0, (self._image.height() * scale - self.height()) / 2),
        )

    def _clamp_offset(self):
        bounds = self._bounds()
        self._offset.setX(max(-bounds.x(), min(bounds.x(), self._offset.x())))
        self._offset.setY(max(-bounds.y(), min(bounds.y(), self._offset.y())))

    def _refresh(self):
        self._clamp_offset()
        if self._bounds().isNull():
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.ClosedHandCursor if self._drag_point is not None
                           else Qt.CursorShape.OpenHandCursor)
        self.zoom_changed.emit(self.zoom(), self._fixed_zoom is None)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _image_rect(self):
        scale = self.zoom() / self.devicePixelRatioF()
        target = QRectF(0, 0, self._image.width() * scale, self._image.height() * scale)
        target.moveCenter(QRectF(self.rect()).center() + self._offset)
        return target

    def contextMenuEvent(self, event):
        visible = self._image_rect().intersected(QRectF(self.rect()))
        if event.reason() == QContextMenuEvent.Reason.Keyboard and not visible.isEmpty():
            position = self.mapToGlobal(visible.center().toPoint())
        elif visible.contains(event.pos()):
            position = event.globalPos()
        else:
            return super().contextMenuEvent(event)
        event.accept()
        self.file_menu_requested.emit(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#18191b"))
        if self._image.isNull():
            return
        target = self._image_rect()
        visible = target.intersected(QRectF(event.rect()))
        if visible.isEmpty():
            return
        if self._image.hasAlphaChannel():
            painter.setBrushOrigin(target.topLeft())
            painter.fillRect(visible, QBrush(self._checker))
        scale = self.zoom() / self.devicePixelRatioF()
        source = QRectF(
            (visible.x() - target.x()) / scale, (visible.y() - target.y()) / scale,
            visible.width() / scale, visible.height() / scale,
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.zoom() < 4)
        painter.drawImage(visible, self._image, source)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y() * 2
        if delta and not self._image.isNull():
            self.zoom_by(1.2 ** max(-10.0, min(10.0, delta / 120)), event.position())
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._bounds().isNull():
            self._drag_point = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_point is None:
            return super().mouseMoveEvent(event)
        self._offset += event.position() - self._drag_point
        self._drag_point = event.position()
        self._clamp_offset()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_point = None
            self._refresh()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(event)
        if self._fixed_zoom is None:
            self.set_zoom(1.0, event.position())
        else:
            self.fit()
        event.accept()
