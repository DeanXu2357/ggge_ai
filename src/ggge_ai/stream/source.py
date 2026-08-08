"""scrcpy --v4l2-sink 串流溝通層：行程管理、v4l2 讀取、最新幀維護與重連。"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np


class StreamStarved(RuntimeError):
    """串流餓死：重建幾輪之後仍拿不到新鮮幀。"""


def _spawn_scrcpy(serial: str | None, video_device: str) -> Any:
    # 坑：--no-window 不可省。GNOME session 下 scrcpy 開視窗的串流視窗會閃退，
    # 連帶把 v4l2 sink 一起帶走。
    command = [
        "scrcpy",
        f"--v4l2-sink={video_device}",
        "--no-audio",
        "--no-control",
        "--no-window",
    ]
    if serial:
        command += ["-s", serial]
    env = dict(os.environ, ADB_LIBUSB="1")
    return subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _open_v4l2(video_device: str) -> Any:
    return cv2.VideoCapture(video_device, cv2.CAP_V4L2)


@dataclass
class StreamSource:
    """scrcpy 子程序＋v4l2 讀取端的生命週期。

    坑：/dev/videoN 同時只准這支程式的 VideoCapture 讀，桌面攝影機程式一開就搶走。
    """

    serial: str | None = None
    video_device: str = "/dev/video0"
    stale_after_s: float = 3.0
    reconnect_tries: int = 3
    first_frame_timeout_s: float = 10.0
    capture_ready_timeout_s: float = 5.0
    capture_poll_s: float = 0.2
    process_factory: Callable[[str | None, str], Any] = _spawn_scrcpy
    capture_factory: Callable[[str], Any] = _open_v4l2
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _process: Any = field(default=None, init=False)
    _capture: Any = field(default=None, init=False)
    _reader: threading.Thread | None = field(default=None, init=False)
    _stopping: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _frame: np.ndarray | None = field(default=None, init=False)
    _stamp: float = field(default=0.0, init=False)

    def start(self) -> None:
        self._open()
        if not self._await_first_frame():
            self._restart_until_fresh()

    def latest(self) -> np.ndarray:
        # 坑：reader 每幀存的是新陣列（copy），不就地覆寫，所以這裡回傳參考即可，
        # 呼叫端手上的幀不會被下一幀改掉。
        frame = self._fresh()
        if frame is not None:
            return frame
        return self._restart_until_fresh()

    def stop(self) -> None:
        self._stopping.set()
        reader, self._reader = self._reader, None
        if reader is not None:
            reader.join(timeout=2.0)
        capture, self._capture = self._capture, None
        if capture is not None:
            capture.release()
        process, self._process = self._process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except Exception:
                process.kill()

    def _open(self) -> None:
        self._stopping = threading.Event()
        with self._lock:
            self._frame = None
            self._stamp = 0.0
        self._process = self.process_factory(self.serial, self.video_device)
        self._capture = self._open_capture()
        if self._capture is None:
            return
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _open_capture(self) -> Any:
        # 坑：scrcpy 的 v4l2 sink 大約 0.84s 才就緒，太早開的 VideoCapture 會一直
        # isOpened()==False 且 read() 永遠失敗，必須丟掉重開而不是留著空轉。
        deadline = self.clock() + self.capture_ready_timeout_s
        while True:
            capture = self.capture_factory(self.video_device)
            if capture is not None and capture.isOpened():
                return capture
            if capture is not None:
                capture.release()
            if self.clock() >= deadline:
                return None
            self.sleep(self.capture_poll_s)

    def _pump(self) -> None:
        capture, stopping = self._capture, self._stopping
        while not stopping.is_set():
            ok, frame = capture.read()
            if not ok or frame is None:
                self.sleep(0.05)
                continue
            with self._lock:
                self._frame = frame.copy()
                self._stamp = self.clock()

    def _fresh(self) -> np.ndarray | None:
        with self._lock:
            frame, stamp = self._frame, self._stamp
        if frame is None or self.clock() - stamp > self.stale_after_s:
            return None
        return frame

    def _await_first_frame(self) -> bool:
        deadline = self.clock() + self.first_frame_timeout_s
        while self.clock() < deadline:
            if self._fresh() is not None:
                return True
            self.sleep(0.05)
        return self._fresh() is not None

    def _restart_until_fresh(self) -> np.ndarray:
        for _ in range(self.reconnect_tries):
            self.stop()
            self._open()
            if self._await_first_frame():
                frame = self._fresh()
                if frame is not None:
                    return frame
        self.stop()
        raise StreamStarved(
            f"{self.video_device} 連 {self.reconnect_tries} 次重建都沒有新鮮幀"
        )
