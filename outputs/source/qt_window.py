"""Resize the VoxPad window in its fixed portrait proportions."""
from PySide6.QtCore import QObject, QPointF, QRect, QSize, Qt, QTimer, Slot

ASPECT = 978 / 1276


def portrait_size(width, height):
    width = max(1, min(width, height * ASPECT))
    return QSize(round(width), round(width / ASPECT))


class WindowGeometry(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.screen = None
        self.last_size = window.size()
        self.timer = QTimer(window)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.constrain)
        window.widthChanged.connect(lambda: self.timer.start())
        window.heightChanged.connect(lambda: self.timer.start())
        window.screenChanged.connect(self.update_limits)
        window.windowStateChanged.connect(self.restore_portrait)
        self.update_limits()

    @Slot()
    def update_limits(self):
        screen = self.window.screen()
        if self.screen is not screen:
            if self.screen is not None:
                self.screen.availableGeometryChanged.disconnect(self.update_limits)
            self.screen = screen
            screen.availableGeometryChanged.connect(self.update_limits)
        available = self.screen.availableGeometry()
        maximum = portrait_size(available.width() - 24, available.height() - 24)
        minimum = portrait_size(min(300, maximum.width()), maximum.height())
        self.window.setMinimumSize(minimum)
        self.window.setMaximumSize(maximum)
        self.constrain()

    def sized(self, width):
        width = max(self.window.minimumWidth(), min(round(width), self.window.maximumWidth()))
        height = max(self.window.minimumHeight(), min(round(width / ASPECT), self.window.maximumHeight()))
        return QSize(width, height)

    def constrain(self):
        if self.window.windowState() != Qt.WindowNoState:
            return
        size = self.window.size()
        if (abs(size.height() - size.width() / ASPECT) <= 1 and
                self.window.minimumWidth() <= size.width() <= self.window.maximumWidth() and
                self.window.minimumHeight() <= size.height() <= self.window.maximumHeight()):
            self.last_size = size
            return
        self.last_size = self.sized(min(size.width(), size.height() * ASPECT))
        if size != self.last_size:
            self.window.resize(self.last_size)

    def restore_portrait(self, state):
        if state == Qt.WindowMaximized:
            self.window.showNormal()
            self.window.resize(self.last_size)

    @Slot(int, QRect, QPointF)
    def resize_from_drag(self, edge_mask, start, delta):
        edges = Qt.Edge(edge_mask)
        left = bool(edges & Qt.LeftEdge)
        top = bool(edges & Qt.TopEdge)
        horizontal = edges & (Qt.LeftEdge | Qt.RightEdge)
        vertical = edges & (Qt.TopEdge | Qt.BottomEdge)
        dx = -delta.x() if left else delta.x()
        dy = -delta.y() if top else delta.y()
        if horizontal and vertical:
            # Project onto the diagonal so the same pointer position always gives the same size.
            width_change = ASPECT * (ASPECT * dx + dy) / (1 + ASPECT ** 2)
        else:
            width_change = dx if horizontal else dy * ASPECT
        size = self.sized(start.width() + width_change)
        if (size.width() == start.width() and
                self.window.minimumHeight() <= start.height() <= self.window.maximumHeight()):
            size.setHeight(start.height())
        x = start.x() + (start.width() - size.width() if left else 0)
        y = start.y() + (start.height() - size.height() if top else 0)
        geometry = QRect(x, y, size.width(), size.height())
        if geometry != self.window.geometry():
            self.window.setGeometry(geometry)
