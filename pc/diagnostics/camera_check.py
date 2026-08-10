from __future__ import annotations

import contextlib
import os
from typing import Any


def check_cameras(start_index: int = 0, end_index: int = 3) -> dict[str, Any]:
    try:
        import cv2
    except ImportError as exc:
        return {
            "ok": False,
            "error": f"OpenCVを読み込めません: {exc}",
            "cameras": [],
        }

    cameras = []
    with _suppress_native_stderr():
        for index in range(start_index, end_index + 1):
            available = False
            width = 0
            height = 0
            capture = None
            try:
                capture = cv2.VideoCapture(index)
                if capture is not None and capture.isOpened():
                    available = True
                    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            except Exception as exc:  # OpenCV backends can raise environment-specific errors.
                cameras.append({"index": index, "available": False, "width": 0, "height": 0, "error": str(exc)})
                continue
            finally:
                if capture is not None:
                    capture.release()

            cameras.append(
                {
                    "index": index,
                    "available": available,
                    "width": width,
                    "height": height,
                    "error": "",
                }
            )

    return {
        "ok": True,
        "error": "",
        "cameras": cameras,
    }


@contextlib.contextmanager
def _suppress_native_stderr():
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        stderr_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
    except OSError:
        yield
        return

    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.dup2(stderr_fd, 2)
            os.close(stderr_fd)
