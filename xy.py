from __future__ import annotations
import os
import sys
import ctypes
import platform
from PySide6.QtCore import Qt, QObject, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout
)
from pynput import mouse

if platform.system() == "Windows":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

class ClickBridge(QObject):
    middle_clicked = Signal(int, int)
    left_clicked = Signal(int, int)
    mouse_moved = Signal(int, int)

class Overlay(QWidget):
    def __init__(self, geometry: QRect):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(geometry)

        self.point1 = None
        self.point2 = None
        self.finalized = False

    def set_points(self, p1: QPoint, p2: QPoint, finalized: bool):
        self.point1 = p1
        self.point2 = p2
        self.finalized = finalized
        self.update()

    def clear(self):
        self.point1 = None
        self.point2 = None
        self.finalized = False
        self.update()

    def paintEvent(self, event):
        if not (self.point1 and self.point2):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRect(self.point1, self.point2).normalized()
        local_rect = rect.translated(-self.geometry().topLeft())

        painter.setBrush(QColor(0, 170, 255, 60))
        pen = QPen(QColor(0, 170, 255, 220), 2)
        if not self.finalized:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(local_rect)


class InfoPanel(QWidget):
    _COORD_PLACEHOLDER = "  --,   --"

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            QWidget      { background: rgba(20, 20, 20, 220); }
            QLabel       { color: white; font-family: Consolas, monospace;
                           font-size: 12px; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.info_label = QLabel()
        self.info_label.setTextFormat(Qt.RichText)
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setCursor(Qt.IBeamCursor)
        layout.addWidget(self.info_label)

        self.move(0, 0)

        self.update_points(None, None)
        self.adjustSize()

    @staticmethod
    def _coord_text(point: QPoint | None) -> str:
        if point is None:
            return InfoPanel._COORD_PLACEHOLDER
        return f"{point.x():>5}, {point.y():>5}"

    def update_points(self, point1: QPoint | None, point2: QPoint | None):
        if point1 and point2:
            rect = QRect(point1, point2).normalized()
            box_text = f"{rect.width():>4} x {rect.height():>4} px"
        else:
            box_text = "  -- x   -- px"

        html = (
            '<span style="color:#7fd4ff; font-weight:bold;">'
            ' Origin (0,0) = top-left corner<br>'
            ' NATIVE physical pixels'
            '</span><br>'
            f' Point 1: ({self._coord_text(point1)})<br>'
            f' Point 2: ({self._coord_text(point2)})<br>'
            f' Box:      {box_text}'
        )
        self.info_label.setText(html)
        self.adjustSize()


class SelectorController(QObject):
    def __init__(self):
        super().__init__()

        screens = QGuiApplication.screens()
        virtual_rect = QRect()
        for s in screens:
            virtual_rect = virtual_rect.united(s.geometry())

        self.overlay = Overlay(virtual_rect)
        self.info = InfoPanel()
        self.overlay.show()
        self.info.show()
        self.info_rect = self.info.geometry()
        self.point1 = None
        self.point2 = None
        self.bridge = ClickBridge()
        self.bridge.middle_clicked.connect(self.handle_middle_click)
        self.bridge.left_clicked.connect(self.handle_left_click)
        self.bridge.mouse_moved.connect(self.handle_move)
        self.listener = mouse.Listener(
            on_click=self._on_click, on_move=self._on_move
        )
        self.listener.start()

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return

        if self.info_rect.contains(QPoint(x, y)):
            return
        if button == mouse.Button.middle:
            self.bridge.middle_clicked.emit(int(x), int(y))
        elif button == mouse.Button.left:
            self.bridge.left_clicked.emit(int(x), int(y))

    def _on_move(self, x, y):
        self.bridge.mouse_moved.emit(int(x), int(y))

    def handle_middle_click(self, x, y):
        if self.point1 is None:
            self.point1 = QPoint(x, y)
            self.info.update_points(self.point1, None)
        elif self.point2 is None:
            self.point2 = QPoint(x, y)
            self.overlay.set_points(self.point1, self.point2, finalized=True)
            self.info.update_points(self.point1, self.point2)
        else:
            self.point1 = QPoint(x, y)
            self.point2 = None
            self.overlay.clear()
            self.info.update_points(self.point1, None)

    def handle_move(self, x, y):
        if self.point1 is not None and self.point2 is None:
            cursor = QPoint(x, y)
            self.overlay.set_points(self.point1, cursor, finalized=False)
            self.info.update_points(self.point1, cursor)

    def handle_left_click(self, x, y):
        self.point1 = None
        self.point2 = None
        self.overlay.clear()
        self.info.update_points(None, None)

    def stop(self):
        self.listener.stop()

def main():
    app = QApplication(sys.argv)
    controller = SelectorController()
    app.aboutToQuit.connect(controller.stop)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
