import threading
import time
import traceback

from ok.capture.adb.DeviceManager import DeviceManager
from ok.gui.Communicate import communicate
from ok.logging.Logger import get_logger
from ok.scene.Scene import Scene
from ok.stats.StreamStats import StreamStats

logger = get_logger(__name__)


class TaskDisabledException(Exception):
    pass


class TaskExecutor:
    current_scene: Scene | None = None
    last_scene: Scene | None = None
    frame_stats = StreamStats()
    _frame = None
    paused = True
    ocr = None
    pause_start = time.time()
    pause_end_time = time.time()

    def __init__(self, device_manager: DeviceManager,
                 wait_until_timeout=10, wait_until_before_delay=1, wait_until_check_delay=1,
                 exit_event=threading.Event(), tasks=[], scenes=[], feature_set=None, ocr=None, config_folder=None):
        self.device_manager = device_manager
        self.feature_set = feature_set
        self.wait_until_check_delay = wait_until_check_delay
        self.wait_until_before_delay = wait_until_before_delay
        self.wait_scene_timeout = wait_until_timeout
        self.exit_event = exit_event
        self.ocr = ocr
        self.current_task = None
        self.tasks = tasks
        self.scenes = scenes
        self.config_folder = config_folder or "config"
        for scene in self.scenes:
            scene.executor = self
            scene.feature_set = self.feature_set
        for task in self.tasks:
            task.executor = self
            task.feature_set = self.feature_set
            task.load_config(self.config_folder)
        self.thread = threading.Thread(target=self.execute, name="TaskExecutor")
        self.thread.start()

    @property
    def interaction(self):
        return self.device_manager.interaction

    @property
    def method(self):
        return self.device_manager.capture_method

    def next_frame(self):
        self.reset_scene()
        start = time.time()
        while not self.exit_event.is_set():
            if self.method and self.interaction.should_capture():
                self._frame = self.method.get_frame()
                if self._frame is not None:
                    height, width = self._frame.shape[:2]
                    if height <= 0 or width <= 0:
                        logger.warning(f"captured wrong size frame: {width}x{height}")
                        self._frame = None
                    communicate.frame.emit(self._frame)
                    return self._frame
            self.sleep(0.001)
            if time.time() - start > self.wait_scene_timeout:
                return None

    @property
    def frame(self):
        if self._frame is None:
            return self.next_frame()
        else:
            return self._frame

    def sleep(self, timeout):
        """
        Sleeps for the specified timeout, checking for an exit event every 100ms, with adjustments to prevent oversleeping.

        :param timeout: The total time to sleep in seconds.
        """
        self.frame_stats.add_sleep(timeout)
        self.pause_end_time = time.time() + timeout
        while True:
            if self.exit_event.is_set():
                logger.info("Exit event set. Exiting early.")
                return
            if self.current_task and not self.current_task.enabled:
                raise TaskDisabledException()
            if not (self.paused or not self.interaction.should_capture()):
                to_sleep = self.pause_end_time - time.time()
                if to_sleep <= 0:
                    return
            time.sleep(0.001)

    def pause(self):
        self.paused = True
        self.pause_start = time.time()
        communicate.executor_paused.emit(self.paused)
        communicate.tasks.emit()

    def start(self):
        can_run = False
        for task in self.tasks:
            if task.can_run():
                can_run = True
                break
        if not can_run:
            return False
        self.pause_end_time += self.pause_start - time.time()
        self.paused = False
        communicate.executor_paused.emit(self.paused)
        communicate.tasks.emit()
        return True

    def wait_scene(self, scene_type, time_out, pre_action, post_action):
        return self.wait_condition(lambda: self.detect_scene(scene_type), time_out, pre_action, post_action)

    def wait_condition(self, condition, time_out, pre_action, post_action):
        self.sleep(self.wait_until_before_delay)
        start = time.time()
        if time_out == 0:
            time_out = self.wait_scene_timeout
        while not self.exit_event.is_set():
            self.reset_scene()
            if pre_action is not None:
                pre_action()
            self._frame = self.next_frame()
            if self._frame is not None:
                result = condition()
                self.add_frame_stats()
                result_str = list_or_obj_to_str(result)
                if result:
                    logger.debug(f"found result {result_str}")
                    self.sleep(self.wait_until_check_delay)
                    return result
            if post_action is not None:
                post_action()
            if time.time() - start > time_out:
                logger.info(f"wait_until timeout {condition} {time_out} seconds")
                break
            self.sleep(0.01)
        return None

    def reset_scene(self):
        self._frame = None
        self.last_scene = self.current_scene
        self.current_scene = None

    def execute(self):
        logger.info(f"start execute")
        while not self.exit_event.is_set():
            self._frame = self.next_frame()
            start = time.time()
            if self._frame is not None:
                self.detect_scene()
                task_executed = 0
                for index, task in enumerate(self.tasks):
                    if task.done or not task.enabled:
                        continue
                    self.current_task = task
                    task.running = True
                    task.last_execute_time = start
                    try:
                        task.run_frame()
                    except TaskDisabledException:
                        logger.info(f"{task.name} is disabled, breaking")
                    except Exception as e:
                        traceback.print_exc()
                        stack_trace_str = traceback.format_exc()
                        logger.error(f"{task.name} exception: {e}, traceback: {stack_trace_str}")
                        task.error_count += 1
                    self.current_task = None
                    task.running = False
                    processing_time = time.time() - start
                    task_executed += 1
                    if processing_time > 0.5:
                        logger.debug(
                            f"{task.__class__.__name__} taking too long get new frame {processing_time} {task_executed} {len(self.tasks)}")
                        self.next_frame()
                        start = time.time()

                # if task_executed == 0:
                #     self.pause()
                self.add_frame_stats()
                self.sleep(0.001)

    def add_frame_stats(self):
        self.frame_stats.add_frame()
        mean = self.frame_stats.mean()
        if mean > 0:
            communicate.frame_time.emit(mean)
            communicate.fps.emit(round(1000 / mean))
            scene = "None"
            if self.current_scene is not None:
                scene = self.current_scene.name or self.current_scene.__class__.__name__
            communicate.scene.emit(scene)

    def latest_scene(self):
        return self.current_scene or self.last_scene

    def detect_scene(self, scene_type=None):
        latest_scene = self.latest_scene()
        if latest_scene is not None:
            # detect the last scene optimistically
            if latest_scene.detect(self._frame):
                self.current_scene = latest_scene
                return latest_scene
        for scene in self.scenes:
            if scene_type is not None and not isinstance(scene, scene_type):
                continue
            if scene != latest_scene:
                if scene.detect(self._frame):
                    self.current_scene = scene
                    logger.debug(f"TaskExecutor: scene changed {scene.__class__.__name__}")
                    return scene
        if self.current_scene is not None:
            logger.debug(f"TaskExecutor: scene changed to None")
            self.current_scene = None
        return self.current_scene

    def stop(self):
        self.exit_event.set()

    def wait_until_done(self):
        self.thread.join()


def list_or_obj_to_str(val):
    if val is not None:
        if isinstance(val, list):
            return ', '.join(str(obj) for obj in val)
        else:
            return str(val)
    else:
        return None