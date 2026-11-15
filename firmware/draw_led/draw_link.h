// draw_link.h - receives the drawing from the laptop (drawing mode). Add-on to laptop_link.h.
//
// To use it in a sketch that already uses laptop_link.h:
//
//   #include "draw_link.h"          // under  #include "laptop_link.h"
//   DrawLink art;                   // under  LaptopLink laptop;
//   art.poll(laptop);               // INSTEAD OF  laptop.poll();   (it feeds laptop too)
//
// and where the panel is drawn, in loop():
//
//   if (art.drawMode) {
//     if (art.needsRedraw()) { art.draw(matrix); matrix.show(); }
//   } else {
//     ... what the sketch did before (gestures) ...
//   }
//
// Also put  Serial.setRxBufferSize(4096);  just BEFORE  Serial.begin(115200);  so a burst
// of pixels isn't dropped while the sketch is busy (for example measuring distance).
//
// Messages handled here (must match laptop/protocol.py); every other line is passed on
// to laptop_link.h untouched:
//   M DRAW | M GESTURE      which mode the laptop is in
//   P x y r g b             paint one pixel
//   C                       clear the drawing
//   K x y r g b             cursor position and pen colour
//   R y <128 hex digits>    one whole row, 32 pixels of RGB565 (background repair)
#pragma once
#include <Arduino.h>
#include <string.h>
#include <stdlib.h>
#include "laptop_link.h"

class DrawLink {
 public:
  static const int W = 32;
  static const int H = 32;
  uint16_t canvas[H][W];            // the drawing, in the panel's colour format (RGB565)
  bool drawMode = false;            // true while the laptop is in drawing mode
  int cursorX = -1;                 // -1 = no cursor yet
  int cursorY = -1;
  uint16_t penColor = 0xFFFF;
  unsigned long timeoutMs = 2000;   // laptop silent this long -> stop blinking the cursor

  DrawLink() { clearCanvas(); }

  static uint16_t rgb565(long r, long g, long b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
  }

  void clearCanvas() { memset(canvas, 0, sizeof(canvas)); }

  // Call every loop() instead of laptop.poll(). Reads all waiting bytes without blocking.
  void poll(LaptopLink &laptop, Stream &port = Serial) {
    while (port.available()) {
      char c = (char)port.read();
      if (c == '\r') continue;
      if (c == '\n') {
        if (!tooLong_) {
          buf_[len_] = '\0';
          if (!handleLine(buf_)) laptop.handleLine(buf_);
        }
        len_ = 0;
        tooLong_ = false;
      } else if (len_ < sizeof(buf_) - 1) {
        buf_[len_++] = c;
      } else {
        tooLong_ = true;             // junk: skip everything up to the next newline
      }
    }
    // We already read everything, so give laptop_link an empty port: it has nothing to
    // read and only runs its own "laptop went quiet -> gesture NONE" check.
    Nothing nothing;
    laptop.poll(nothing);
  }

  bool connected() const { return lastMsgMs_ != 0 && millis() - lastMsgMs_ <= timeoutMs; }

  // True once after the laptop switches between drawing and gesture mode.
  bool modeChanged() {
    bool c = modeChanged_;
    modeChanged_ = false;
    return c;
  }

  // The cursor blinks: on for 1/4 s, off for 1/4 s. Hidden if the laptop has gone quiet.
  bool cursorShown() const { return cursorX >= 0 && connected() && (millis() / 250) % 2 == 0; }

  // Blink in the pen colour; use white where that wouldn't be visible (eraser, or the
  // pixel underneath already has that colour). Same rule as laptop/drawing.py render().
  uint16_t cursorColor() const {
    bool visible = penColor != 0 && canvas[cursorY][cursorX] != penColor;
    return visible ? penColor : 0xFFFF;
  }

  // True when the panel needs repainting: new pixels arrived or the cursor blinked.
  bool needsRedraw() {
    bool on = cursorShown();
    if (on != lastCursorOn_) {
      lastCursorOn_ = on;
      dirty_ = true;
    }
    bool d = dirty_;
    dirty_ = false;
    return d;
  }

  // Paints the drawing and the cursor. G is anything with drawPixel(x, y, color), e.g.
  // Adafruit_Protomatter. Call matrix.show() afterwards.
  template <typename G>
  void draw(G &g) { draw(g, cursorShown()); }

  template <typename G>
  void draw(G &g, bool withCursor) {
    for (int y = 0; y < H; y++)
      for (int x = 0; x < W; x++) g.drawPixel(x, y, canvas[y][x]);
    if (withCursor && cursorX >= 0) g.drawPixel(cursorX, cursorY, cursorColor());
  }

  // Returns true if the line was a drawing message (even a damaged one, which is
  // dropped). Returns false, leaving the line untouched, if it belongs to laptop_link.h.
  // Public so it can be tested on a PC; normally poll() calls it.
  bool handleLine(char *line) {
    char tag = line[0];
    if (tag != 'M' && tag != 'P' && tag != 'C' && tag != 'K' && tag != 'R') return false;
    if (line[1] != ' ' && line[1] != '\0') return false;
    lastMsgMs_ = millis();
    if (lastMsgMs_ == 0) lastMsgMs_ = 1;
    const char *p = line + 1;
    while (*p == ' ') p++;

    if (tag == 'M') {
      bool wantDraw;
      if (strcmp(p, "DRAW") == 0) wantDraw = true;
      else if (strcmp(p, "GESTURE") == 0) wantDraw = false;
      else return true;
      if (wantDraw != drawMode) {
        drawMode = wantDraw;
        modeChanged_ = true;
        dirty_ = true;
      }
    } else if (tag == 'C') {
      if (*p != '\0') return true;
      clearCanvas();
      dirty_ = true;
    } else if (tag == 'P' || tag == 'K') {
      long v[5];
      if (!readNumbers(p, v, 5)) return true;
      for (int i = 2; i < 5; i++) v[i] = v[i] < 0 ? 0 : (v[i] > 255 ? 255 : v[i]);
      bool onPanel = v[0] >= 0 && v[0] < W && v[1] >= 0 && v[1] < H;
      uint16_t c = rgb565(v[2], v[3], v[4]);
      if (tag == 'P') {
        if (onPanel) canvas[v[1]][v[0]] = c;
      } else {
        cursorX = onPanel ? (int)v[0] : -1;
        cursorY = onPanel ? (int)v[1] : -1;
        penColor = c;
      }
      dirty_ = true;
    } else {  // 'R': one whole row. Decode into a spare row first, so a damaged
              // message changes nothing.
      char *end;
      long y = strtol(p, &end, 10);
      if (end == p || *end != ' ' || y < 0 || y >= H) return true;
      p = end + 1;
      if (strlen(p) != (size_t)W * 4) return true;
      uint16_t row[W];
      for (int x = 0; x < W; x++) {
        uint16_t value = 0;
        for (int i = 0; i < 4; i++) {
          int d = hexDigit(p[x * 4 + i]);
          if (d < 0) return true;
          value = (uint16_t)((value << 4) | d);
        }
        row[x] = value;
      }
      if (memcmp(canvas[y], row, sizeof(row)) != 0) {
        memcpy(canvas[y], row, sizeof(row));
        dirty_ = true;
      }
    }
    return true;
  }

 private:
  char buf_[160];                   // longest message is a row: "R 31 " + 128 hex digits
  size_t len_ = 0;
  bool tooLong_ = false;
  unsigned long lastMsgMs_ = 0;
  bool dirty_ = true;
  bool modeChanged_ = false;
  bool lastCursorOn_ = false;

  // A port with nothing in it, handed to laptop_link's poll() (see poll() above).
  class Nothing : public Stream {
   public:
    int available() { return 0; }
    int read() { return -1; }
    int peek() { return -1; }
    void flush() {}
    size_t write(uint8_t) { return 0; }
  };

  static int hexDigit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  }

  // Reads exactly n whole numbers separated by spaces, and nothing after them.
  static bool readNumbers(const char *p, long *out, int n) {
    for (int i = 0; i < n; i++) {
      char *end;
      out[i] = strtol(p, &end, 10);
      if (end == p) return false;
      p = end;
      if (i < n - 1 && *p != ' ') return false;
    }
    return *p == '\0';
  }
};
