"""Hand tracking -> LED board.

  python main.py                 gesture mode, ESP32 plugged in
  python main.py --no-serial     camera + on-screen board only
  python main.py --mode draw     draw in the air with your index finger
  python main.py --mode asl      recognise ASL letters (train first)

Click the camera window, then press q or Esc to quit.
Draw mode keys: c = clear, s = save the drawing as a PNG.
"""
import argparse
import sys
import time

import camera
import cv2

import board_view
import config
import gestures
from link import NullLink, SerialLink


def parse_args():
    p = argparse.ArgumentParser(description="Hand gestures -> 32x32 LED board")
    p.add_argument("--no-serial", action="store_true", help="don't talk to the ESP32")
    p.add_argument("--port", help="serial port, e.g. COM5 (default: auto-detect)")
    p.add_argument("--camera", type=int, default=config.CAMERA_INDEX, help="camera index (default 0)")
    p.add_argument("--no-board", action="store_true", help="hide the on-screen LED board")
    p.add_argument("--mode", choices=("gesture", "draw", "asl"), default="gesture",
                   help="gesture: shapes follow your hand (default). draw: draw with your "
                        "index finger. asl: recognise letters (train first)")
    p.add_argument("--asl", action="store_true", help="same as --mode asl")
    args = p.parse_args()
    if args.asl:
        args.mode = "asl"
    return args


def draw_mode_overlay(frame, art, lx, ly):
    """Status text, a swatch of the pen colour, and the hold-to-clear bar."""
    pen = "pen DOWN" if art.pen_down else "pen up"
    cv2.putText(frame, f"DRAW  {pen}  {art.color_name}  ({lx},{ly})", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    w = frame.shape[1]
    r, g, b = art.color
    cv2.rectangle(frame, (w - 70, 10), (w - 10, 70), (b, g, r), -1)     # OpenCV wants B, G, R
    cv2.rectangle(frame, (w - 70, 10), (w - 10, 70), (255, 255, 255), 2)
    if art.clear_progress > 0:
        cv2.putText(frame, "hold to clear", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.rectangle(frame, (10, 75), (10 + int(200 * art.clear_progress), 90), (0, 0, 255), -1)
        cv2.rectangle(frame, (10, 75), (210, 90), (255, 255, 255), 1)


def main():
    args = parse_args()
    from tracker import HandTracker, draw_hand   # imported here so --help works without MediaPipe

    letters = letter_filter = art = None
    if args.mode == "draw":
        from drawing import Drawing
        art = Drawing()
    if args.mode == "asl":
        import asl
        try:
            letters = asl.ASLClassifier()
        except (FileNotFoundError, RuntimeError) as e:
            print(e)
            return 1
        letter_filter = gestures.GestureFilter(config.STABLE_FRAMES)

    if args.no_serial:
        link = NullLink()
    else:
        try:
            link = SerialLink(port=args.port)
            print(f"Connected to ESP32 on {link.port}")
        except Exception as e:
            print(f"Serial error: {e}")
            print("Tip: close the Arduino Serial Monitor (only one program can use the port), "
                  "or run with --no-serial.")
            return 1

    cap = camera.open_camera(args.camera)
    if cap is None:
        print(camera.camera_help(args.camera))
        link.close()
        return 1

    tracker = HandTracker()
    filt = gestures.GestureFilter(
        config.STABLE_FRAMES, config.DRAW_SMOOTHING if art is not None else config.SMOOTHING)
    lx, ly = config.PANEL_W // 2, config.PANEL_H // 2
    try:
        while True:
            ok, frame = camera.read_frame(cap)
            if not ok:
                print("Camera stopped sending frames.\n" + camera.camera_help(args.camera))
                break
            if config.MIRROR:
                frame = cv2.flip(frame, 1)

            raw, x, y, lm = tracker.process(frame)
            if art is not None and lm is not None:
                x, y = lm[8].x, lm[8].y          # draw mode: always follow the index fingertip
            if lm is None:
                filt.x = filt.y = None           # hand gone: next time, jump straight to it
            gesture = filt.update(raw, x, y)
            if filt.x is not None:
                lx, ly = gestures.to_led(filt.x, filt.y, config.PANEL_W, config.PANEL_H)
            now = time.monotonic()

            link.poll()
            if art is not None:
                art.update(gesture, lx, ly, now, raw=raw)
                # The real panel can't show the drawing yet (that's the next step), so
                # for now it shows a white dot that follows your fingertip.
                link.send("NONE" if gesture == "NONE" else "POINT", lx, ly)
            else:
                link.send(gesture, lx, ly)

            if lm is not None:
                draw_hand(frame, lm)
            dist = f"{link.distance_cm:.0f} cm" if link.distance_cm > 0 else "-"
            if art is not None:
                draw_mode_overlay(frame, art, lx, ly)
            else:
                cv2.putText(frame, f"{gesture}  ({lx},{ly})  dist {dist}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            if letters is not None:
                letter, conf = letters.predict(lm) if lm is not None else ("-", 0.0)
                shown = letter_filter.update(letter)
                cv2.putText(frame, shown, (frame.shape[1] - 110, 110),
                            cv2.FONT_HERSHEY_SIMPLEX, 3.5, (255, 255, 0), 6)
                cv2.putText(frame, f"ASL {letter} {conf:.0%}", (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.imshow("Camera", frame)
            if not args.no_board:
                if art is not None:
                    board_view.show_image(art.render(now))
                else:
                    board_view.show(gesture, lx, ly, link.distance_cm)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if art is not None and key == ord("c"):
                art.clear()
            if art is not None and key == ord("s"):
                name = time.strftime("drawing_%Y%m%d_%H%M%S.png")
                cv2.imwrite(name, board_view.scale_up(art.canvas))
                print(f"Saved {name}")
    finally:
        tracker.close()
        cap.release()
        link.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
