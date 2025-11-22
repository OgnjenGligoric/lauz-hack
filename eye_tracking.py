import cv2
import mediapipe as mp
import math
import time
from collections import deque

# ------------ Konfiguracija ------------
CAM_ID = 0             # koji camera device (0 = default)
MAX_NUM_HANDS = 2
MIN_DET_CONF = 0.5
MIN_TRACK_CONF = 0.5

FOLD_THRESHOLD = 0.65  # prag za normiranu dist(tip, wrist)/hand_size < threshold => prst "skupljen"
FINGERS_FOR_FIST = 4   # koliko prstiju treba biti "folded" da bude fist (obično 4/5)
SMOOTH_FRAMES = 6      # koliko frame-ova koristiti za majority smoothing
DEBOUNCE_TIME = 0.25   # sec - koliko dugo treba fist biti kontinuirano pre nego sto se trigger-uje
# ---------------------------------------

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Indeksi landmarka (MediaPipe Hands)
WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20
MIDDLE_MCP = 9
TIPS = [THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]

def euclid(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def hand_size_pixels(pts):
    # referentna veličina: wrist <-> middle_mcp
    return euclid(pts[WRIST], pts[MIDDLE_MCP])

def is_fist_from_landmarks(landmarks, image_w, image_h, fold_threshold=FOLD_THRESHOLD):
    """
    Vraca (is_fist_flag, confidence) gde je confidence fraction prstiju koji su 'folded'.
    landmarks: list od 21 normalizovanih landmarka
    """
    pts = [(lm.x * image_w, lm.y * image_h) for lm in landmarks]
    wrist = pts[WRIST]
    size = hand_size_pixels(pts)
    if size < 1e-6:
        return False, 0.0

    folded = 0
    for tip_idx in TIPS:
        tip = pts[tip_idx]
        dist_norm = euclid(tip, wrist) / size
        if dist_norm < fold_threshold:
            folded += 1

    conf = folded / 5.0
    return (folded >= FINGERS_FOR_FIST), conf

def main():
    cap = cv2.VideoCapture(CAM_ID)
    if not cap.isOpened():
        print("Ne mogu otvoriti kameru. Proveri CAM_ID.")
        return

    # Za svaku ruku (po indexu), cuvamo deque poslednjih N boolean vrednosti za smoothing
    hand_state_deques = {}  # key: hand_index (0..), value: deque
    hand_last_state = {}    # key: hand_index, value: current majority boolean
    hand_fist_start_time = {}  # key: hand_index, value: timestamp kada fist postao True (for debounce)
    hand_triggered = {}     # key: hand_index, value: True ako smo vec triggerovali dok traje fist

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=MAX_NUM_HANDS,
        min_detection_confidence=MIN_DET_CONF,
        min_tracking_confidence=MIN_TRACK_CONF
    ) as hands:
        print("Start kamera. Pritisni ESC za izlaz.")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)  # mirror
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            detected_any = False
            # reset if nema ruke
            current_hand_indices = []

            if results.multi_hand_landmarks:
                for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                    # In MediaPipe, hand_landmarks correspond to detected hands but index i is only for iteration.
                    # We will use i as identifier for a given frame; persistent mapping across frames relies on tracking in Mediapipe.
                    detected_any = True
                    current_hand_indices.append(i)

                    # Draw landmarks
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    fist_flag, conf = is_fist_from_landmarks(hand_landmarks.landmark, w, h)
                    # init if not present
                    if i not in hand_state_deques:
                        hand_state_deques[i] = deque(maxlen=SMOOTH_FRAMES)
                        hand_last_state[i] = False
                        hand_fist_start_time[i] = None
                        hand_triggered[i] = False

                    hand_state_deques[i].append(fist_flag)
                    # majority smoothing
                    states = hand_state_deques[i]
                    majority = sum(states) >= (len(states) // 2 + 1)
                    prev = hand_last_state[i]
                    hand_last_state[i] = majority

                    # Debounce logic
                    now = time.time()
                    if majority:
                        if hand_fist_start_time[i] is None:
                            hand_fist_start_time[i] = now
                        elapsed = now - hand_fist_start_time[i]
                        if elapsed >= DEBOUNCE_TIME and not hand_triggered[i]:
                            # trigger once
                            timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
                            print(f"[{timestamp_str}] HAND {i}: FIST detected! confidence={conf:.2f}")
                            # Mozes ovde staviti callback, websocket emit itd.
                            hand_triggered[i] = True
                            # vizualno označiti
                            cv2.putText(frame, f"HAND {i}: FIST!", (10, 30 + 30*i), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,255,0), 2)
                    else:
                        # reset start time i triggered flag kada ruka više nije fist
                        hand_fist_start_time[i] = None
                        hand_triggered[i] = False

                    # opcionalno: ispisi confidence tekst pored ruke (tipično uz landmark bounding)
                    # nalazimo bounding box to draw label near
                    x_coords = [lm.x for lm in hand_landmarks.landmark]
                    y_coords = [lm.y for lm in hand_landmarks.landmark]
                    min_x, min_y = int(min(x_coords) * w), int(min(y_coords) * h)
                    cv2.putText(frame, f"{'FIST' if majority else 'open'} {conf:.2f}", (min_x, min_y-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

            # If no hands detected currently, we could optionally clear per-hand structures or keep them.
            # Here ne brisemo hand_state_deques jer Mediapipe reuses hand indices reasonably; ali ako zelis robustno
            # mapiranje hands across frames, koristi results.multi_handedness (left/right) + persistent IDs.

            # Show frame
            cv2.imshow("Fist detector (MediaPipe)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
