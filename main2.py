import cv2
import time
import json
import requests
import threading
from queue import Queue
from eyetrax import GazeEstimator, run_9_point_calibration
from hand_engine import HandTracker


SERVER_URL = "http://localhost:5005/"


class BackgroundTrackerService:
    def __init__(self, server_url=SERVER_URL, show_debug=False, offline_mode=False):
        self.server_url = server_url
        self.show_debug = show_debug
        self.offline_mode = offline_mode
        self.running = False
        
        self.event_queue = Queue()
        
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise ValueError("Camera not found!")

        print("Initializing Eye Tracker...")
        self.gaze_tracker = GazeEstimator()
        
        print("Starting calibration... Follow the points.")
        run_9_point_calibration(self.gaze_tracker)
        print("Calibration complete!")

        print("Initializing Hand Tracker...")
        self.hand_tracker = HandTracker()
        
        try:
            import tkinter as tk
            root = tk.Tk()
            self.screen_w = root.winfo_screenwidth()
            self.screen_h = root.winfo_screenheight()
            root.destroy()
        except:
            self.screen_w = 1920
            self.screen_h = 1080
            print(f"Warning: Could not detect screen size, using default {self.screen_w}x{self.screen_h}")
        
        print(f"Screen resolution: {self.screen_w}x{self.screen_h}")
        
        self.current_gaze = {"x": 0, "y": 0}

    def send_event(self, event_data):
        if self.offline_mode:
            print(f"📤 [OFFLINE] Would send: {json.dumps(event_data)}")
            return
            
        try:
            print(f"📤 Sending: {json.dumps(event_data, indent=2)}")
            
            response = requests.post(
                self.server_url,
                json=event_data,
                headers={"Content-Type": "application/json"},
                timeout=1
            )
            if response.status_code == 200:
                print(f"✓ Sent: {response.json()}")
            else:
                print(f"✗ Server error: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"✗ Connection error: {e}")

    def http_worker(self):
        while self.running:
            try:
                event_data = self.event_queue.get(timeout=0.1)
                self.send_event(event_data)
            except:
                continue

    def process_loop(self):
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            features, blink = self.gaze_tracker.extract_features(frame)
            
            if features is not None and not blink:
                coordinates = self.gaze_tracker.predict([features])[0]
                gx, gy = int(coordinates[0]), int(coordinates[1])
                
                gx = max(0, min(gx, self.screen_w))
                gy = max(0, min(gy, self.screen_h))
                
                self.current_gaze = {"x": gx, "y": gy}

            annotated_frame, events = self.hand_tracker.process(frame)
            
            if events:
                timestamp = time.time()
                for event in events:
                    action_type = self.parse_action(event)
                    
                    gesture_event = {
                        "timestamp": int(timestamp * 1000),
                        "type": "gesture",
                        "action": action_type,
                        "coordinates": self.current_gaze,
                        "raw_event": event
                    }
                    
                    self.event_queue.put(gesture_event)
                    print(f"[{time.strftime('%H:%M:%S')}] {event}")

            if self.show_debug:
                cv2.imshow("Debug View", annotated_frame)
                if cv2.waitKey(1) & 0xFF == 27:
                    self.stop()
                    break
            else:
                cv2.waitKey(1)

    def parse_action(self, event):
        if "SWIPE_UP" in event:
            return "swipe_up"
        elif "SWIPE_DOWN" in event:
            return "swipe_down"
        elif "SWIPE_LEFT" in event:
            return "swipe_left"
        elif "SWIPE_RIGHT" in event:
            return "swipe_right"
        elif "SPECIAL_POSE" in event:
            return "special_pose"
        elif "OPEN_PALM" in event:
            return "open_palm"
        elif "CLOSED_HAND" in event:
            return "closed_hand"
        elif "THUMBS_UP" in event:
            return "thumbs_up"
        else:
            return "unknown"

    def start(self):
        self.running = True
        
        self.http_thread = threading.Thread(target=self.http_worker, daemon=True)
        self.http_thread.start()
        
        self.process_thread = threading.Thread(target=self.process_loop, daemon=True)
        self.process_thread.start()
        
        print("\n=== SERVICE STARTED ===")
        print(f"Server: {self.server_url}")
        print(f"Debug window: {'ON' if self.show_debug else 'OFF'}")
        print("Press Ctrl+C to stop\n")

    def stop(self):
        print("\n=== SHUTTING DOWN ===")
        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()
        print("Service stopped.")

    def run(self):
        self.start()
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()


if __name__ == "__main__":
    service = BackgroundTrackerService(
        server_url="http://localhost:5005/",
        show_debug=False,
        offline_mode=False
    )
    
    try:
        service.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()