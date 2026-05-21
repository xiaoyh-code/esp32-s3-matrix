import cv2
import numpy as np
import mediapipe as mp
import serial
import serial.tools.list_ports
import time
import sys
import os
import pickle
import random
import collections

MATRIX_W = 8
MATRIX_H = 8
BAUDRATE = 115200

SYNC_MARKER = 0xAA
CMD_FRAME = 0x01

ROCK = "rock"
PAPER = "paper"
SCISSORS = "scissors"
NONE = "none"

BEATS = {ROCK: SCISSORS, SCISSORS: PAPER, PAPER: ROCK}
BEATEN_BY = {v: k for k, v in BEATS.items()}

GESTURE_COLORS = {
    ROCK: (255, 60, 60),
    PAPER: (60, 255, 60),
    SCISSORS: (60, 160, 255),
}

def make_icon(pattern_lines, default_val=0):
    icon = np.full((MATRIX_H, MATRIX_W), default_val, dtype=np.uint8)
    for y, line in enumerate(pattern_lines):
        for x, ch in enumerate(line):
            if x < MATRIX_W and ch.isdigit() and int(ch) == 1:
                icon[y, x] = 1
    return icon

ICON_3 = make_icon([
    "01111100",
    "00000110",
    "00001100",
    "00000110",
    "00000110",
    "00001100",
    "00000110",
    "01111100",
])

ICON_2 = make_icon([
    "01111100",
    "00000110",
    "00000110",
    "01111100",
    "01100000",
    "01100000",
    "01111110",
    "00000000",
])

ICON_1 = make_icon([
    "00011000",
    "00111000",
    "00011000",
    "00011000",
    "00011000",
    "00011000",
    "01111110",
    "00000000",
])

ICON_W = make_icon([
    "10000001",
    "10000001",
    "10010001",
    "10010001",
    "10101001",
    "10101001",
    "01010101",
    "00000000",
])

ICON_L = make_icon([
    "10000000",
    "10000000",
    "10000000",
    "10000000",
    "10000000",
    "10000000",
    "11111100",
    "00000000",
])

ICON_ROCK = make_icon([
    "00000000",
    "00111100",
    "01111110",
    "01111110",
    "01111110",
    "01111110",
    "00111100",
    "00000000",
])

ICON_PAPER = make_icon([
    "11111111",
    "10000001",
    "10111101",
    "10111101",
    "10111101",
    "10111101",
    "10000001",
    "11111111",
])

ICON_SCISSORS = make_icon([
    "10000001",
    "11000011",
    "01100110",
    "00111100",
    "00011000",
    "00111100",
    "01100110",
    "11000011",
])

ICON_D = make_icon([
    "01111100",
    "01000110",
    "01000001",
    "01000001",
    "01000001",
    "01000001",
    "01000110",
    "01111100",
])

GESTURE_ICONS = {ROCK: ICON_ROCK, PAPER: ICON_PAPER, SCISSORS: ICON_SCISSORS}

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


def classify_gesture(hand_landmarks):
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    extended_count = 0
    fingers = []

    for tip_idx, pip_idx in zip(tips, pips):
        if hand_landmarks.landmark[tip_idx].y < hand_landmarks.landmark[pip_idx].y:
            extended_count += 1
            fingers.append(True)
        else:
            fingers.append(False)

    if extended_count <= 1:
        return ROCK
    elif extended_count == 2:
        return SCISSORS
    elif extended_count >= 4:
        return PAPER
    return ROCK


AI_MODEL_FILE = "ai_brain.pkl"
MAX_ORDER = 5


class SmartAI:
    def __init__(self, max_order=MAX_ORDER):
        self.max_order = max_order
        self.transitions = {n: {} for n in range(1, max_order + 1)}
        self.history = []
        self.global_counts = collections.Counter()

    def record(self, move):
        for order in range(1, self.max_order + 1):
            if len(self.history) >= order:
                seq = tuple(self.history[-order:])
                if seq not in self.transitions[order]:
                    self.transitions[order][seq] = collections.Counter()
                self.transitions[order][seq][move] += 1
        self.history.append(move)
        self.global_counts[move] += 1

    def predict(self):
        for order in range(self.max_order, 0, -1):
            if len(self.history) >= order:
                seq = tuple(self.history[-order:])
                counts = self.transitions[order].get(seq)
                if counts and len(counts) > 0:
                    return counts.most_common(1)[0][0]
        if self.global_counts:
            return self.global_counts.most_common(1)[0][0]
        return random.choice([ROCK, PAPER, SCISSORS])

    def counter_move(self):
        return BEATEN_BY[self.predict()]

    def stats(self):
        total = sum(self.global_counts.values()) if self.global_counts else 0
        return total


def save_ai(ai):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, AI_MODEL_FILE)
    data = (ai.transitions, ai.history, ai.global_counts, ai.max_order)
    with open(path, "wb") as f:
        pickle.dump(data, f)


def load_ai():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, AI_MODEL_FILE)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        transitions, history, global_counts, max_order = pickle.load(f)
    ai = SmartAI(max_order)
    ai.transitions = transitions
    ai.history = history
    ai.global_counts = global_counts
    return ai
    if player == ai:
        return "draw"
    if BEATS[player] == ai:
        return "win"
    return "lose"


def judge(player, ai):
    if player == ai:
        return "draw"
    if BEATS[player] == ai:
        return "win"
    return "lose"


def build_payload(icon, color):
    payload = bytearray()
    for y in range(MATRIX_H):
        for x in range(MATRIX_W):
            if icon[y, x]:
                payload.extend([color[0], color[1], color[2]])
            else:
                payload.extend([0, 0, 0])
    return payload


def send_frame(ser, icon, color):
    packet = bytearray([SYNC_MARKER, CMD_FRAME]) + build_payload(icon, color)
    ser.write(packet)


def find_serial_port():
    ports = serial.tools.list_ports.comports()
    if not ports:
        return None
    for p in ports:
        if "usbmodem" in p.device.lower():
            return p.device
    for p in ports:
        if "usbserial" in p.device.lower():
            return p.device
    for p in ports:
        if "ttyACM" in p.device.lower() or "ttyUSB" in p.device.lower():
            return p.device
    return ports[0].device if ports else None


def find_camera():
    for idx in range(5):
        cap = cv2.VideoCapture(idx)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"Camera found at index {idx}")
                return cap
        cap.release()
    return None


def main():
    port = find_serial_port()
    if port is None:
        print("No serial port found.")
        sys.exit(1)

    ser = serial.Serial(port, BAUDRATE, timeout=1)
    time.sleep(2)
    print(f"Connected: {port}")
    print("Waiting for ESP32...")
    time.sleep(4)

    cap = find_camera()
    if cap is None:
        print("Cannot open any webcam.")
        print("On macOS: grant camera permission to Terminal in")
        print("  System Preferences > Privacy & Security > Camera")
        ser.close()
        sys.exit(1)

    import os
    os.environ["MEDIAPIPE_DISABLE_GPU"] = "0"

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
        model_complexity=1,
    )

    print("MediaPipe running on Apple Silicon (Metal GPU)")

    ai = load_ai()
    if ai is not None:
        print(f"AI loaded: {ai.stats()} matches remembered")
    else:
        ai = SmartAI()
        print("Fresh AI — learning from scratch")
    print("")

    STATE_COUNTDOWN = "countdown"
    STATE_SHOOT = "shoot"
    STATE_RESULT = "result"

    state = STATE_COUNTDOWN
    state_start = time.time()
    countdown_phase = 0
    countdown_steps = [3, 2, 1]
    countdown_icons = [ICON_3, ICON_2, ICON_1]
    countdown_interval = 0.8

    ai_prediction = ""
    ai_choice = random.choice([ROCK, PAPER, SCISSORS])
    result = "draw"
    score = [0, 0, 0]

    player_current = NONE
    player_final = NONE
    gesture_show_start = 0

    print("\nRock Paper Scissors vs AI! [q] to quit\n")

    frame_count = 0
    t0 = time.time()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            if results.multi_hand_landmarks:
                for hl in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(
                        frame, hl, mp_hands.HAND_CONNECTIONS,
                        mp_drawing_styles.get_default_hand_landmarks_style(),
                        mp_drawing_styles.get_default_hand_connections_style(),
                    )
                    player_current = classify_gesture(hl)

            now = time.time()

            if state == STATE_COUNTDOWN:
                elapsed = now - state_start
                step_idx = int(elapsed / countdown_interval)
                if step_idx >= len(countdown_steps):
                    state = STATE_SHOOT
                    state_start = now
                    ai_prediction = ai.predict()
                    ai_choice = ai.counter_move()
                    player_final = player_current
                    print(f"  You: {player_final.upper():8s}  AI: {ai_choice.upper():8s}  (predicted: {ai_prediction.upper()})")
                else:
                    idx = min(step_idx, len(countdown_icons) - 1)
                    num_str = str(countdown_steps[idx])
                    send_frame(ser, countdown_icons[idx], (200, 200, 200))

            elif state == STATE_SHOOT:
                player_final = player_current
                result = judge(player_final, ai_choice)

                if result == "win":
                    score[0] += 1
                    send_frame(ser, ICON_W, (0, 255, 0))
                elif result == "lose":
                    score[1] += 1
                    send_frame(ser, ICON_L, (255, 0, 0))
                else:
                    score[2] += 1
                    send_frame(ser, ICON_D, (255, 255, 0))

                if player_final != NONE:
                    ai.record(player_final)

                state = STATE_RESULT
                state_start = now

            elif state == STATE_RESULT:
                if now - state_start > 1.5:
                    state = STATE_COUNTDOWN
                    state_start = now

            h, w, _ = frame.shape

            if state == STATE_COUNTDOWN:
                elapsed = now - state_start
                step_idx = int(elapsed / countdown_interval)
                if step_idx < len(countdown_steps):
                    t_left = countdown_interval - (elapsed - step_idx * countdown_interval)
                    num = countdown_steps[step_idx]
                    cv2.putText(frame, str(num), (w // 2 - 40, h // 2 + 40),
                                cv2.FONT_HERSHEY_DUPLEX, 4, (255, 255, 255), 5)
                else:
                    cv2.putText(frame, "SHOOT!", (w // 2 - 140, h // 2 + 40),
                                cv2.FONT_HERSHEY_DUPLEX, 3, (0, 255, 255), 4)
            elif state == STATE_RESULT:
                if result == "win":
                    txt, clr = "YOU WIN!", (0, 255, 0)
                elif result == "lose":
                    txt, clr = "AI WINS!", (0, 0, 255)
                else:
                    txt, clr = "DRAW!", (255, 255, 0)
                cv2.putText(frame, txt, (w // 2 - 160, h // 2 + 40),
                            cv2.FONT_HERSHEY_DUPLEX, 3, clr, 4)

                pcol = GESTURE_COLORS.get(player_final, (200, 200, 200))
                acol = GESTURE_COLORS.get(ai_choice, (200, 200, 200))
                cv2.putText(frame, f"You: {player_final.upper()}", (30, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, pcol, 2)
                cv2.putText(frame, f"AI: {ai_choice.upper()}", (30, 100),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, acol, 2)
                cv2.putText(frame, f"predicted: {ai_prediction.upper()}", (30, 140),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

            score_text = f"W:{score[0]}  L:{score[1]}  D:{score[2]}"
            cv2.putText(frame, score_text, (20, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            fps = frame_count / max(now - t0, 0.01) if frame_count > 0 else 0
            cv2.putText(frame, f"FPS:{int(fps)}  [q]uit", (w - 180, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

            cv2.imshow("Rock Paper Scissors vs AI", frame)

            if player_current != NONE:
                prev = np.zeros((160, 160, 3), dtype=np.uint8)
                c = GESTURE_COLORS.get(player_current, (255, 255, 255))
                icon = GESTURE_ICONS.get(player_current)
                if icon is not None:
                    for y in range(8):
                        for x in range(8):
                            if icon[y, x]:
                                cv2.rectangle(prev, (x * 20, y * 20),
                                              (x * 20 + 19, y * 20 + 19), c, -1)
                cv2.imshow("Your Gesture", prev)

            frame_count += 1
            if frame_count % 30 == 0:
                frame_count = 0
                t0 = now

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    except serial.SerialException as e:
        print(f"Serial error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        save_ai(ai)
        cap.release()
        cv2.destroyAllWindows()
        ser.close()
        hands.close()
        total = sum(score)
        if total > 0:
            print(f"\nFinal: W:{score[0]} L:{score[1]} D:{score[2]} ({score[0]/total*100:.0f}% win)")
        print("Done.")


if __name__ == "__main__":
    main()
