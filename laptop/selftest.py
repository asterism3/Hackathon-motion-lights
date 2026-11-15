"""Checks everything that doesn't need a camera or an ESP32.  Run:  python selftest.py"""
import os
import sys
import threading
import time
import traceback
from types import SimpleNamespace as P

import numpy as np

import config
import frames
import gestures
import protocol
from link import SerialLink

results = []


def check(name):
    def wrap(fn):
        try:
            out = fn()
            if out == "skip":
                results.append(("SKIP", name, ""))
            else:
                results.append(("PASS", name, ""))
        except Exception as e:
            results.append(("FAIL", name, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
        return fn
    return wrap


# ---------- a fake hand: 21 points, wrist at the bottom, fingers pointing up ----------
def fake_hand(index=False, middle=False, ring=False, pinky=False, thumb="in"):
    pts = [P(x=0.5, y=0.8) for _ in range(21)]
    pts[0] = P(x=0.5, y=0.8)
    for name, ext, fx in (("index", index, 0.42), ("middle", middle, 0.48),
                          ("ring", ring, 0.54), ("pinky", pinky, 0.60)):
        mcp, pip, tip = gestures.FINGERS[name]
        pts[mcp] = P(x=fx, y=0.60)
        pts[pip] = P(x=fx, y=0.50)
        pts[pip + 1] = P(x=fx, y=0.45 if ext else 0.58)
        pts[tip] = P(x=fx, y=0.40 if ext else 0.66)
    pts[1] = P(x=0.42, y=0.75)
    pts[2] = P(x=0.38, y=0.70)
    pts[3], pts[4] = {
        "in": (P(x=0.41, y=0.67), P(x=0.44, y=0.65)),      # tucked against the palm
        "side": (P(x=0.32, y=0.64), P(x=0.25, y=0.60)),    # sticking out sideways
        "up": (P(x=0.36, y=0.52), P(x=0.35, y=0.40)),      # pointing up
    }[thumb]
    return pts


def expect(lm, want):
    got = gestures.classify(lm)
    assert got == want, f"expected {want}, got {got}"


@check("open hand -> OPEN")
def _():
    expect(fake_hand(True, True, True, True, thumb="side"), "OPEN")


@check("fist -> FIST")
def _():
    expect(fake_hand(), "FIST")


@check("index finger -> POINT")
def _():
    expect(fake_hand(index=True), "POINT")


@check("two fingers -> PEACE")
def _():
    expect(fake_hand(index=True, middle=True), "PEACE")


@check("thumb up -> THUMBS_UP")
def _():
    expect(fake_hand(thumb="up"), "THUMBS_UP")


@check("gesture filter ignores one-frame flickers and smooths position")
def _():
    f = gestures.GestureFilter(stable_frames=3, smoothing=0.5)
    for _ in range(3):
        f.update("OPEN", 0.0, 0.0)
    assert f.current == "OPEN"
    f.update("FIST", 1.0, 1.0)                 # single odd frame
    assert f.current == "OPEN"
    assert abs(f.x - 0.5) < 1e-9               # moved halfway, not jumped
    for _ in range(3):
        f.update("FIST")
    assert f.current == "FIST"


@check("0..1 position maps onto the 32x32 panel and is clamped")
def _():
    assert gestures.to_led(0, 0) == (0, 0)
    assert gestures.to_led(1, 1) == (31, 31)
    assert gestures.to_led(0.5, 0.5) == (16, 16)
    assert gestures.to_led(-0.2, 1.4) == (0, 31)


@check("protocol: messages round-trip and junk is ignored")
def _():
    for g in protocol.GESTURES:
        assert protocol.parse_gesture(protocol.encode_gesture(g, 3, 29).decode()) == (g, 3, 29)
    assert protocol.parse_distance(protocol.encode_distance(42.26).decode()) == 42.3
    for junk in ("", "hello", "G WAVE 1 2", "G OPEN x 2", "D", "D far", "Object detected"):
        assert protocol.parse_gesture(junk) is None
        assert protocol.parse_distance(junk) is None


@check("board frames: every gesture draws something, and stays on the panel")
def _():
    seen = set()
    for g in protocol.GESTURES:
        for x, y in ((0, 0), (16, 16), (31, 31)):
            img = frames.render(g, x, y, 30.0)
            assert img.shape == (32, 32, 3)
            assert img.any(), f"{g} at {x},{y} drew nothing"
        seen.add(frames.render(g, 16, 16).tobytes())
    assert len(seen) == len(protocol.GESTURES), "two gestures look identical"


@check("ultrasonic distance sets circle size (closer = bigger)")
def _():
    assert frames.distance_radius(-1) == 5
    assert frames.distance_radius(5) == 10
    assert frames.distance_radius(100) == 2
    assert frames.distance_radius(500) == 2
    sizes = [frames.distance_radius(d) for d in range(5, 101)]
    assert sizes == sorted(sizes, reverse=True)
    near = np.count_nonzero(frames.render("OPEN", 16, 16, 10).any(axis=2))
    far = np.count_nonzero(frames.render("OPEN", 16, 16, 90).any(axis=2))
    assert near > far


class FakeESP32Port:
    """Pretends to be the ESP32's serial port: parses what the laptop sends,
    answers every gesture message with a distance, and prints debug noise too."""
    port = "fake"

    def __init__(self):
        self.received = []
        self._out = b"Ready!\nObject detected\n"
        self._in = b""

    def write(self, data):
        self._in += data
        while b"\n" in self._in:
            line, self._in = self._in.split(b"\n", 1)
            msg = protocol.parse_gesture(line.decode())
            if msg:
                self.received.append(msg)
                self._out += protocol.encode_distance(37.0)

    @property
    def in_waiting(self):
        return len(self._out)

    def read(self, n):
        data, self._out = self._out[:n], self._out[n:]
        return data

    def close(self):
        pass


@check("laptop link: sends only on change + heartbeat, reads distance back")
def _():
    fake = FakeESP32Port()
    link = SerialLink(serial_obj=fake)
    link.send("OPEN", 10, 10)
    link.send("OPEN", 10, 10)                   # same again: not resent
    link.send("FIST", 10, 10)
    assert fake.received == [("OPEN", 10, 10), ("FIST", 10, 10)], fake.received
    time.sleep(config.HEARTBEAT_S + 0.05)
    link.send("FIST", 10, 10)                   # heartbeat
    assert len(fake.received) == 3
    link.poll()
    assert link.distance_cm == 37.0


@check("fake ESP32 on a real virtual serial port (pyserial)")
def _():
    if os.name == "nt":
        return "skip"                           # pty virtual ports are Linux/macOS only
    import pty
    import serial
    master, slave = pty.openpty()
    import tty
    tty.setraw(slave)
    got = []

    def esp32():                                # reads gesture lines, replies with distance
        buf = b""
        deadline = time.time() + 3
        while time.time() < deadline and len(got) < 2:
            buf += os.read(master, 256)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = protocol.parse_gesture(line.decode())
                if msg:
                    got.append(msg)
                    os.write(master, b"debug text\r\n" + protocol.encode_distance(55.5))

    t = threading.Thread(target=esp32, daemon=True)
    t.start()
    ser = serial.Serial(os.ttyname(slave), config.BAUD, timeout=0)
    link = SerialLink(serial_obj=ser)
    link.send("PEACE", 4, 27)
    link.send("POINT", 5, 26)
    deadline = time.time() + 3
    while link.distance_cm != 55.5 and time.time() < deadline:
        link.poll()
        time.sleep(0.01)
    t.join(1)
    ser.close()
    os.close(master)
    assert got == [("PEACE", 4, 27), ("POINT", 5, 26)], got
    assert link.distance_cm == 55.5


def moved(lm, dx=0.0, dy=0.0, scale=1.0, noise=0.0, rng=None):
    """The same hand shifted, resized and jittered, like a real hand moving in front of the camera."""
    out = []
    for p in lm:
        jx, jy = (rng.normal(0, noise, 2) if rng is not None else (0, 0))
        out.append(P(x=0.5 + (p.x - 0.5) * scale + dx + jx, y=0.5 + (p.y - 0.5) * scale + dy + jy))
    return out


@check("ASL features ignore where the hand is and how big it looks")
def _():
    import asl
    hand = fake_hand(index=True, middle=True)
    a = asl.features(asl.raw_row(hand))
    b = asl.features(asl.raw_row(moved(hand, dx=0.2, dy=-0.1, scale=0.5)))
    assert a.shape == (42,)
    assert np.allclose(a, b), "features changed when the hand moved"
    c = asl.features(asl.raw_row(fake_hand()))
    assert not np.allclose(a, c), "different hand shapes gave the same features"


@check("ASL: record -> train -> recognise, on fake hands")
def _():
    import tempfile
    import asl
    import train_asl
    shapes = {"A": fake_hand(), "B": fake_hand(True, True, True, True),
              "L": fake_hand(index=True, thumb="side"), "Y": fake_hand(pinky=True, thumb="side")}
    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as tmp:
        data, model = os.path.join(tmp, "d.csv"), os.path.join(tmp, "m.joblib")
        rows = []
        for letter, hand in shapes.items():
            for _ in range(40):
                h = moved(hand, rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2),
                          rng.uniform(0.5, 1.3), noise=0.004, rng=rng)
                rows.append((letter, asl.raw_row(h)))
        asl.append_samples(rows, data)
        acc = train_asl.train(data, model, quiet=True)
        assert acc >= 0.95, f"test accuracy only {acc:.0%}"
        clf = asl.ASLClassifier(model, min_confidence=0.6)
        for letter, hand in shapes.items():
            got, conf = clf.predict(moved(hand, dx=0.1, scale=0.8))
            assert got == letter, f"{letter} recognised as {got} ({conf:.0%})"
        # Not enough data must give a clear message, not a crash.
        asl.append_samples([("A", asl.raw_row(shapes["A"]))], os.path.join(tmp, "small.csv"))
        try:
            train_asl.train(os.path.join(tmp, "small.csv"), model, quiet=True)
            raise AssertionError("training on 1 sample should refuse")
        except ValueError:
            pass


def lit(art):
    """Set of (x, y) pixels that are not black."""
    ys, xs = np.nonzero(art.canvas.any(axis=2))
    return set(zip(xs.tolist(), ys.tolist()))


@check("draw: a fast finger still leaves a line with no gaps")
def _():
    from drawing import Drawing, line_points
    art = Drawing()
    art.update("POINT", 2, 2, 0.0)
    art.update("POINT", 20, 9, 0.1)              # jumped 18 LEDs in one frame
    pts = line_points(2, 2, 20, 9)
    assert lit(art) == set(pts)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):  # every pixel touches the next one
        assert max(abs(x1 - x0), abs(y1 - y0)) == 1
    art.update("POINT", 40, 9, 0.2)              # off the edge of the panel: no crash
    assert all(0 <= x < 32 and 0 <= y < 32 for x, y in lit(art))


@check("draw: moving with the pen up draws nothing and starts a new stroke")
def _():
    from drawing import Drawing
    art = Drawing()
    art.update("POINT", 1, 1, 0.0)
    art.update("OPEN", 15, 15, 0.1)              # pen up: move only
    assert not art.pen_down and art.cursor == (15, 15)
    art.update("NONE", 0, 0, 0.2)                # hand gone: cursor stays where it was
    assert art.cursor == (15, 15)
    art.update("POINT", 30, 30, 0.3)
    assert lit(art) == {(1, 1), (30, 30)}, "pen-up movement was joined into a line"
    # The hand starting to change shape (raw gesture differs) lifts the pen at once.
    art.update("POINT", 30, 20, 0.4, raw="FIST")
    assert lit(art) == {(1, 1), (30, 30)}


@check("draw: colour gestures step once, repeat when held, and wrap around")
def _():
    from drawing import Drawing
    art = Drawing(repeat_s=1.0)
    n = len(art.palette)
    for t in (0.0, 0.1, 0.5, 0.9):               # one long PEACE: only one step...
        art.update("PEACE", 5, 5, t)
    assert art.color_index == 1
    art.update("PEACE", 5, 5, 1.05)              # ...until held for the repeat time
    assert art.color_index == 2
    art.update("OPEN", 5, 5, 1.2)
    art.update("THUMBS_UP", 5, 5, 1.3)
    assert art.color_index == 1
    for i in range(n):                           # all the way round
        art.update("OPEN", 5, 5, 2 + i)
        art.update("PEACE", 5, 5, 2 + i + 0.5)
    assert art.color_index == 1
    art.update("POINT", 3, 3, 50.0)
    assert tuple(art.canvas[3, 3]) == art.palette[1][1], "drew in the wrong colour"


@check("draw: clearing needs the gesture held, and happens once")
def _():
    from drawing import Drawing
    art = Drawing(clear_hold_s=1.0)
    art.update("POINT", 4, 4, 0.0)
    art.update("FIST", 4, 4, 1.0)
    art.update("FIST", 4, 4, 1.5)                # only half a second so far
    assert lit(art) and 0.4 < art.clear_progress < 0.6
    art.update("OPEN", 4, 4, 1.6)                # let go early: nothing cleared
    assert lit(art) and art.clear_progress == 0
    art.update("FIST", 4, 4, 2.0)
    changes = art.update("FIST", 4, 4, 3.1)
    assert changes == [("C",)] and not lit(art)
    assert art.update("FIST", 4, 4, 5.0) == [], "cleared a second time during one hold"


@check("draw: the list of changes is enough to rebuild the picture (for the ESP32)")
def _():
    from drawing import Drawing
    art = Drawing(clear_hold_s=0.5)
    copy = np.zeros((32, 32, 3), np.uint8)       # what a panel would show
    rng = np.random.default_rng(3)
    t = 0.0
    for _ in range(400):
        t += 0.1
        g = str(rng.choice(["POINT", "POINT", "POINT", "OPEN", "PEACE", "FIST", "NONE"]))
        for change in art.update(g, int(rng.integers(0, 32)), int(rng.integers(0, 32)), t):
            if change[0] == "C":
                copy[:] = 0
            else:
                _, x, y, colour = change
                copy[y, x] = colour
    assert lit(art), "test never drew anything"
    assert np.array_equal(copy, art.canvas)
    img = art.render(0.0)                        # cursor is drawn on a copy, not the canvas
    assert np.array_equal(copy, art.canvas) and img.shape == (32, 32, 3)


@check("MediaPipe hand model loads and runs")
def _():
    try:
        import tracker
    except ImportError as e:
        raise AssertionError(f"install requirements first: {e}")
    t = tracker.HandTracker()
    try:
        g, x, y, lm = t.process(np.zeros((240, 320, 3), np.uint8))
        assert (g, lm) == ("NONE", None)        # blank image: no hand
    finally:
        t.close()


if __name__ == "__main__":
    print()
    for status, name, err in results:
        print(f"[{status}] {name}" + (f"\n        {err}" if err else ""))
    failed = sum(s == "FAIL" for s, _, _ in results)
    passed = sum(s == "PASS" for s, _, _ in results)
    print(f"\n{passed} passed, {failed} failed, {len(results) - passed - failed} skipped")
    sys.exit(1 if failed else 0)
