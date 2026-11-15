"""On-screen copy of the 32x32 LED board, so you can work without the hardware."""
import cv2
import numpy as np

import config
from frames import render

WINDOW = "LED board (simulated)"


def scale_up(rgb):
    """32x32 RGB picture -> big BGR picture with grid lines, ready for cv2.imshow."""
    s = config.SIM_SCALE
    big = np.repeat(np.repeat(rgb, s, axis=0), s, axis=1)
    big[::s, :] = 20            # grid lines so individual LEDs are visible
    big[:, ::s] = 20
    return cv2.cvtColor(big, cv2.COLOR_RGB2BGR)


def board_image(gesture, x, y, dist_cm):
    return scale_up(render(gesture, x, y, dist_cm))


def show(gesture, x, y, dist_cm):
    cv2.imshow(WINDOW, board_image(gesture, x, y, dist_cm))


def show_image(rgb):
    """Show any 32x32 RGB picture on the board window (used by drawing mode)."""
    cv2.imshow(WINDOW, scale_up(rgb))
