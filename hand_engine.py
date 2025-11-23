import cv2
import mediapipe as mp
import math
import time
from collections import deque

MAX_NUM_HANDS = 1
MIN_DET_CONF = 0.5
MIN_TRACK_CONF = 0.5
SMOOTH_FRAMES = 8

# Thresholds (opuštenije)
FINGER_TIP_EXT_TH = 1.65
CLOSED_SCORE_TH = 1.20          # manje rigorozno
THUMB_TIP_EXT_SIMPLE_TH = 1.10

# Prag za "savijen prst" (opuštenije)
FINGER_TIP_CLOSED_TH = 1.32     # tolerise ugao

# Pointing params
POINT_AXIS_RATIO = 1.3
POINT_MIN_CONF = 0.35

# --- NEW: POINT_DOWN override when knuckles are up ---
POINT_DOWN_AXIS_RATIO = 1.1   # lakše okidanje down ose
POINT_DOWN_MIN_CONF   = 0.20   # index mora biti dovoljno ispruzen
# -----------------------------------------------------

# Special Pose
SPECIAL_WINDOW = 6
SPECIAL_MAJ_FRAC = 0.7
SPECIAL_PREBLOCK_FRAC = 0.34
SPECIAL_EVENT_COOLDOWN = 1.5

# Global action cooldown
ACTION_COOLDOWN = 0.5  # sekunde između bilo koja dva event-a

# ================= MEDIAPIPE SETUP =================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Landmarks indices
WRIST = 0
THUMB_TIP = 4

# add INDEX_PIP for stable pointing vector
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_TIP = 9, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20

FINGER_TIPS = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def landmarks_to_pixels(landmarks, image_w, image_h):
    return [(lm.x * image_w, lm.y * image_h, lm.z) for lm in landmarks]


def hand_size(pts):
    return euclid(pts[WRIST], pts[MIDDLE_MCP])


def finger_tip_norm_dist(pts, tip_idx):
    sz = hand_size(pts)
    return 0.0 if sz < 1e-6 else euclid(pts[tip_idx][:2], pts[WRIST][:2]) / sz


def openness_score(pts):
    return sum([finger_tip_norm_dist(pts, tip) for tip in FINGER_TIPS]) / 4


def classify_simple(landmarks, w, h):
    """
    Vraća samo:
      - "CLOSED_HAND"
      - "UNKNOWN"
    Opušten CLOSED_HAND:
      - bar 3/4 prsta savijena
      - open_score nizak
      - ne proveravamo palac (da radi pod uglom)
    """
    pts = landmarks_to_pixels(landmarks, w, h)
    sz = hand_size(pts)
    if sz < 1e-6:
        return "UNKNOWN", 0.0

    dists4 = [finger_tip_norm_dist(pts, tip) for tip in FINGER_TIPS]
    open_score = sum(dists4) / 4.0

    closed_count = sum(d < FINGER_TIP_CLOSED_TH for d in dists4)

    if closed_count >= 3 and open_score <= CLOSED_SCORE_TH:
        return "CLOSED_HAND", 1.0

    return "UNKNOWN", 0.0


def detect_special_pose(pts_px):
    """
    Trenutna special poza:
      - thumb + index + pinky extended
      - middle + ring folded
    """
    thumb_ext = finger_tip_norm_dist(pts_px, THUMB_TIP) > THUMB_TIP_EXT_SIMPLE_TH
    idx_ext   = finger_tip_norm_dist(pts_px, INDEX_TIP) > FINGER_TIP_EXT_TH
    mid_ext   = finger_tip_norm_dist(pts_px, MIDDLE_TIP) > FINGER_TIP_EXT_TH
    ring_ext  = finger_tip_norm_dist(pts_px, RING_TIP) > FINGER_TIP_EXT_TH
    pinky_ext = finger_tip_norm_dist(pts_px, PINKY_TIP) > FINGER_TIP_EXT_TH

    return thumb_ext and idx_ext and pinky_ext and (not mid_ext) and (not ring_ext)


def detect_pointing_direction(pts_px):
    """
    Pointing = index extended, middle/ring folded.

    NEW RULE:
    if index is clearly extended and its direction vector points strongly DOWN,
    return POINT_DOWN even if middle/ring look extended (knuckles up case).
    """
    idx_d  = finger_tip_norm_dist(pts_px, INDEX_TIP)
    mid_d  = finger_tip_norm_dist(pts_px, MIDDLE_TIP)
    ring_d = finger_tip_norm_dist(pts_px, RING_TIP)

    # index must be extended at least
    if idx_d <= FINGER_TIP_EXT_TH:
        return None, 0.0

    # stable vector along index: PIP -> TIP
    x0, y0, _ = pts_px[INDEX_PIP]
    x1, y1, _ = pts_px[INDEX_TIP]
    vx, vy = (x1 - x0), (y1 - y0)

    sz = hand_size(pts_px)
    if sz < 1e-6:
        return None, 0.0

    vlen_norm = math.hypot(vx, vy) / sz
    if vlen_norm < POINT_MIN_CONF:
        return None, 0.0

    ax, ay = abs(vx), abs(vy)

    # --------- POINT_DOWN OVERRIDE ---------
    # If finger points clearly down, ignore other fingers.
    if vy > 0 and ay > ax * POINT_DOWN_AXIS_RATIO and vlen_norm > POINT_DOWN_MIN_CONF:
        return "POINT_DOWN", vlen_norm
    # --------------------------------------

    # default strict rule: middle/ring must be folded
    mid_ext  = mid_d > FINGER_TIP_EXT_TH
    ring_ext = ring_d > FINGER_TIP_EXT_TH
    if mid_ext or ring_ext:
        return None, 0.0

    # normal axis decision
    if ay > ax * POINT_AXIS_RATIO:
        return ("POINT_DOWN" if vy > 0 else "POINT_UP"), vlen_norm
    if ax > ay * POINT_AXIS_RATIO:
        return ("POINT_RIGHT" if vx > 0 else "POINT_LEFT"), vlen_norm

    return None, 0.0


class HandTracker:
    def __init__(self):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=MIN_DET_CONF,
            min_tracking_confidence=MIN_TRACK_CONF
        )

        # smoothing za base (CLOSED/UNKNOWN)
        self.state_deque = deque(maxlen=SMOOTH_FRAMES)
        self.current_majority = "UNKNOWN"

        # special pose istorija
        self.special_hist = deque(maxlen=SPECIAL_WINDOW)
        self.last_special_time = 0.0

        # gating: poslednje NON-UNKNOWN stanje
        self.last_non_unknown_state = None

        # poslednje final stanje za prikaz
        self.last_final_state = None

        # global cooldown između event-a
        self.last_action_time = 0.0

    def process(self, frame):
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)

        events = []

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            base_label, _ = classify_simple(hand_landmarks.landmark, w, h)
            self.state_deque.append(base_label)
            votes = {l: self.state_deque.count(l) for l in self.state_deque}
            majority_label = max(votes, key=votes.get)
            self.current_majority = majority_label

            now = time.time()
            pts_px = landmarks_to_pixels(hand_landmarks.landmark, w, h)

            # ---------- SPECIAL POSE ----------
            sp_ok = detect_special_pose(pts_px)
            self.special_hist.append(1 if sp_ok else 0)
            sp_votes = sum(self.special_hist)
            sp_forming = sp_votes >= SPECIAL_WINDOW * SPECIAL_PREBLOCK_FRAC
            sp_majority = sp_votes >= SPECIAL_WINDOW * SPECIAL_MAJ_FRAC

            # ---------- POINTING ----------
            point_lbl = None
            if not sp_forming:
                point_lbl, _ = detect_pointing_direction(pts_px)

                # blokiraj POINT_UP ako je mali prst podignut
                pinky_ext = finger_tip_norm_dist(pts_px, PINKY_TIP) > FINGER_TIP_EXT_TH
                if point_lbl == "POINT_UP" and pinky_ext:
                    point_lbl = None

                # ako je SPECIAL aktivan, ne salji POINT_UP
                if sp_majority and point_lbl == "POINT_UP":
                    point_lbl = None

            # final state: SPECIAL > POINT > BASE
            if sp_majority:
                final_state = "SPECIAL_POSE"
            elif point_lbl:
                final_state = point_lbl
            else:
                final_state = majority_label

            # --------- EVENT GATING + GLOBAL COOLDOWN ------------
            if final_state != "UNKNOWN":
                if (now - self.last_action_time) >= ACTION_COOLDOWN:
                    if final_state != self.last_non_unknown_state:
                        if final_state == "SPECIAL_POSE":
                            if (now - self.last_special_time) > SPECIAL_EVENT_COOLDOWN:
                                events.append("SPECIAL_POSE")
                                self.last_special_time = now
                                self.last_non_unknown_state = final_state
                                self.last_action_time = now
                        else:
                            events.append(final_state)
                            self.last_non_unknown_state = final_state
                            self.last_action_time = now

            self.last_final_state = final_state

            # draw label
            min_x = int(min([lm.x for lm in hand_landmarks.landmark]) * w)
            min_y = int(min([lm.y for lm in hand_landmarks.landmark]) * h)

            color = (0, 255, 0) if final_state != "UNKNOWN" else (0, 0, 255)
            cv2.putText(
                frame,
                final_state,
                (min_x, max(20, min_y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2
            )

            if sp_ok:
                cv2.putText(
                    frame,
                    "SPECIAL_POSE",
                    (min_x, max(45, min_y - 35)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 0, 255),
                    2
                )
        else:
            self.last_final_state = "UNKNOWN"

        return frame, events


# if __name__ == "__main__":
#     cap = cv2.VideoCapture(0)
#     tracker = HandTracker()

#     if not cap.isOpened():
#         print("❌ Camera not found!")
#         exit()

#     print("🎥 Starting hand tracker... Press Q to quit.")

#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             break

#         frame, events = tracker.process(frame)

#         for ev in events:
#             print("EVENT:", ev)

#         cv2.imshow("Hand Tracking", frame)

#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break

#     cap.release()
#     cv2.destroyAllWindows()
