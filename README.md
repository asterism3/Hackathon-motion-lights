# Hackathon motion lights

Hand gestures seen by a laptop webcam drive a 32x32 RGB LED panel on an ESP32.
An ultrasonic sensor on the ESP32 measures how far your hand is and sends it back.

```
webcam -> laptop/ (MediaPipe hand tracking -> gesture + x,y) --USB serial--> ESP32 -> LED panel
                                       ^------------- distance (cm) ----------'  (HC-SR04)
```

| Gesture       | Panel shows                                       |
|---------------|---------------------------------------------------|
| open hand     | green circle that follows your palm; closer = bigger |
| fist          | red block                                         |
| point (index) | white dot on your fingertip                       |
| peace (2 fingers) | two yellow bars                               |
| thumbs up     | magenta plus                                      |
| no hand       | dim blue border                                   |

## Layout

```
laptop/                    the vision side (Python)
  main.py                  run this
  camera.py                opens the webcam (default driver, DirectShow as fallback)
  config.py                every setting: port, camera, smoothing, panel size
  tracker.py               camera + MediaPipe -> landmarks   (swap this for another model)
  gestures.py              landmarks -> gesture name          (add gestures here)
  protocol.py              the serial message format
  link.py                  USB serial to the ESP32
  frames.py                what the panel draws (twin of gesture_frames.h)
  board_view.py            on-screen copy of the LED panel
  drawing.py               draw mode: canvas, pen, colours, clear
  draw_link.py             sends the drawing to the ESP32
  asl.py                   ASL letter features + classifier
  record_asl.py            record ASL examples
  train_asl.py             train the ASL model
  selftest.py              checks that need no camera or ESP32
firmware/gesture_led/      ESP32 sketch: gesture mode only
  gesture_led.ino          panel + ultrasonic + laptop link
  laptop_link.h            drop-in parser for any sketch
  gesture_frames.h         what the panel draws (twin of frames.py)
firmware/draw_led/         ESP32 sketch: gesture mode + drawing mode (upload this one to draw)
  draw_led.ino             everything gesture_led.ino does, plus drawing
  draw_link.h              drop-in receiver for the drawing (twin of draw_link.py)
  laptop_link.h, gesture_frames.h   exact copies of the ones above (Arduino needs them here)
tools/check_firmware.py    compiles the firmware headers on a PC and compares them to the laptop
hackathon*.ino             the original test sketches, unchanged
```

Each file does one job. A new gesture touches `gestures.py`, `protocol.py` and the two
frame files. A new output (sound, a second display) reads `gesture, x, y` in `main.py`.
A different vision model only replaces `tracker.py`.

## Laptop setup (Windows)

Use Python 3.11, 3.12 or 3.13 (3.12 recommended). In the `laptop` folder:

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

macOS/Linux: `python3 -m venv .venv`, then `source .venv/bin/activate`.

## Run

```bash
python selftest.py
```

All 23 checks should pass (1 is skipped on Windows). The first run downloads the 8 MB hand model.

```bash
python main.py --no-serial
```

Camera window plus the on-screen LED board, no hardware needed. Press `q` to quit.

With the ESP32 plugged in, close the Arduino Serial Monitor first (only one program can
open the port), then:

```bash
python main.py
```

The port is auto-detected; if it picks the wrong one, use `python main.py --port COM5`.
Other options: `--camera 1`, `--no-board`.

## Modes

`main.py` runs one mode at a time. Pick it with `--mode`:

| Command | What it does |
|---|---|
| `python main.py` | **gesture** (default): a shape for each gesture follows your hand |
| `python main.py --mode draw` | **draw**: draw on the board with your index finger |
| `python main.py --mode asl` | **asl**: recognise ASL letters (train first, see below) |

Add `--no-serial` to any of them to run without the ESP32.

## Drawing mode

```bash
python main.py --no-serial --mode draw
```

| Gesture | Action |
|---|---|
| point (index finger) | pen down: draw |
| open hand | pen up: move the cursor without drawing |
| peace | next colour (hold to keep stepping, once a second) |
| thumbs up | previous colour |
| fist, held for 1 second | clear the board |

The blinking dot on the board is the cursor: it follows your index fingertip. The camera
window shows pen up/down, the colour name and a swatch of it. The last colour in the
list is the eraser. Keys (click the camera window first): `c` clears, `s` saves the
drawing as a PNG, `q` quits.

To change which gesture does what, the colours, or the hold time, edit `DRAW_ACTIONS`,
`DRAW_PALETTE` and `CLEAR_HOLD_S` in `config.py`. If lines look wobbly, lower
`DRAW_SMOOTHING`; if fast strokes come out short or corners look rounded, raise it.

**On the real panel:** upload `firmware/draw_led/draw_led.ino` (see ESP32 below), then run
without `--no-serial`:

```bash
python main.py --mode draw
```

The panel shows the drawing and the blinking cursor. If the board still has an older
sketch on it, nothing breaks: older sketches ignore the drawing messages, and the panel
shows a white dot following your fingertip instead.

## ASL letters

You train the letter model yourself on your own hand and camera. In the `laptop` folder,
with the venv active (scikit-learn is in `requirements.txt`; rerun
`pip install -r requirements.txt` if you installed before it was added):

1. **Record.** Start with a few letters that look different:

   ```bash
   python record_asl.py A B L Y
   ```

   For each letter, make the sign and press SPACE to start recording. While it records,
   move your hand a little: closer, further, slightly tilted. It saves 200 samples per
   letter (`--samples` to change), then moves to the next letter. SPACE pauses, `n` skips
   a letter, `q` quits. Samples are appended to `asl_data.csv`, so you can record more in
   later sessions, or with other people's hands.

2. **Train.**

   ```bash
   python train_asl.py
   ```

   It prints the accuracy on samples it didn't train on, and which letters get mixed up.
   Record more of those letters and train again. It saves `asl_model.joblib`.

3. **Run.**

   ```bash
   python main.py --no-serial --mode asl
   ```

   The letter shows large in the top-right of the camera window, with the raw guess and
   confidence under the gesture line. `?` means the model is less than 60% sure
   (`ASL_MIN_CONFIDENCE` in `config.py`). Gestures still drive the LED board as before.

Add letters a few at a time. Letters that look alike (M, N, T, S) need more samples.
J and Z involve movement and won't work with this single-frame model.
`asl_data.csv` and `asl_model.joblib` can be committed so teammates can use them.

## ESP32

**Full sketch:** open `firmware/gesture_led/gesture_led.ino` in the Arduino IDE, install
**Adafruit Protomatter** from the Library Manager, and upload. Panel pins are the same as
`hackathon_rgbbox.ino`.

**For drawing mode,** upload `firmware/draw_led/draw_led.ino` instead. It does everything
`gesture_led.ino` does and adds drawing; the laptop tells it which mode to be in. Same
libraries, same wiring. No existing sketch is changed: it's a separate folder.

**Already have a sketch that works?** Copy `laptop_link.h` next to it and add three lines:

```cpp
#include "laptop_link.h"   // top of the file
LaptopLink laptop;         // under the include
laptop.poll();             // first line of loop()
```

Then use `laptop.gesture`, `laptop.is("OPEN")`, `laptop.x`, `laptop.y` (0..31) and
`laptop.changed()`. `Serial.begin(115200)` must be in `setup()`. Keep `delay()`s short, or
the panel reacts late. Send distance back with `laptop.sendDistance(cm)`.
(It's called `laptop`, not `link`, because `link` is already a function on the ESP32.)

To add drawing to a sketch that already uses `laptop_link.h`, copy `draw_link.h` next to
it too. The steps are in the comment at the top of that file: two new lines, one changed
line (`art.poll(laptop);` replaces `laptop.poll();`), and a few lines where the panel is drawn.

### Wiring notes

- **Ultrasonic pins moved.** The original `hackathon.ino` used pins 5 and 18 for the
  HC-SR04, but the panel uses those. The full sketch uses **TRIG = 22, ECHO = 23**.
- **ECHO is 5 V.** The ESP32 is 3.3 V. Put a divider on ECHO: 1 kΩ from ECHO to pin 23,
  and 2 kΩ from pin 23 to GND.
- **Panel power.** Power the panel from a 5 V supply rated 2 A or more, not the laptop's
  USB port. Keep brightness low when testing.

## Protocol

One text line per message, 115200 baud. Anything else on the line is ignored by both
sides, so debug `Serial.println`s are safe.

- laptop -> ESP32: `G <GESTURE> <x> <y>`, e.g. `G OPEN 12 20`. Sent on every change and
  every 0.5 s. If the ESP32 hears nothing for 2 s it goes back to `NONE`.
- Drawing mode adds, laptop -> ESP32 (read by `draw_link.h`; older sketches ignore them):
  - `M DRAW` / `M GESTURE`: which mode the laptop is in, sent once a second.
  - `P <x> <y> <r> <g> <b>`: paint one pixel. Sent the moment it changes.
  - `C`: clear the drawing.
  - `K <x> <y> <r> <g> <b>`: cursor position and pen colour.
  - `R <y> <128 hex digits>`: one whole row of the drawing. The laptop re-sends one row
    every 0.1 s (the whole picture every 3.2 s), so the panel repairs itself if a message
    was lost or the ESP32 was restarted or plugged in late.
- ESP32 -> laptop: `D <cm>`, e.g. `D 42.5` (`-1` = nothing in range).

## Checking the firmware without hardware

```bash
python tools/check_firmware.py
```

Needs `g++` (Linux/macOS, or WSL on Windows). It compiles the firmware headers with a
stand-in Arduino core and checks that:

- `laptop_link.h` reads good messages and ignores bad ones;
- `gesture_frames.h` draws the same pixels as the laptop's on-screen board;
- `draw_link.h`, fed a real drawing session's messages, shows exactly the laptop's
  picture and cursor, and recovers when a third of the pixel messages are thrown away;
- the older firmware is not disturbed by the drawing messages.

It does not compile the `.ino` sketches themselves; the Arduino IDE does that when you upload.
