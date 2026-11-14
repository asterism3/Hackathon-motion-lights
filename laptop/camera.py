"""Opens the webcam reliably, especially on Windows.

Windows has two camera drivers in OpenCV. The default one (Media Foundation, "MSMF") is
slow to start and often fails with "can't grab frame". DirectShow usually just works,
so on Windows we try DirectShow first, then MSMF, and keep whichever delivers a picture.
Import this module before cv2 is used anywhere, so the setting below takes effect.
"""
import os
import sys
import time

# Stops MSMF's slow (and failure-prone) hardware start-up if we do end up using it.
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2  # noqa: E402

import config  # noqa: E402


def open_camera(index=config.CAMERA_INDEX):
    """Returns an opened cv2.VideoCapture that has delivered at least one frame, or None."""
    if sys.platform == "win32":
        backends = [("DirectShow", cv2.CAP_DSHOW), ("Media Foundation", cv2.CAP_MSMF)]
    else:
        backends = [("default", cv2.CAP_ANY)]
    for name, backend in backends:
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            ok, _ = read_frame(cap, retries=20)   # some cameras open but never send a picture
            if ok:
                print(f"Camera {index} opened ({name})")
                return cap
            print(f"Camera {index} opened with {name} but sent no picture; trying next driver...")
        cap.release()
    return None


def read_frame(cap, retries=30):
    """Like cap.read(), but tolerates a few dropped frames before giving up."""
    for _ in range(retries):
        ok, frame = cap.read()
        if ok and frame is not None:
            return True, frame
        time.sleep(0.03)
    return False, None


CAMERA_HELP = """Could not get a picture from camera {index}. Check:
  - the camera privacy switch / key (often F10 or a key with a crossed-out camera) is ON
  - no other app is using the camera: Teams, Zoom, the Camera app, a browser tab,
    or another copy of main.py / record_asl.py still running in another window
  - Settings > Privacy & security > Camera: 'Let desktop apps access your camera' is on
  - or try another camera number, e.g. --camera {other}"""


def camera_help(index):
    return CAMERA_HELP.format(index=index, other=0 if index else 1)
