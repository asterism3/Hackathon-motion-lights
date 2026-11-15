"""The text protocol between laptop and ESP32. Must match firmware/gesture_led/laptop_link.h.

Laptop -> ESP32, one line:   G <GESTURE> <x> <y>\\n     e.g.  "G OPEN 12 20"
ESP32 -> laptop, one line:   D <centimetres>\\n          e.g.  "D 42.5"

x and y are LED coordinates, 0..31. Any other line is ignored by both sides,
so debug prints from the ESP32 don't break anything.

Drawing mode adds these laptop -> ESP32 lines (read by firmware/draw_led/draw_link.h).
Older firmware that doesn't know them just ignores them:

  M <MODE>                 "M DRAW" or "M GESTURE": which mode the laptop is in
  P <x> <y> <r> <g> <b>    paint one pixel, colour 0..255 each
  C                        clear the drawing
  K <x> <y> <r> <g> <b>    cursor position and pen colour
  R <y> <128 hex digits>   one whole row of the drawing: 32 pixels, 4 hex digits each
                           (RGB565, the panel's own colour format). The laptop keeps
                           re-sending rows in the background, so the panel fixes itself
                           if a message was lost or the ESP32 was restarted.
"""

GESTURES = ("NONE", "OPEN", "FIST", "POINT", "PEACE", "THUMBS_UP")


def encode_gesture(gesture: str, x: int, y: int) -> bytes:
    if gesture not in GESTURES:
        raise ValueError(f"unknown gesture {gesture!r}")
    return f"G {gesture} {int(x)} {int(y)}\n".encode("ascii")


def parse_gesture(line: str):
    """Returns (gesture, x, y) or None. Used by the self-test and fake ESP32."""
    parts = line.strip().split()
    if len(parts) != 4 or parts[0] != "G" or parts[1] not in GESTURES:
        return None
    try:
        return parts[1], int(parts[2]), int(parts[3])
    except ValueError:
        return None


def encode_distance(cm: float) -> bytes:
    return f"D {cm:.1f}\n".encode("ascii")


def parse_distance(line: str):
    """Returns distance in cm (float) or None if the line isn't a distance message."""
    parts = line.strip().split()
    if len(parts) != 2 or parts[0] != "D":
        return None
    try:
        return float(parts[1])
    except ValueError:
        return None


# ---------------- drawing mode ----------------
MODES = ("GESTURE", "DRAW")


def rgb565(color):
    """(r, g, b) 0..255 -> the 16-bit colour the panel uses. Same formula as the firmware."""
    r, g, b = (int(v) for v in color)
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def encode_mode(mode: str) -> bytes:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return f"M {mode}\n".encode("ascii")


def encode_pixel(x, y, color) -> bytes:
    r, g, b = (int(v) for v in color)
    return f"P {int(x)} {int(y)} {r} {g} {b}\n".encode("ascii")


def encode_clear() -> bytes:
    return b"C\n"


def encode_cursor(x, y, color) -> bytes:
    r, g, b = (int(v) for v in color)
    return f"K {int(x)} {int(y)} {r} {g} {b}\n".encode("ascii")


def encode_row(y, row) -> bytes:
    """row: 32 colours (r, g, b)."""
    return (f"R {int(y)} " + "".join(f"{rgb565(c):04x}" for c in row) + "\n").encode("ascii")
