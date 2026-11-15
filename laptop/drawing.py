"""Drawing mode: draw on the 32x32 board by moving a finger in the air.

Pure logic: no camera, no serial, no windows. main.py feeds it one gesture + position
per camera frame, and it keeps the picture. That makes it easy to test (see selftest.py).

The ideas, in order:
  canvas      a 32x32 grid of colours that remembers everything drawn so far
  cursor      where the fingertip is right now (shown as a blinking dot)
  pen down    the "draw" gesture is held: moving the cursor leaves a line
  pen up      any other gesture: the cursor moves but draws nothing
  actions     what each gesture does, set in config.DRAW_ACTIONS

update() also returns the list of changes it made, e.g. [("P", 12, 20, (255, 0, 0))].
Later, sending exactly those changes to the ESP32 is all the panel needs.
"""
import numpy as np

import config


def line_points(x0, y0, x1, y1):
    """Every grid point on the straight line from (x0, y0) to (x1, y1), both ends included
    (Bresenham's line algorithm). Used so a fast-moving finger leaves no gaps."""
    points = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return points
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class Drawing:
    def __init__(self, w=config.PANEL_W, h=config.PANEL_H, palette=None, actions=None,
                 clear_hold_s=config.CLEAR_HOLD_S, repeat_s=config.COLOR_REPEAT_S):
        self.w, self.h = w, h
        self.palette = list(palette or config.DRAW_PALETTE)     # [(name, (r, g, b)), ...]
        self.actions = dict(actions or config.DRAW_ACTIONS)     # gesture -> action name
        self.clear_hold_s = clear_hold_s
        self.repeat_s = repeat_s
        self.canvas = np.zeros((h, w, 3), np.uint8)
        self.color_index = 0
        self.cursor = (w // 2, h // 2)
        self.pen_down = False
        self.clear_progress = 0.0        # 0..1 while the clear gesture is being held
        self._last_point = None          # where the line continues from; None = pen was up
        self._prev_action = None
        self._action_since = 0.0         # when the current action's gesture started
        self._last_fired = 0.0           # when a colour change last happened
        self._cleared = False            # so one long hold clears only once

    # ---- small helpers -------------------------------------------------------------
    @property
    def color(self):
        return self.palette[self.color_index][1]

    @property
    def color_name(self):
        return self.palette[self.color_index][0]

    def _paint(self, x, y, changes):
        if 0 <= x < self.w and 0 <= y < self.h and tuple(self.canvas[y, x]) != self.color:
            self.canvas[y, x] = self.color
            changes.append(("P", x, y, self.color))

    def clear(self):
        self.canvas[:] = 0
        self._last_point = None
        return [("C",)]

    def step_color(self, step):
        self.color_index = (self.color_index + step) % len(self.palette)

    # ---- called once per camera frame ----------------------------------------------
    def update(self, gesture, x, y, now, raw=None):
        """gesture: the steady gesture name.  x, y: LED position of the fingertip.
        now: time in seconds.  raw: this frame's unfiltered gesture, if known.
        Returns the changes made this frame: ("P", x, y, (r, g, b)) and/or ("C",)."""
        changes = []
        action = self.actions.get(gesture)
        if gesture != "NONE":
            self.cursor = (x, y)
        if action != self._prev_action:              # a new gesture just started
            self._action_since = now
            self._cleared = False
        just_started = action != self._prev_action
        self._prev_action = action

        # Draw only while the hand clearly shows the draw gesture. If this frame's raw
        # gesture already differs, the hand is changing shape: lift the pen so the
        # finger curling away doesn't leave a stray tail.
        raw_action = self.actions.get(raw) if raw is not None else action
        self.pen_down = action == "draw" and raw_action == "draw"
        if self.pen_down:
            start = self._last_point or (x, y)
            for px, py in line_points(start[0], start[1], x, y):
                self._paint(px, py, changes)
            self._last_point = (x, y)
        else:
            self._last_point = None                  # next stroke starts fresh

        if action in ("next_color", "prev_color"):
            # Once when the gesture starts, then again every repeat_s while it's held.
            if just_started or now - self._last_fired >= self.repeat_s:
                self.step_color(1 if action == "next_color" else -1)
                self._last_fired = now

        if action == "clear":
            held = now - self._action_since
            self.clear_progress = 0.0 if self._cleared else min(1.0, held / self.clear_hold_s)
            if not self._cleared and held >= self.clear_hold_s:
                changes += self.clear()
                self._cleared = True
        else:
            self.clear_progress = 0.0
        return changes

    def render(self, now):
        """The picture to show: the canvas with the cursor blinking on top."""
        img = self.canvas.copy()
        if int(now * 4) % 2 == 0:                    # on for 1/4 s, off for 1/4 s
            cx, cy = self.cursor
            # Blink in the pen colour; use white if that wouldn't be visible there.
            visible = self.color != (0, 0, 0) and tuple(img[cy, cx]) != self.color
            img[cy, cx] = self.color if visible else (255, 255, 255)
        return img
