from __future__ import annotations

import math
import time

import cv2
import numpy as np


class CameraModule:
    def __init__(self, config: dict) -> None:
        self.index = int(config.get("index", 0))
        self.width = int(config.get("width", 640))
        self.height = int(config.get("height", 360))
        self.mock = bool(config.get("mock", True))
        self.capture: cv2.VideoCapture | None = None
        self.connected = False
        self.frame_count = 0
        self.last_error = "Not opened"
        self.last_open_attempt = 0.0
        self.reopen_interval = 2.0

    def open(self) -> bool:
        if self.capture is not None and self.capture.isOpened():
            return True
        now = time.monotonic()
        if now - self.last_open_attempt < self.reopen_interval:
            return False
        self.last_open_attempt = now
        cap = cv2.VideoCapture(self.index)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.capture = cap
            self.connected = True
            self.last_error = ""
            return True
        cap.release()
        self.connected = False
        self.last_error = f"Camera index {self.index} unavailable"
        return False

    def read(self) -> np.ndarray:
        if self.capture is None:
            self.open()
        if self.capture is not None:
            ok, frame = self.capture.read()
            if ok:
                self.connected = True
                return cv2.resize(frame, (self.width, self.height))
            self.connected = False

        if self.mock:
            return self._mock_frame()
        return np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def _mock_frame(self) -> np.ndarray:
        self.frame_count += 1
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        grid_color = (45, 65, 80)
        for x in range(0, self.width, 40):
            cv2.line(frame, (x, 0), (x, self.height), grid_color, 1)
        for y in range(0, self.height, 40):
            cv2.line(frame, (0, y), (self.width, y), grid_color, 1)
        cx = int(self.width * (0.5 + 0.35 * math.sin(self.frame_count * 0.045)))
        cy = int(self.height * (0.5 + 0.25 * math.cos(self.frame_count * 0.035)))
        cv2.circle(frame, (cx, cy), 34, (0, 180, 255), -1)
        cv2.putText(frame, "MOCK CAMERA", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (230, 240, 245), 2)
        return frame

    def close(self) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None
