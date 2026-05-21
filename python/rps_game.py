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
    ROCK: (30, 30, 255),
    PAPER: (30, 255, 30),
    SCISSORS: (255, 160, 30),
}

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
        return sum(self.global_counts.values()) if self.global_counts else 0


def save_ai(ai):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AI_MODEL_FILE)
    data = (ai.transitions, ai.history, ai.global_counts, ai.max_order)
    with open(path, "wb") as f:
        import pickle
        pickle.dump(data, f)


def load_ai():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), AI_MODEL_FILE)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        import pickle
        transitions, history, global_counts, max_order = pickle.load(f)
    ai = SmartAI(max_order)
    ai.transitions = transitions
    ai.history = history
    ai.global_counts = global_counts
    return ai


def classify_gesture(hand_landmarks):
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    extended = 0
    for tip_idx, pip_idx in zip(tips, pips):
        if hand_landmarks.landmark[tip_idx].y < hand_landmarks.landmark[pip_idx].y:
            extended += 1
    if extended <= 1:
        return ROCK
    elif extended == 2:
        return SCISSORS
    elif extended >= 4:
        return PAPER
    return ROCK


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
                payload.extend([color[2], color[1], color[0]])
            else:
                payload.extend([0, 0, 0])
    return payload


def send_frame(ser, icon, color):
    packet = bytearray([SYNC_MARKER, CMD_FRAME]) + build_payload(icon, color)
    ser.write(packet)


def make_icon(lines):
    icon = np.zeros((MATRIX_H, MATRIX_W), dtype=np.uint8)
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if x < MATRIX_W and ch == "1":
                icon[y, x] = 1
    return icon


ICON_3 = make_icon(["01111100","00000110","00001100","00000110","00000110","00001100","00000110","01111100"])
ICON_2 = make_icon(["01111100","00000110","00000110","01111100","01100000","01100000","01111110","00000000"])
ICON_1 = make_icon(["00011000","00111000","00011000","00011000","00011000","00011000","01111110","00000000"])
ICON_W = make_icon(["10000001","10000001","10010001","10010001","10101001","10101001","01010101","00000000"])
ICON_L = make_icon(["10000000","10000000","10000000","10000000","10000000","10000000","11111100","00000000"])
ICON_D = make_icon(["01111100","01000110","01000001","01000001","01000001","01000001","01000110","01111100"])


def find_serial_port():
    ports = serial.tools.list_ports.comports()
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


def main():
    # --- Serial ---
    port = find_serial_port()
    ser = None
    if port:
        ser = serial.Serial(port, BAUDRATE, timeout=1)
        time.sleep(2)
        print(f"Connected: {port}")
        print("Waiting for ESP32...")
        time.sleep(3)
    else:
        print("No ESP32 found. Running local-only mode.")

    # --- Camera ---
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open camera.")
        print("On macOS: double-click CameraFix.app first, then click Allow.")
        if ser:
            ser.close()
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    print("Camera OK")

    # --- MediaPipe ---
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.5,
        model_complexity=1,
    )

    # --- AI ---
    ai = load_ai()
    if ai is None:
        ai = SmartAI()
        print("Fresh AI")
    else:
        print(f"AI loaded: {ai.stats()} matches")

    # --- Game state ---
    STATE_COUNTDOWN = 0
    STATE_SHOOT = 1
    STATE_RESULT = 2
    state = STATE_COUNTDOWN
    state_start = time.time()
    countdown_interval = 0.8

    ai_choice = random.choice([ROCK, PAPER, SCISSORS])
    ai_prediction = ""
    result = "draw"
    score = [0, 0, 0]
    player_current = NONE
    player_final = NONE

    print("\nRock Paper Scissors vs AI! [q] quit\n")
    print("Show your hand to the camera.")

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
            h, w, _ = frame.shape

            if state == STATE_COUNTDOWN:
                elapsed = now - state_start
                step_idx = int(elapsed / countdown_interval)
                if step_idx >= 3:
                    state = STATE_SHOOT
                    state_start = now
                    ai_prediction = ai.predict()
                    ai_choice = ai.counter_move()
                    player_final = player_current
                    result = judge(player_final, ai_choice)
                    print(f"  You: {player_final.upper():8s}  AI: {ai_choice.upper():8s}  (pred: {ai_prediction.upper()})")

                    if result == "win":
                        score[0] += 1
                    elif result == "lose":
                        score[1] += 1
                    else:
                        score[2] += 1

                    if player_final != NONE:
                        ai.record(player_final)

                    state = STATE_RESULT
                    state_start = now
                else:
                    num = step_idx + 1
                    icons = [ICON_3, ICON_2, ICON_1]
                    if ser:
                        send_frame(ser, icons[step_idx], (200, 200, 200))
                    cv2.putText(frame, str(num), (w // 2 - 30, h // 2 + 30),
                                cv2.FONT_HERSHEY_DUPLEX, 3, (255, 255, 255), 4)

            elif state == STATE_RESULT:
                if ser:
                    if result == "win":
                        send_frame(ser, ICON_W, (0, 255, 0))
                    elif result == "lose":
                        send_frame(ser, ICON_L, (0, 0, 255))
                    else:
                        send_frame(ser, ICON_D, (255, 255, 0))

                if result == "win":
                    txt, clr = "YOU WIN!", (0, 255, 0)
                elif result == "lose":
                    txt, clr = "AI WINS!", (0, 0, 255)
                else:
                    txt, clr = "DRAW!", (255, 255, 0)
                cv2.putText(frame, txt, (w // 2 - 130, h // 2 + 30),
                            cv2.FONT_HERSHEY_DUPLEX, 2, clr, 3)
                cv2.putText(frame, f"You: {player_final.upper()}", (20, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, GESTURE_COLORS.get(player_final, (200, 200, 200)), 2)
                cv2.putText(frame, f"AI: {ai_choice.upper()}", (20, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, GESTURE_COLORS.get(ai_choice, (200, 200, 200)), 2)
                cv2.putText(frame, f"pred: {ai_prediction.upper()}", (20, 115),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

                if now - state_start > 1.5:
                    state = STATE_COUNTDOWN
                    state_start = now

            score_text = f"W:{score[0]}  L:{score[1]}  D:{score[2]}"
            cv2.putText(frame, score_text, (20, h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            fps = frame_count / max(now - t0, 0.01) if frame_count > 0 else 0
            cv2.putText(frame, f"FPS:{int(fps)}", (w - 100, h - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

            cv2.imshow("Rock Paper Scissors vs AI", frame)

            frame_count += 1
            if frame_count % 30 == 0:
                frame_count = 0
                t0 = now

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        save_ai(ai)
        cap.release()
        cv2.destroyAllWindows()
        if ser:
            ser.close()
        hands.close()
        total = sum(score)
        if total > 0:
            print(f"\nFinal: W:{score[0]} L:{score[1]} D:{score[2]} ({score[0]/total*100:.0f}% win)")
        print("Done.")


if __name__ == "__main__":
    main()
