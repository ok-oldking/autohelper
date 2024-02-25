from autoui.feature.Box import Box


class BaseInteraction:

    def __init__(self, capture):
        self.capture = capture

    def send_key(self, key, down_time=0.02):
        pass

    def click_relative(self, x, y):
        self.click(int(self.capture.width * x), int(self.capture.height * y))

    def click_box(self, box: Box, relative_x=0.5, relative_y=0.5):
        x, y = box.relative_with_variance(relative_x, relative_y)
        self.click(x, y)

    def click(self, x=-1, y=-1):
        pass