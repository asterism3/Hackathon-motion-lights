"""All tunable settings in one place. Change values here, not in the other files."""

# --- Serial link to the ESP32 ---
SERIAL_PORT = None          # None = auto-detect. Or set e.g. "COM5" (Windows) / "/dev/ttyUSB0" (Linux)
BAUD = 115200
HEARTBEAT_S = 0.5           # resend the current gesture this often so the ESP32 knows we're alive

# --- Camera ---
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
MIRROR = True               # flip the image so moving your hand right moves the dot right

# --- Hand tracking ---
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
MODEL_PATH = "hand_landmarker.task"   # downloaded automatically on first run
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.5

# --- Gesture stability ---
STABLE_FRAMES = 3           # a new gesture must be seen this many frames in a row before it counts
SMOOTHING = 0.4             # 0..1, how fast x/y follow the hand (1 = no smoothing)

# --- ASL letters (python main.py --asl) ---
ASL_DATA_PATH = "asl_data.csv"      # written by record_asl.py
ASL_MODEL_PATH = "asl_model.joblib" # written by train_asl.py
ASL_MIN_CONFIDENCE = 0.6            # below this the letter shows as "?"

# --- Drawing mode (python main.py --mode draw) ---
# The pen colours, in the order the colour gestures step through them.
DRAW_PALETTE = [
    ("red", (255, 0, 0)),
    ("orange", (255, 128, 0)),
    ("yellow", (255, 255, 0)),
    ("green", (0, 255, 0)),
    ("cyan", (0, 255, 255)),
    ("blue", (0, 0, 255)),
    ("purple", (160, 0, 255)),
    ("white", (255, 255, 255)),
    ("eraser", (0, 0, 0)),
]
# What each gesture does. Actions: "draw", "move", "next_color", "prev_color", "clear".
# Swap the gestures around here; nothing else needs to change.
DRAW_ACTIONS = {
    "POINT": "draw",            # index finger out: pen down
    "OPEN": "move",             # open hand: move the cursor without drawing
    "PEACE": "next_color",
    "THUMBS_UP": "prev_color",
    "FIST": "clear",            # must be held for CLEAR_HOLD_S
}
CLEAR_HOLD_S = 1.0              # hold the clear gesture this long, so it can't happen by accident
COLOR_REPEAT_S = 1.0            # holding a colour gesture steps again this often
DRAW_SMOOTHING = 0.5            # like SMOOTHING, for draw mode: higher = follows fast strokes
                                # better (sharper corners), lower = steadier lines

# --- LED panel (must match the firmware) ---
PANEL_W = 32
PANEL_H = 32
SIM_SCALE = 14              # on-screen board: pixels per LED
