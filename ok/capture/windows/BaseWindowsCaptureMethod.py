# original https://github.com/dantmnf & https://github.com/hakaboom/winAuto
import ctypes.wintypes

from ok.capture.BaseCaptureMethod import BaseCaptureMethod
from ok.capture.HwndWindow import HwndWindow
from ok.logging.Logger import get_logger

PBYTE = ctypes.POINTER(ctypes.c_ubyte)
WGC_NO_BORDER_MIN_BUILD = 20348

logger = get_logger(__name__)


class BaseWindowsCaptureMethod(BaseCaptureMethod):
    _hwnd_window: HwndWindow = None

    def __init__(self, hwnd_window: HwndWindow):
        super().__init__()
        self._hwnd_window = hwnd_window

    @property
    def hwnd_window(self):
        return self._hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self._hwnd_window = hwnd_window

    def connected(self):
        return self.hwnd_window is not None and self.hwnd_window.exists

    def get_abs_cords(self, x, y):
        return self.hwnd_window.get_abs_cords(x, y)

    def clickable(self):
        return self.hwnd_window is not None and self.hwnd_window.visible
