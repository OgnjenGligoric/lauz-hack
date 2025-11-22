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

SMOOTH_FRAMES = 6       # majority smoothing window
DEBOUNCE_TIME = 0.25    # seconds - koliko gesture treba trajati pre trigger-a

# pragovi (tweak po potrebi)
THUMB_DISTANCE_FACTOR = 0.5  # za utvrđivanje da li je palac "ekstendovan" (relativno hand_size)
THUMB_ABOVE_WRIST_FACTOR = 0.15  # koliko iznad zgloba da bude za thumbs-up
# -------------------------------------------------

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# Indeksi landmarka (MediaPipe Hands)
WRIST = 0
THUMB_TIP = 4
THUMB_IP = 3
INDEX_TIP = 8
INDEX_PIP = 6
MIDDLE_TIP = 12
MIDDLE_PIP = 10
RING_TIP = 16
RING_PIP = 14
PINKY_TIP = 20
PINKY_PIP = 18
MIDDLE_MCP = 9

TIP_INDICES = [THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP]

def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def hand_size(pts):
    """Referentna veličina ruke: wrist <-> middle_mcp"""
    return euclid(pts[WRIST], pts[MIDDLE_MCP])

def landmarks_to_pixels(landmarks, image_w, image_h):
    return [(lm.x * image_w, lm.y * image_h, lm.z) for lm in landmarks]

def finger_is_extended(landmarks_px, tip_idx, pip_idx):
    """
    Jednostavan heuristički test: prst je 'extended' ako je tip iznad (manji y) od PIP-a.
    Radi za index/middle/ring/pinky kad je dlan okrenut ka kameri.
    """
    tip_y = landmarks_px[tip_idx][1]
    pip_y = landmarks_px[pip_idx][1]
    return tip_y < pip_y  # manji y == više na slici

def thumb_is_extended(landmarks_px, hand_sz):
    """
    Heuristika za palac: ako je udaljenost palac_tip <-> index_mcp veća od frakcije hand_size,
    smatramo da je palac 'extended' (odvojen od dlana).
    """
    thumb_tip = landmarks_px[THUMB_TIP][:2]
    index_mcp = landmarks_px[5][:2]  # index_mcp je landmark 5
    dist = euclid(thumb_tip, index_mcp)
    return dist > hand_sz * THUMB_DISTANCE_FACTOR

def classify_gesture(landmarks, image_w, image_h):
    """
    Vraca jedan od labela: 'FIST', 'PALM', 'THUMBS_UP', 'UNKNOWN'
    i confidence (0..1) kao broj ekstenidovanih prstiju / 5 ili slično.
    """
    pts = landmarks_to_pixels(landmarks, image_w, image_h)
    wrist = pts[WRIST][:2]
    sz = hand_size(pts)
    if sz < 1e-6:
        return "UNKNOWN", 0.0

    # proveravamo status za svaki prst (osim palca koristimo tip < pip)
    idx_ext = finger_is_extended(pts, INDEX_TIP, INDEX_PIP)
    mid_ext = finger_is_extended(pts, MIDDLE_TIP, MIDDLE_PIP)
    ring_ext = finger_is_extended(pts, RING_TIP, RING_PIP)
    pinky_ext = finger_is_extended(pts, PINKY_TIP, PINKY_PIP)
    thumb_ext = thumb_is_extended(pts, sz)

    extended_count = sum([1 if idx_ext else 0,
                          1 if mid_ext else 0,
                          1 if ring_ext else 0,
                          1 if pinky_ext else 0,
                          1 if thumb_ext else 0])

    # FIST: vecina prstiju pogodjena kao "ne-extended"
    if extended_count <= 1:  # obično 0 ili 1 (palac može ostati ext)
        # confidence: koliko su svi savijeni -> (5 - extended_count) / 5
        conf = (5 - extended_count) / 5.0
        return "FIST", conf

    # PALM: vecina prstiju ekstendovana
    if extended_count >= 4:
        conf = extended_count / 5.0
        return "PALM", conf

    # THUMBS UP: palac ext, ostali su savijeni, i palac je iznad zgloba (y manji)
    other_folded = (not idx_ext) and (not mid_ext) and (not ring_ext) and (not pinky_ext)
    thumb_above_wrist = pts[THUMB_TIP][1] < wrist[1] - (sz * THUMB_ABOVE_WRIST_FACTOR)
    if thumb_ext and other_folded and thumb_above_wrist:
        return "THUMBS_UP", 1.0

    return "UNKNOWN", extended_count / 5.0

# --------- Real-time capture i smoothing/debounce ----------
def main():
    cap = cv2.VideoCapture(CAM_ID)
    if not cap.isOpened():
        print("Ne mogu otvoriti kameru. Proveri CAM_ID.")
        return

    # strukture po ruci (index iz trenutnog frame-a)
    state_deques = {}        # hand_index -> deque of last SMOOTH_FRAMES labels
    last_trigger_time = {}   # hand_index -> kada je zadnji put trigger-ovana detekcija
    triggered_flag = {}      # hand_index -> bool (da ne trigg-ujemo svaki frame)

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

            frame = cv2.flip(frame, 1)  # mirror za prirodniji osecaj
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb)

            # reset lista detektovanih ruku za ovaj frame
            detected_hand_indices = []

            if results.multi_hand_landmarks:
                for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
                    # crtanje
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    gesture_label, conf = classify_gesture(hand_landmarks.landmark, w, h)

                    # Inicijalizacija struktura po ruci ako ne postoje
                    if i not in state_deques:
                        state_deques[i] = deque(maxlen=SMOOTH_FRAMES)
                        last_trigger_time[i] = 0
                        triggered_flag[i] = False

                    # dodaj label u deque (možemo čuvati label kao string, ali za majority koristimo numeric mapping)
                    state_deques[i].append(gesture_label)
                    # majority vote iz deque
                    # find most common label in deque
                    votes = {}
                    for lab in state_deques[i]:
                        votes[lab] = votes.get(lab, 0) + 1
                    majority_label = max(votes.items(), key=lambda x: x[1])[0]

                    # debounce logika: ako majority_label traje dovoljno dugo -> trigger
                    now = time.time()
                    if majority_label != "UNKNOWN":
                        # ako promenjeno sa prethodne vrednosti, reset trigger flag
                        if not triggered_flag[i] or (now - last_trigger_time[i]) > 1.0:
                            # require minimal continuous time (DEBOUNCE_TIME) before print
                            # jednostavan nacin: proverimo da li u deque vec postoji >= half elements same label
                            count_label = votes.get(majority_label, 0)
                            if count_label >= (len(state_deques[i]) // 2 + 1):
                                # trigger
                                print(f"[{time.strftime('%H:%M:%S')}] HAND {i}: {majority_label} (conf~{conf:.2f})")
                                last_trigger_time[i] = now
                                triggered_flag[i] = True
                    else:
                        # reset flags kad je unknown
                        triggered_flag[i] = False

                    # prikaz label na slici pored ruke
                    # nalazimo minimalne koordinate landmaraka da znamo gde da iscrtamo
                    xs = [lm.x for lm in hand_landmarks.landmark]
                    ys = [lm.y for lm in hand_landmarks.landmark]
                    min_x, min_y = int(min(xs) * w), int(min(ys) * h)
                    cv2.putText(frame, f"{majority_label}", (min_x, max(10, min_y - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0) if majority_label!="UNKNOWN" else (0,0,255), 2)

                    detected_hand_indices.append(i)

            # cv2.imshow("Hand Gestures (Fist / Palm / Thumbs Up)", frame)
            # key = cv2.waitKey(1) & 0xFF
            # if key == 27:  # ESC
            #     break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
