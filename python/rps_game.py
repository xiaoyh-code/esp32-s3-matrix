import cv2
import numpy as np
import mediapipe as mp
import serial
import serial.tools.list_ports
import time
import sys
import random
import collections
import os
import pickle

# --- Config ---
MATRIX_W, MATRIX_H = 8, 8
BAUDRATE = 115200
SYNC_MARKER, CMD_FRAME = 0xAA, 0x01
MAX_ORDER = 5
COUNTDOWN_SEC = 0.7

ROCK, PAPER, SCISSORS, NONE = "rock", "paper", "scissors", "none"
BEATS = {ROCK: SCISSORS, SCISSORS: PAPER, PAPER: ROCK}
BEATEN_BY = {v: k for k, v in BEATS.items()}
GESTURE_COLORS = {ROCK: (30, 30, 255), PAPER: (30, 255, 30), SCISSORS: (255, 160, 30)}


# --- AI ---
class SmartAI:
    def __init__(self, max_order=MAX_ORDER):
        self.max_order = max_order
        self.transitions = {n: {} for n in range(1, max_order + 1)}
        self.history = []
        self.freq = collections.Counter()

    def record(self, move):
        for o in range(1, self.max_order + 1):
            if len(self.history) >= o:
                seq = tuple(self.history[-o:])
                self.transitions[o].setdefault(seq, collections.Counter())
                self.transitions[o][seq][move] += 1
        self.history.append(move)
        self.freq[move] += 1

    def predict(self):
        for o in range(self.max_order, 0, -1):
            if len(self.history) >= o:
                c = self.transitions[o].get(tuple(self.history[-o:]))
                if c: return c.most_common(1)[0][0]
        return self.freq.most_common(1)[0][0] if self.freq else random.choice([ROCK, PAPER, SCISSORS])

    def counter(self):
        return BEATEN_BY[self.predict()]

    def total(self):
        return sum(self.freq.values())

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump((self.transitions, self.history, self.freq, self.max_order), f)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path): return None
        with open(path, "rb") as f:
            t, h, g, o = pickle.load(f)
        ai = cls(o); ai.transitions = t; ai.history = h; ai.freq = g
        return ai


# --- Icons ---
def icon(lines):
    m = np.zeros((MATRIX_H, MATRIX_W), dtype=np.uint8)
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if x < MATRIX_W and ch == "1": m[y, x] = 1
    return m

I3 = icon(["01111100","00000110","00001100","00000110","00000110","00001100","00000110","01111100"])
I2 = icon(["01111100","00000110","00000110","01111100","01100000","01100000","01111110","00000000"])
I1 = icon(["00011000","00111000","00011000","00011000","00011000","00011000","01111110","00000000"])
IW = icon(["10000001","10000001","10010001","10010001","10101001","10101001","01010101","00000000"])
IL = icon(["10000000","10000000","10000000","10000000","10000000","10000000","11111100","00000000"])
ID = icon(["01111100","01000110","01000001","01000001","01000001","01000001","01000110","01111100"])
IC = [I3, I2, I1]


# --- Serial ---
def find_port():
    for p in serial.tools.list_ports.comports():
        if any(x in p.device.lower() for x in ("usbmodem", "usbserial", "ttyacm", "ttyusb")):
            return p.device
    return None


def send(ser, img, color):
    if not ser: return
    b = bytearray([SYNC_MARKER, CMD_FRAME])
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            b.extend([color[2], color[1], color[0]] if img[y, x] else [0, 0, 0])
    ser.write(b)


# --- Gesture ---
def gesture(landmarks):
    tips, pips = [8, 12, 16, 20], [6, 10, 14, 18]
    n = sum(1 for t, p in zip(tips, pips) if landmarks.landmark[t].y < landmarks.landmark[p].y)
    if n <= 1: return ROCK
    if n == 2: return SCISSORS
    if n >= 4: return PAPER
    return ROCK


def judge(p, a):
    if p == a: return "draw"
    return "win" if BEATS[p] == a else "lose"


# --- Main ---
def main():
    port = find_port()
    ser = serial.Serial(port, BAUDRATE, timeout=1) if port else None
    if ser:
        time.sleep(2)
        print(f"ESP32: {port}")
        time.sleep(3)
        print("Ready.")
    else:
        print("ESP32 not found — screen-only mode.")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera blocked by macOS. Fix: System Settings → Privacy → Camera → enable Terminal.")
        if ser: ser.close()
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.7,
                                      min_tracking_confidence=0.5, model_complexity=1)
    draw = mp.solutions.drawing_utils
    style = mp.solutions.drawing_styles

    ai_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_brain.pkl")
    ai = SmartAI.load(ai_path) or SmartAI()
    print(f"AI memory: {ai.total()} rounds")

    SC, SS, SR = 0, 1, 2
    state, t0 = SC, time.time()
    ai_choice = random.choice([ROCK, PAPER, SCISSORS])
    player, last, result, score = NONE, NONE, "draw", [0, 0, 0]
    fps_timer, fps_count = time.time(), 0

    print("\n  R O C K   P A P E R   S C I S S O R S  vs  A I")
    print("  Show your hand  |  [Q] quit\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok: break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            res = hands.process(rgb)
            rgb.flags.writeable = True

            if res.multi_hand_landmarks:
                for hl in res.multi_hand_landmarks:
                    draw.draw_landmarks(frame, hl, mp.solutions.hands.HAND_CONNECTIONS,
                                        style.get_default_hand_landmarks_style(),
                                        style.get_default_hand_connections_style())
                    player = gesture(hl)

            now = time.time()
            h, w, _ = frame.shape

            # --- Countdown ---
            if state == SC:
                i = min(int((now - t0) / COUNTDOWN_SEC), 3)
                if i >= 3:
                    state, t0 = SS, now
                    last = player
                    ai_choice = ai.counter()
                    result = judge(last, ai_choice)
                    if result == "win": score[0] += 1
                    elif result == "lose": score[1] += 1
                    else: score[2] += 1
                    if last != NONE: ai.record(last)
                    print(f"  You: {last.upper():8s}  AI: {ai_choice.upper():8s}  "
                          f"{'WIN' if result=='win' else 'LOSE' if result=='lose' else 'DRAW'}")
                    state, t0 = SR, now
                else:
                    send(ser, IC[min(i, 2)], (200, 200, 200))
                    cv2.putText(frame, str(i + 1), (w // 2 - 25, h // 2 + 35),
                                cv2.FONT_HERSHEY_DUPLEX, 3, (255, 255, 255), 4)

            # --- Result ---
            elif state == SR:
                if result == "win":
                    send(ser, IW, (0, 255, 0))
                    txt, clr = "YOU WIN!", (0, 255, 0)
                elif result == "lose":
                    send(ser, IL, (0, 0, 255))
                    txt, clr = "AI WINS!", (0, 0, 255)
                else:
                    send(ser, ID, (255, 255, 0))
                    txt, clr = "DRAW!", (255, 255, 0)

                cv2.putText(frame, txt, (w // 2 - 120, h // 2 + 30),
                            cv2.FONT_HERSHEY_DUPLEX, 2, clr, 3)
                cv2.putText(frame, f"You: {last.upper()}", (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, GESTURE_COLORS.get(last, (200, 200, 200)), 2)
                cv2.putText(frame, f"AI: {ai_choice.upper()}", (20, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, GESTURE_COLORS.get(ai_choice, (200, 200, 200)), 2)

                if now - t0 > 1.5:
                    state, t0 = SC, now

            sc = f"W:{score[0]}  L:{score[1]}  D:{score[2]}"
            cv2.putText(frame, sc, (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            fps_count += 1
            if fps_count % 30 == 0:
                f = int(fps_count / max(now - fps_timer, 0.001))
                fps_count, fps_timer = 0, now
                cv2.putText(frame, f"FPS:{f}", (w - 100, h - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

            cv2.imshow("RPS vs AI", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        ai.save(ai_path)
        cap.release(); cv2.destroyAllWindows()
        if ser: ser.close()
        hands.close()
        t = sum(score)
        if t:
            print(f"\n  Final: W:{score[0]}  L:{score[1]}  D:{score[2]}  ({score[0]/t*100:.0f}%)")
        print("Done.")


if __name__ == "__main__":
    main()
