import cv2
import mediapipe as mp
import math
import time
from collections import deque

# ----------------- Konfiguracija -----------------
CAM_ID = 0
MAX_NUM_HANDS = 2
MIN_DET_CONF = 0.5
MIN_TRACK_CONF = 0.5

SMOOTH_FRAMES = 8
DEBOUNCE_TIME = 0.30

# Pragovi (orijentaciono-nezavisni, bazirani na distancama)
FINGER_TIP_EXT_TH = 1.45   # > => prst ispruzen (probaj 1.35–1.60)
OPEN_SCORE_TH     = 1.55   # prosek tip dist za otvorenu saku (4 prsta)
CLOSED_SCORE_TH   = 1.20   # prosek tip dist za pesnicu

# ---------- THUMB pravila (SABO za THUMBS_UP) ----------
THUMB_INLINE_TH = 160  # MCP–IP–TIP inline prag (160–175)
THUMB_SPREAD_TH = 70   # ugao izmedju pinky knuckle i thumb joint (>=80)
# ------------------------------------------------------

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Landmarks (MediaPipe Hands)
WRIST = 0

THUMB_MCP = 2
THUMB_IP  = 3
THUMB_TIP = 4

INDEX_TIP  = 8
MIDDLE_TIP = 12
RING_TIP   = 16
PINKY_TIP  = 20

MIDDLE_MCP = 9
PINKY_MCP  = 17

FINGER_TIPS = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def landmarks_to_pixels(landmarks, image_w, image_h):
    return [(lm.x * image_w, lm.y * image_h, lm.z) for lm in landmarks]


def hand_size(pts):
    """Referentna veličina ruke: wrist <-> middle_mcp"""
    return euclid(pts[WRIST], pts[MIDDLE_MCP])


def finger_tip_norm_dist(pts, tip_idx):
    """Normalizovana distanca TIP-a od WRIST-a."""
    sz = hand_size(pts)
    if sz < 1e-6:
        return 0.0
    return euclid(pts[tip_idx][:2], pts[WRIST][:2]) / sz


def openness_score(pts):
    """Prosek normalizovanih distanci 4 prsta od wrist-a."""
    dists = [finger_tip_norm_dist(pts, tip) for tip in FINGER_TIPS]
    return sum(dists) / len(dists)


def angle_deg(a, b, c):
    """Ugao ABC u stepenima (2D)."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    cx, cy = c[0], c[1]

    ba = (ax - bx, ay - by)
    bc = (cx - bx, cy - by)

    dot = ba[0] * bc[0] + ba[1] * bc[1]
    norm_ba = math.hypot(ba[0], ba[1])
    norm_bc = math.hypot(bc[0], bc[1])

    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return 0.0

    cosang = dot / (norm_ba * norm_bc)
    cosang = max(-1.0, min(1.0, cosang))
    return math.degrees(math.acos(cosang))


def thumb_is_extended_custom(pts):
    """
    Palac je extended ako:
    1) (THUMB_MCP, THUMB_IP, THUMB_TIP) su inline (ugao blizu 180)
    2) ugao na wrist-u izmedju pinky_mcp i thumb_mcp >= THUMB_SPREAD_TH
    """
    wrist = pts[WRIST][:2]

    thumb_mcp = pts[THUMB_MCP][:2]
    thumb_ip  = pts[THUMB_IP][:2]
    thumb_tip = pts[THUMB_TIP][:2]

    pinky_mcp = pts[PINKY_MCP][:2]

    inline_ang = angle_deg(thumb_mcp, thumb_ip, thumb_tip)
    spread_ang = angle_deg(pinky_mcp, wrist, thumb_mcp)

    thumb_ext = (inline_ang >= THUMB_INLINE_TH) and (spread_ang >= THUMB_SPREAD_TH)
    return thumb_ext, inline_ang, spread_ang


def classify_simple(landmarks, w, h):
    """
    Vraca: OPEN_PALM, CLOSED_HAND, THUMBS_UP, HALF_OPEN, UNKNOWN

    OPEN_PALM IGNORIŠE PALAC.
    Palac se koristi samo za THUMBS_UP kad je šaka zatvorena.
    """
    pts = landmarks_to_pixels(landmarks, w, h)
    sz = hand_size(pts)
    if sz < 1e-6:
        return "UNKNOWN", 0.0

    # 1) Status 4 prsta preko tip->wrist distance
    finger_norms = [finger_tip_norm_dist(pts, tip) for tip in FINGER_TIPS]
    fingers_ext = [d > FINGER_TIP_EXT_TH for d in finger_norms]
    ext_count = sum(1 for e in fingers_ext if e)

    # 2) Thumb po custom pravilu (koristi se samo u zatvorenoj šaci)
    thumb_ext, thumb_inline_ang, thumb_spread_ang = thumb_is_extended_custom(pts)

    # 3) Globalni openness (samo 4 prsta)
    open_score = openness_score(pts)

    # --- OPEN PALM: sva 4 prsta ispruzena + openness visok (palac ignorišemo)
    if ext_count == 4 and open_score >= OPEN_SCORE_TH:
        conf = min(1.0, (open_score - OPEN_SCORE_TH) / 0.4 + 0.6)
        return "OPEN_PALM", conf

    # --- CLOSED HAND ili THUMBS UP:
    if ext_count == 0 and open_score <= CLOSED_SCORE_TH:
        if thumb_ext:
            return "THUMBS_UP", 1.0
        else:
            conf = min(1.0, (CLOSED_SCORE_TH - open_score) / 0.3 + 0.6)
            return "CLOSED_HAND", conf

    # --- HALF OPEN: bar 2 prsta ispruzena (relaksirana ruka)
    if ext_count >= 2:
        conf = ext_count / 4.0
        return "HALF_OPEN", conf

    return "UNKNOWN", ext_count / 4.0


def main():
    cap = cv2.VideoCapture(CAM_ID)
    if not cap.isOpened():
        print("Ne mogu otvoriti kameru.")
        return

    state_deques = {}
    current_majority = {}
    majority_start = {}
    triggered_flag = {}

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=MAX_NUM_HANDS,
        min_detection_confidence=MIN_DET_CONF,
        min_tracking_confidence=MIN_TRACK_CONF
    ) as hands:
        print("Pokrecem kameru... ESC za izlaz.")
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            if results.multi_hand_landmarks:
                for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    gesture_label, conf = classify_simple(hand_landmarks.landmark, w, h)

                    if i not in state_deques:
                        state_deques[i] = deque(maxlen=SMOOTH_FRAMES)
                        current_majority[i] = "UNKNOWN"
                        majority_start[i] = time.time()
                        triggered_flag[i] = False

                    state_deques[i].append(gesture_label)

                    votes = {}
                    for lab in state_deques[i]:
                        votes[lab] = votes.get(lab, 0) + 1
                    majority_label = max(votes.items(), key=lambda x: x[1])[0]

                    now = time.time()
                    prev_majority = current_majority.get(i, "UNKNOWN")

                    if majority_label != prev_majority:
                        current_majority[i] = majority_label
                        majority_start[i] = now
                        triggered_flag[i] = False

                    if majority_label != "UNKNOWN":
                        if (now - majority_start.get(i, now)) >= DEBOUNCE_TIME and not triggered_flag[i]:
                            print(f"[{time.strftime('%H:%M:%S')}] HAND {i}: {majority_label} (conf~{conf:.2f})")
                            triggered_flag[i] = True
                    else:
                        triggered_flag[i] = False

                    xs = [lm.x for lm in hand_landmarks.landmark]
                    ys = [lm.y for lm in hand_landmarks.landmark]
                    min_x, min_y = int(min(xs) * w), int(min(ys) * h)

                    color = (0, 255, 0) if majority_label != "UNKNOWN" else (0, 0, 255)
                    cv2.putText(
                        frame, f"{majority_label}",
                        (min_x, max(20, min_y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
                    )

            cv2.imshow("Simple Hand States", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
