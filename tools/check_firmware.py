"""Compiles the firmware headers on this PC (needs g++) and checks that:
  1. laptop_link.h parses messages the way laptop/protocol.py writes them, and rejects junk;
  2. gesture_frames.h draws exactly the same pixels as laptop/frames.py;
  3. draw_link.h, fed the real messages from a drawing session, ends up showing exactly
     the laptop's picture and cursor, even when some messages are lost on the way;
  4. the copies of the shared headers in firmware/draw_led match firmware/gesture_led.
Run from anywhere:  python tools/check_firmware.py
"""
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.path.join(ROOT, "firmware", "gesture_led")
FW_DRAW = os.path.join(ROOT, "firmware", "draw_led")
sys.path.insert(0, os.path.join(ROOT, "laptop"))
import frames      # noqa: E402
import protocol    # noqa: E402
from draw_link import DrawSender   # noqa: E402
from drawing import Drawing        # noqa: E402

# Minimal stand-ins for the Arduino core, just enough for the headers.
ARDUINO_SHIM = r"""
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string>
static unsigned long fake_ms = 1000;
inline unsigned long millis() { return fake_ms; }
struct Print {
  std::string out;
  virtual ~Print() {}
  virtual size_t write(uint8_t c) { out += (char)c; return 1; }
  virtual void flush() {}
  void print(const char *s) { out += s; }
  void println(float v, int d) { char b[32]; snprintf(b, sizeof b, "%.*f\n", d, v); out += b; }
};
struct Stream : Print {
  virtual int available() = 0;
  virtual int read() = 0;
  virtual int peek() = 0;
};
struct FakeSerial : Stream {              // a serial port fed from a string
  std::string in; size_t pos = 0;
  int available() { return (int)(in.size() - pos); }
  int read() { return (unsigned char)in[pos++]; }
  int peek() { return (unsigned char)in[pos]; }
};
static FakeSerial Serial;
"""

TEST_CPP = r"""
#include "laptop_link.h"
#include "gesture_frames.h"

struct Canvas {
  uint16_t px[32][32] = {};
  uint16_t color565(uint8_t r, uint8_t g, uint8_t b) {
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
  }
  void drawPixel(int x, int y, uint16_t c) { px[y][x] = c; }
};

int main(int argc, char **argv) {
  // --- parser ---
  FakeSerial s;
  LaptopLink L;
  s.in = INPUT_LINES;
  L.poll(s);
  printf("parsed %s %d %d %d\n", L.gesture, L.x, L.y, (int)L.changed());
  fake_ms += 5000; L.poll(s);
  printf("timeout %s\n", L.gesture);
  L.sendDistance(42.25f, s);
  printf("sent %s", s.out.c_str());

  // --- frames ---
  const char *gs[] = {"NONE", "OPEN", "FIST", "POINT", "PEACE", "THUMBS_UP"};
  const int pos[][2] = {{0, 0}, {16, 16}, {31, 31}, {2, 29}, {30, 3}};
  const float dists[] = {-1, 3, 10, 47.9f, 100, 400};
  for (auto g : gs) for (auto &p : pos) for (float d : dists) {
    Canvas c;
    drawGestureFrame(c, g, p[0], p[1], d);
    printf("frame %s %d %d %g ", g, p[0], p[1], d);
    for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) printf("%04x", c.px[y][x]);
    printf("\n");
  }
}
"""

# Reads a file of laptop messages in small chunks (like bytes trickling in over USB),
# then prints what the panel would show, with the cursor on.
DRAW_CPP = r"""
#include "laptop_link.h"
#include "draw_link.h"
#include <fstream>
#include <sstream>

struct Canvas {
  uint16_t px[32][32] = {};
  void drawPixel(int x, int y, uint16_t c) { px[y][x] = c; }
};

int main(int argc, char **argv) {
  std::ifstream f(argv[1], std::ios::binary);
  std::stringstream ss; ss << f.rdbuf();
  std::string all = ss.str();
  FakeSerial s;
  LaptopLink laptop;
  DrawLink art;
  int modeChanges = 0;
  for (size_t i = 0; i < all.size(); i += 7) {       // 7 bytes per loop(): lines get split
    s.in += all.substr(i, 7);
    art.poll(laptop, s);
    if (art.modeChanged()) modeChanges++;
    fake_ms += 1;
  }
  Canvas c;
  art.draw(c, true);
  printf("%d %d %s %d %d %d ", (int)art.drawMode, modeChanges, laptop.gesture, laptop.x, laptop.y,
         (int)art.connected());
  for (int y = 0; y < 32; y++) for (int x = 0; x < 32; x++) printf("%04x", c.px[y][x]);
  fake_ms += 5000;                                    // laptop goes quiet
  art.poll(laptop, s);
  printf(" %d %d %s\n", (int)art.cursorShown(), (int)art.connected(), laptop.gesture);
}
"""


# The firmware from before drawing mode existed: laptop_link.h on its own.
OLD_FW_CPP = r"""
#include "laptop_link.h"
#include <fstream>
#include <sstream>
int main(int argc, char **argv) {
  std::ifstream f(argv[1], std::ios::binary);
  std::stringstream ss; ss << f.rdbuf();
  std::string all = ss.str();
  FakeSerial s;
  LaptopLink laptop;
  int wrong = 0;
  for (size_t i = 0; i < all.size(); i += 7) {
    s.in += all.substr(i, 7);
    laptop.poll(s);
    if (!laptop.is("NONE") && !laptop.is("POINT")) wrong++;   // draw mode only sends these two
    fake_ms += 1;
  }
  printf("%s %d %d %d\n", laptop.gesture, laptop.x, laptop.y, wrong);
}
"""


def build(tmp, name, source):
    src = os.path.join(tmp, name + ".cpp")
    with open(src, "w") as f:
        f.write(source)
    exe = os.path.join(tmp, name)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Werror", "-I", tmp, "-I", FW_DRAW, "-I", FW,
                    src, "-o", exe], check=True)
    return exe


def hex565(img):
    return "".join(f"{protocol.rgb565(img[r, c]):04x}" for r in range(32) for c in range(32))


class Capture:
    """Stands in for the serial link: collects what the laptop would send."""

    def __init__(self):
        self.lines = []

    def write(self, data):
        self.lines.append(data)


def drawing_session(seed, frames_n=600):
    """A random drawing session. Returns (the Drawing, every message sent, in order)."""
    rng = np.random.default_rng(seed)
    art, cap = Drawing(clear_hold_s=0.5), Capture()
    sender = DrawSender(cap, row_period_s=0.1)
    cap.write(b"Ready!\r\nG WAVE 1 2\nPx 1 2 3 4 5\nP 1 2 3\nR 3 zz\nK 40 40 9 9 9\n")  # junk first
    cap.write(protocol.encode_mode("DRAW"))
    sender.start()
    t, x, y = 0.0, 16, 16
    for i in range(frames_n):
        t += 1 / 30
        if i < frames_n - 150:
            g = str(rng.choice(["POINT"] * 6 + ["OPEN", "OPEN", "PEACE", "FIST", "THUMBS_UP", "NONE"]))
        else:
            g = "OPEN"     # finish with 5 s of not drawing, so the background repair can finish
        x = int(np.clip(x + rng.integers(-6, 7), -2, 33))     # sometimes off the panel edge
        y = int(np.clip(y + rng.integers(-6, 7), -2, 33))
        lx, ly = min(31, max(0, x)), min(31, max(0, y))
        sender.send_changes(art.update(g, lx, ly, t))
        sender.tick(art, t)
        cap.write(protocol.encode_gesture("NONE" if g == "NONE" else "POINT", lx, ly))
    return art, cap.lines


def check_drawing(tmp, exe, label, drop_every=0):
    art, lines = drawing_session(seed=7)
    assert art.canvas.any(), "session drew nothing"
    if drop_every:        # lose pixel/clear messages, as a flooded or restarted ESP32 would
        kept, n = [], 0
        for l in lines:
            if l[:1] in (b"P", b"C"):
                n += 1
                if n % drop_every == 0:
                    continue
            kept.append(l)
        assert len(lines) - len(kept) > 50, "test dropped too few messages to mean anything"
        lines = kept
    path = os.path.join(tmp, "session.txt")
    with open(path, "wb") as f:
        f.write(b"".join(lines))
    out = subprocess.run([exe, path], check=True, capture_output=True, text=True).stdout.split()
    draw_mode, mode_changes, gesture, gx, gy, connected, pixels, cursor_after, conn_after, g_after = out
    want = hex565(art.render(0.0))            # laptop's picture with the cursor on
    problems = []
    if pixels != want:
        diff = sum(pixels[i:i + 4] != want[i:i + 4] for i in range(0, len(want), 4))
        problems.append(f"{diff} pixels differ from the laptop")
    if (draw_mode, mode_changes, connected) != ("1", "1", "1"):
        problems.append(f"mode state wrong: drawMode={draw_mode} changes={mode_changes}")
    if (gesture, int(gx), int(gy)) != ("POINT", art.cursor[0], art.cursor[1]):
        problems.append(f"gesture lines not passed on to laptop_link: {gesture} {gx} {gy}")
    if (cursor_after, conn_after, g_after) != ("0", "0", "NONE"):
        problems.append("cursor/gesture did not time out after the laptop went quiet")
    print(("PASS " if not problems else "FAIL ") + label + ("" if not problems else ": " + "; ".join(problems)))
    return len(problems)


def main():
    if not shutil.which("g++"):
        print("g++ not found; this check needs a C++ compiler (skip it on Windows).")
        return 0
    fails = 0
    # Good message last; junk lines before it must be ignored, not crash or change state.
    lines = ["Object detected", "G WAVE 1 2", "G OPEN 1", "G OPEN a 2", "G OPEN 1 2 3",
             "x" * 200, "D 12.0", protocol.encode_gesture("PEACE", 4, 40).decode().strip()]
    c_lines = "".join(l.replace('"', '\\"') + "\\r\\n" for l in lines)
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "Arduino.h"), "w") as f:
            f.write(ARDUINO_SHIM)
        exe = build(tmp, "t", f'#define INPUT_LINES "{c_lines}"\n' + TEST_CPP)
        out = subprocess.run([exe], check=True, capture_output=True, text=True).stdout.splitlines()

        draw_exe = build(tmp, "d", DRAW_CPP)
        fails += check_drawing(tmp, draw_exe, "draw_link.h shows the laptop's drawing and cursor")
        fails += check_drawing(tmp, draw_exe, "draw_link.h repairs itself when 1 in 3 pixel messages is lost",
                               drop_every=3)

        old_exe = build(tmp, "o", OLD_FW_CPP)
        art, session = drawing_session(seed=7)
        path = os.path.join(tmp, "session_old.txt")
        with open(path, "wb") as f:
            f.write(b"".join(session))
        got = subprocess.run([old_exe, path], check=True, capture_output=True, text=True).stdout.split()
        ok = got == ["POINT", str(art.cursor[0]), str(art.cursor[1]), "0"]
        print(("PASS " if ok else f"FAIL {got} ")
              + "older firmware ignores drawing messages and still tracks the fingertip dot")
        fails += not ok

    for name in ("laptop_link.h", "gesture_frames.h"):
        same = filecmp.cmp(os.path.join(FW, name), os.path.join(FW_DRAW, name), shallow=False)
        print(("PASS " if same else "FAIL ") + f"firmware/draw_led/{name} is an exact copy of gesture_led's")
        fails += not same

    # y=40 is clamped to 31; the distance reply must parse with protocol.parse_distance.
    want = ["parsed PEACE 4 31 1", "timeout NONE", "sent D 42.2"]
    for w, g in zip(want, out[:3]):
        if w.startswith("sent"):
            d = protocol.parse_distance(g[len("sent "):])
            ok = d is not None and abs(d - 42.25) <= 0.05
        else:
            ok = g == w
        print(("PASS " if ok else "FAIL ") + g + ("" if ok else f"   (expected {w})"))
        fails += not ok
    frames_checked = frame_fails = 0
    for line in out[3:]:
        _, g, x, y, d, hexpx = line.split()
        x, y, d = int(x), int(y), float(d)
        if hex565(frames.render(g, x, y, d)) != hexpx:
            print(f"FAIL frame {g} at {x},{y} dist {d}: firmware and laptop board differ")
            frame_fails += 1
        frames_checked += 1
    fails += frame_fails
    print(("PASS " if not frame_fails else "FAIL ")
          + f"{frames_checked} gesture frames compared, firmware == laptop board")
    print("\nAll firmware checks passed." if not fails else f"\n{fails} firmware check(s) FAILED.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
