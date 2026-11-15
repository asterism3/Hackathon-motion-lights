"""Sends the drawing to the ESP32. Twin of firmware/draw_led/draw_link.h, which receives it.

The laptop owns the picture; the panel only does what it's told:
  - every pixel that changes is sent straight away ("P ..."), so drawing feels instant;
  - the cursor is sent when it moves or the pen colour changes ("K ...");
  - one row of the whole picture is re-sent every DRAW_RESYNC_ROW_S ("R ..."), so if a
    message got lost, or the ESP32 was unplugged or restarted, the panel catches up
    within a few seconds without anyone doing anything.
"""
import config
import protocol


class DrawSender:
    def __init__(self, link, row_period_s=config.DRAW_RESYNC_ROW_S):
        self.link = link                     # anything with .write(bytes)
        self.row_period_s = row_period_s
        self._cursor = None                  # last (x, y, colour) sent
        self._row = 0                        # next row to re-send
        self._row_due = None                 # when the next row should go out

    def start(self):
        """Call once when drawing mode begins: wipe whatever the panel was showing."""
        self.link.write(protocol.encode_clear())

    def send_changes(self, changes):
        """changes: the list Drawing.update() or Drawing.clear() returned."""
        for change in changes:
            if change[0] == "C":
                self.link.write(protocol.encode_clear())
            else:
                _, x, y, color = change
                self.link.write(protocol.encode_pixel(x, y, color))

    def tick(self, art, now):
        """Call every frame, after send_changes: cursor updates and the background re-send."""
        cursor = (art.cursor[0], art.cursor[1], art.color)
        if cursor != self._cursor:
            self.link.write(protocol.encode_cursor(*cursor))
            self._cursor = cursor
        if self._row_due is None:
            self._row_due = now
        if now >= self._row_due:
            self.link.write(protocol.encode_row(self._row, art.canvas[self._row]))
            self._row = (self._row + 1) % art.h
            # Schedule from when this row was due, not from now, so the average pace
            # stays exact whatever the camera frame rate is.
            self._row_due = max(self._row_due + self.row_period_s, now)
            if self._row == 0:
                self._cursor = None          # re-send the cursor once per full pass too
