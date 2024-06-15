import threading

from ok.config.Config import Config
from ok.config.InfoDict import InfoDict
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.task.ExecutorOperation import ExecutorOperation
from ok.util.Handler import Handler

logger = get_logger(__name__)


class BaseTask(ExecutorOperation):

    def __init__(self):
        super().__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.name = self.__class__.__name__
        self.description = ""
        self.feature_set = None
        self._enabled = False
        self.config = None
        self.info = InfoDict()
        self.default_config = {}
        self.config_description = {}
        self.config_type = {}
        self._paused = False
        self.lock = threading.Lock()
        self._handler = None
        self._done = False
        self.running = False

    def get_status(self):
        if self.running:
            return "Running"
        elif self.enabled:
            if self.paused:
                return "Paused"
            else:
                return "In Queue"
        else:
            return "Not Started"

    def enable(self):
        if not self._enabled:
            self._enabled = True
            self.info_clear()
        communicate.task.emit(self)
        self._done = False

    @property
    def done(self):
        return self._done

    def set_done(self):
        self._done = True
        self.disable()

    @property
    def handler(self) -> Handler:
        with self.lock:
            if self._handler is None:
                self._handler = Handler(self.executor.exit_event, __name__)
            return self._handler

    def pause(self):
        self.executor.pause(self)
        self._paused = True
        communicate.task.emit(self)
        if self.executor.is_executor_thread():
            self.sleep(1)

    def unpause(self):
        self._paused = False
        self.executor.start()
        communicate.task.emit(self)

    @property
    def paused(self):
        return self._paused

    def log_info(self, message, notify=False):
        self.logger.info(message)
        self.info_set("Log", message)
        if notify:
            self.notification(message)
        communicate.task_info.emit()

    def log_debug(self, message, notify=False):
        self.logger.debug(message)
        if notify:
            self.notification(message)

    def log_error(self, message, exception=None, notify=False):
        self.logger.error(message, exception)
        if exception is not None:
            if len(exception.args) > 0:
                message += exception.args[0]
            else:
                message += str(exception)
        self.info_set("Error", message)
        if notify:
            self.notification(message)
        communicate.task_info.emit()

    def notification(self, message, title=None, error=False):
        communicate.notification.emit(message, title, error, False)

    @property
    def enabled(self):
        return self._enabled

    def info_clear(self):
        self.info.clear()

    def info_incr(self, key, by=1):
        # If the key is in the dictionary, get its value. If not, return 0.
        value = self.info.get(key, 0)
        # Increment the value
        value += by
        # Store the incremented value back in the dictionary
        self.info[key] = value

    def info_add_to_list(self, key, item):
        value = self.info.get(key, [])
        if isinstance(item, list):
            value += item
        else:
            value.append(item)
        self.info[key] = value

    def info_set(self, key, value):
        self.info[key] = value

    def info_add(self, key, count=1):
        self.info[key] = self.info.get(key, 0) + count

    def load_config(self, folder):
        self.config = Config(self.default_config, folder, self.__class__.__name__, self.validate)

    def validate(self, key, value):
        message = self.validate_config(key, value)
        if message:
            return False, message
        else:
            return True, None

    def validate_config(self, key, value):
        pass

    def disable(self):
        self._enabled = False
        self.executor.current_task = None
        communicate.task.emit(self)

    def run(self):
        pass

    def check_trigger(self):
        return True

    def check_condition(self):
        return True

    def on_destroy(self):
        pass

    def on_create(self):
        pass

    def set_executor(self, executor):
        self.executor = executor
        self.feature_set = executor.feature_set
        self.load_config(executor.config_folder)
        self.on_create()
