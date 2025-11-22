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

# ---------- THUMB pravila (samo za THUMBS_UP) ----------
THUMB_INLINE_TH = 165  # MCP–IP–TIP inline prag (160–175)
THUMB_SPREAD_TH = 80   # ugao izmedju pinky knuckle i thumb joint (>=80)
THUMB_TIP_EXT_SIMPLE_TH = 1.10  # prag za "palac otvoren" u OPEN/HALF (probaj 1.0–1.2)
# ------------------------------------------------------

# ---------- SWIPE parametri (asimetrični, TIP-ovi) ----------
SWIPE_WINDOW = 8

# vertikalni pragovi (UP/DOWN lakši)
SWIPE_MIN_FACTOR_Y = 0.55   # * hand_size (0.45–0.70)

# horizontalni pragovi (LEFT/RIGHT teži)
SWIPE_MIN_FACTOR_X = 1.05   # * hand_size (0.9–1.4)

# dominantnost ose
SWIPE_AXIS_RATIO_Y = 1.2    # vertikala tolerantnija
SWIPE_AXIS_RATIO_X = 1.7    # horizontala stroža

SWIPE_COOLDOWN = 0.6
# ------------------------------------------------------------

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
    """Referentna veličina ruke: wrist <-> middle_mcp (u pikselima)."""
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

    Palac je "otvoren prst" za OPEN_PALM / HALF_OPEN,
    ali se NE računa u zatvorenost šake (da THUMBS_UP radi).
    """
    pts = landmarks_to_pixels(landmarks, w, h)
    sz = hand_size(pts)
    if sz < 1e-6:
        return "UNKNOWN", 0.0

    # ---- 1) 4 prsta (bez palca) ----
    finger_norms = [finger_tip_norm_dist(pts, tip) for tip in FINGER_TIPS]
    fingers_ext = [d > FINGER_TIP_EXT_TH for d in finger_norms]
    ext_count4 = sum(1 for e in fingers_ext if e)

    # ---- 2) palac kao "otvoren prst" za OPEN/HALF ----
    thumb_norm = finger_tip_norm_dist(pts, THUMB_TIP)
    thumb_ext_simple = (thumb_norm > THUMB_TIP_EXT_SIMPLE_TH)

    # ---- 3) custom palac samo za THUMBS_UP ----
    thumb_ext_custom, _, _ = thumb_is_extended_custom(pts)

    # ---- 4) openness score (4 prsta) ----
    open_score = openness_score(pts)

    # ---------- OPEN PALM: 4 prsta otvorena + palac otvoren ----------
    if ext_count4 == 4 and thumb_ext_simple and open_score >= OPEN_SCORE_TH:
        conf = min(1.0, (open_score - OPEN_SCORE_TH) / 0.4 + 0.6)
        return "OPEN_PALM", conf

    # ---------- CLOSED HAND ili THUMBS UP ----------
    # zatvorena šaka se gleda SAMO po 4 prsta
    if ext_count4 == 0 and open_score <= CLOSED_SCORE_TH:
        if thumb_ext_custom:
            return "THUMBS_UP", 1.0
        else:
            conf = min(1.0, (CLOSED_SCORE_TH - open_score) / 0.3 + 0.6)
            return "CLOSED_HAND", conf

    # ---------- HALF OPEN ----------
    # računamo otvaranje uključujući palac
    ext_count5 = ext_count4 + (1 if thumb_ext_simple else 0)
    if ext_count5 >= 2:
        conf = ext_count5 / 5.0
        return "HALF_OPEN", conf

    return "UNKNOWN", ext_count5 / 5.0

def fingertip_centroid_px(pts):
    """Centroid 4 fingertip-a u pikselima."""
    xs = [pts[t][0] for t in FINGER_TIPS]
    ys = [pts[t][1] for t in FINGER_TIPS]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def detect_swipe_from_tips(tip_traj, hand_sz_px):
    """
    Swipe se računa SAMO iz kretanja TIP centroida.
    tip_traj: deque of (x,y) centroid TIP-ova
    """
    if len(tip_traj) < 2:
        return None, 0.0

    x0, y0 = tip_traj[0]
    x1, y1 = tip_traj[-1]

    dx = x1 - x0
    dy = y1 - y0

    min_y = hand_sz_px * SWIPE_MIN_FACTOR_Y
    min_x = hand_sz_px * SWIPE_MIN_FACTOR_X

    adx, ady = abs(dx), abs(dy)

    # 1) PRIORITET: UP/DOWN (lakši prag, tolerantniji ratio)
    if ady >= min_y and ady > adx * SWIPE_AXIS_RATIO_Y:
        return ("SWIPE_DOWN" if dy > 0 else "SWIPE_UP"), ady / min_y

    # 2) LEFT/RIGHT (teži prag, strožiji ratio)
    if adx >= min_x and adx > ady * SWIPE_AXIS_RATIO_X:
        return ("SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"), adx / min_x

    return None, 0.0


def main():
    cap = cv2.VideoCapture(CAM_ID)
    if not cap.isOpened():
        print("Ne mogu otvoriti kameru.")
        return

    # smoothing/debounce za statične gestove
    state_deques = {}
    current_majority = {}
    majority_start = {}
    triggered_flag = {}

    # swipe state po ruci (samo tipovi)
    tip_traj_deques = {}
    last_swipe_time = {}

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

                    # -------- STATIC gesture --------
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
                            # print(f"[{time.strftime('%H:%M:%S')}] HAND {i}: {majority_label} (conf~{conf:.2f})")
                            triggered_flag[i] = True
                    else:
                        triggered_flag[i] = False

                    # -------- SWIPE tracking (TIP-ovi) --------
                    pts_px = landmarks_to_pixels(hand_landmarks.landmark, w, h)
                    tip_px = fingertip_centroid_px(pts_px)
                    hand_sz_px = hand_size(pts_px)

                    if i not in tip_traj_deques:
                        tip_traj_deques[i] = deque(maxlen=SWIPE_WINDOW)
                        last_swipe_time[i] = 0.0

                    tip_traj_deques[i].append(tip_px)

                    swipe_label, swipe_strength = detect_swipe_from_tips(
                        tip_traj_deques[i], hand_sz_px
                    )

                    if swipe_label is not None and (now - last_swipe_time[i]) > SWIPE_COOLDOWN:
                        print(f"[{time.strftime('%H:%M:%S')}] HAND {i}: {swipe_label} (strength~{swipe_strength:.2f})")
                        last_swipe_time[i] = now
                        tip_traj_deques[i].clear()

                    # -------- overlay --------
                    xs = [lm.x for lm in hand_landmarks.landmark]
                    ys = [lm.y for lm in hand_landmarks.landmark]
                    min_x, min_y = int(min(xs) * w), int(min(ys) * h)

                    color = (0, 255, 0) if majority_label != "UNKNOWN" else (0, 0, 255)
                    cv2.putText(
                        frame, f"{majority_label}",
                        (min_x, max(20, min_y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
                    )

            cv2.imshow("Simple Hand States + Tip Swipe", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
