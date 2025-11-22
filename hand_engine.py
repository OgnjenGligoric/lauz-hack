import cv2
import mediapipe as mp
import math
import time
from collections import deque

MAX_NUM_HANDS = 2
MIN_DET_CONF = 0.5
MIN_TRACK_CONF = 0.5
SMOOTH_FRAMES = 8
DEBOUNCE_TIME = 0.30

# Tresholds
FINGER_TIP_EXT_TH = 1.45
OPEN_SCORE_TH = 1.55
CLOSED_SCORE_TH = 1.20
THUMB_TIP_EXT_SIMPLE_TH = 1.10
THUMB_INLINE_TH = 165
THUMB_SPREAD_TH = 80

# Swipe
SWIPE_WINDOW = 12
SWIPE_MIN_FACTOR_Y = 0.55
SWIPE_MIN_FACTOR_X = 1.05
SWIPE_AXIS_RATIO_Y = 1.2
SWIPE_AXIS_RATIO_X = 1.7
SWIPE_COOLDOWN = 1
SWIPE_OPPOSITE_LAG = 2

# Special Pose
SPECIAL_WINDOW = 6
SPECIAL_MAJ_FRAC = 0.7
SPECIAL_PREBLOCK_FRAC = 0.34
SPECIAL_EVENT_COOLDOWN = 1.5

# ================= MEDIAPIPE SETUP =================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Landmarks indices
WRIST = 0
THUMB_MCP, THUMB_IP, THUMB_TIP = 2, 3, 4
INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 8, 12, 16, 20
MIDDLE_MCP, PINKY_MCP = 9, 17
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


def angle_deg(a, b, c):
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])
    norm_ba = math.hypot(*ba)
    norm_bc = math.hypot(*bc)
    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return 0.0
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    cosang = max(-1.0, min(1.0, dot / (norm_ba * norm_bc)))
    return math.degrees(math.acos(cosang))


def thumb_is_extended_custom(pts):
    inline_ang = angle_deg(pts[THUMB_MCP], pts[THUMB_IP], pts[THUMB_TIP])
    spread_ang = angle_deg(pts[PINKY_MCP], pts[WRIST], pts[THUMB_MCP])
    return (inline_ang >= THUMB_INLINE_TH and spread_ang >= THUMB_SPREAD_TH)


def classify_simple(landmarks, w, h):
    pts = landmarks_to_pixels(landmarks, w, h)
    sz = hand_size(pts)
    if sz < 1e-6:
        return "UNKNOWN", 0.0
    
    fingers_ext = [finger_tip_norm_dist(pts, tip) > FINGER_TIP_EXT_TH for tip in FINGER_TIPS]
    ext_count4 = sum(fingers_ext)
    thumb_simple = finger_tip_norm_dist(pts, THUMB_TIP) > THUMB_TIP_EXT_SIMPLE_TH
    thumb_custom = thumb_is_extended_custom(pts)
    open_score = openness_score(pts)

    if ext_count4 == 4 and thumb_simple and open_score >= OPEN_SCORE_TH:
        return "OPEN_PALM", 1.0
    if ext_count4 == 0 and open_score <= CLOSED_SCORE_TH:
        return ("THUMBS_UP", 1.0) if thumb_custom else ("CLOSED_HAND", 1.0)
    
    ext_count5 = ext_count4 + (1 if thumb_simple else 0)
    return ("HALF_OPEN", ext_count5 / 5.0) if ext_count5 >= 2 else ("UNKNOWN", 0.0)


def fingertip_centroid_px(pts):
    xs, ys = zip(*[pts[t][:2] for t in FINGER_TIPS])
    return (sum(xs) / 4, sum(ys) / 4)


def is_counterpart(prev_lab, new_lab):
    pairs = {
        ("SWIPE_UP", "SWIPE_DOWN"),
        ("SWIPE_DOWN", "SWIPE_UP"),
        ("SWIPE_LEFT", "SWIPE_RIGHT"),
        ("SWIPE_RIGHT", "SWIPE_LEFT"),
    }
    return (prev_lab, new_lab) in pairs


def detect_swipe_from_tips(tip_traj, hand_sz_px):
    if len(tip_traj) < 2:
        return None, 0.0

    dx = tip_traj[-1][0] - tip_traj[0][0]
    dy = tip_traj[-1][1] - tip_traj[0][1]
    min_y = hand_sz_px * SWIPE_MIN_FACTOR_Y
    min_x = hand_sz_px * SWIPE_MIN_FACTOR_X
    adx, ady = abs(dx), abs(dy)
    
    if ady >= min_y and ady > adx * SWIPE_AXIS_RATIO_Y:
        return ("SWIPE_DOWN" if dy > 0 else "SWIPE_UP"), ady / min_y
    
    if adx >= min_x and adx > ady * SWIPE_AXIS_RATIO_X:
        return ("SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT"), adx / min_x
    
    return None, 0.0


def detect_special_pose(pts_px):
    thumb_ext = finger_tip_norm_dist(pts_px, THUMB_TIP) > THUMB_TIP_EXT_SIMPLE_TH
    idx_ext = finger_tip_norm_dist(pts_px, INDEX_TIP) > FINGER_TIP_EXT_TH
    mid_ext = finger_tip_norm_dist(pts_px, MIDDLE_TIP) > FINGER_TIP_EXT_TH
    ring_ext = finger_tip_norm_dist(pts_px, RING_TIP) > FINGER_TIP_EXT_TH
    pinky_ext = finger_tip_norm_dist(pts_px, PINKY_TIP) > FINGER_TIP_EXT_TH
    
    return thumb_ext and idx_ext and pinky_ext and (not mid_ext) and (not ring_ext)


class HandTracker:
    def __init__(self):
        self.hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DET_CONF,
            min_tracking_confidence=MIN_TRACK_CONF
        )
        
        # State tracking
        self.state_deques = {}
        self.current_majority = {}
        self.majority_start = {}
        self.triggered_flag = {}
        
        self.tip_traj_deques = {}
        self.last_swipe_time = {}
        self.last_swipe_label = {}
        
        self.special_hist = {}
        self.last_special_time = {}
        
        self.CLOSED_SET = {"CLOSED_HAND", "THUMBS_UP"}

    def process(self, frame):

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb)
        
        events = []

        if results.multi_hand_landmarks:
            for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                mp_drawing.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    mp_hands.HAND_CONNECTIONS
                )
                
                gesture_label, _ = classify_simple(hand_landmarks.landmark, w, h)
                
                if i not in self.state_deques:
                    self.state_deques[i] = deque(maxlen=SMOOTH_FRAMES)
                    self.current_majority[i] = "UNKNOWN"
                    self.majority_start[i] = time.time()
                    self.triggered_flag[i] = False
                
                self.state_deques[i].append(gesture_label)
                votes = {l: self.state_deques[i].count(l) for l in self.state_deques[i]}
                majority_label = max(votes, key=votes.get)
                
                now = time.time()
                if majority_label != self.current_majority[i]:
                    self.current_majority[i] = majority_label
                    self.majority_start[i] = now
                    self.triggered_flag[i] = False
                
                pts_px = landmarks_to_pixels(hand_landmarks.landmark, w, h)
                tip_px = fingertip_centroid_px(pts_px)
                hand_sz = hand_size(pts_px)
                
                if i not in self.special_hist:
                    self.special_hist[i] = deque(maxlen=SPECIAL_WINDOW)
                    self.last_special_time[i] = 0.0
                
                sp_ok = detect_special_pose(pts_px)
                self.special_hist[i].append(1 if sp_ok else 0)
                
                sp_votes = sum(self.special_hist[i])
                sp_forming = sp_votes >= SPECIAL_WINDOW * SPECIAL_PREBLOCK_FRAC
                sp_majority = sp_votes >= SPECIAL_WINDOW * SPECIAL_MAJ_FRAC
                
                if sp_majority and (now - self.last_special_time[i] > SPECIAL_EVENT_COOLDOWN):
                    events.append(f"HAND_{i}_SPECIAL_POSE")
                    self.last_special_time[i] = now
                
                if not sp_forming:
                    if i not in self.tip_traj_deques:
                        self.tip_traj_deques[i] = deque(maxlen=SWIPE_WINDOW)
                        self.last_swipe_time[i] = 0.0
                        self.last_swipe_label[i] = None
                    
                    self.tip_traj_deques[i].append(tip_px)
                    swipe_lbl, swipe_str = detect_swipe_from_tips(
                        self.tip_traj_deques[i], 
                        hand_sz
                    )
                    
                    if swipe_lbl in ("SWIPE_LEFT", "SWIPE_RIGHT") and majority_label in self.CLOSED_SET:
                        swipe_lbl = None
                    
                    if swipe_lbl is not None:
                        prev_swipe = self.last_swipe_label.get(i)
                        if prev_swipe and is_counterpart(prev_swipe, swipe_lbl):
                            if (now - self.last_swipe_time[i]) < SWIPE_OPPOSITE_LAG:
                                swipe_lbl = None
                    
                    if swipe_lbl and (now - self.last_swipe_time[i] > SWIPE_COOLDOWN):
                        events.append(f"HAND_{i}_{swipe_lbl}")
                        self.last_swipe_time[i] = now
                        self.last_swipe_label[i] = swipe_lbl
                        self.tip_traj_deques[i].clear()
                else:
                    if i in self.tip_traj_deques:
                        self.tip_traj_deques[i].clear()
                
                min_x = int(min([lm.x for lm in hand_landmarks.landmark]) * w)
                min_y = int(min([lm.y for lm in hand_landmarks.landmark]) * h)
                
                color = (0, 255, 0) if majority_label != "UNKNOWN" else (0, 0, 255)
                cv2.putText(
                    frame, 
                    majority_label, 
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

        return frame, events