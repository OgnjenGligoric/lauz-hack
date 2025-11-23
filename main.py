import tkinter as tk
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
    def __init__(self, server_url=SERVER_URL, show_debug=True, offline_mode=False):
        self.server_url = server_url
        self.show_debug = show_debug
        self.offline_mode = offline_mode
        self.running = False
        
        self.event_queue = Queue()
        
        self.cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise ValueError("Camera not found!")

        print("Initializing Eye Tracker...")
        self.gaze_tracker = GazeEstimator()
        
        print("Starting calibration... Follow the points.")
        run_9_point_calibration(self.gaze_tracker)
        print("Calibration complete!")

        print("Initializing Hand Tracker...")
        self.hand_tracker = HandTracker()

        self.root = tk.Tk()
        self.root.title("Eye & Hand Controller")
        
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.7)
        
        self.canvas = tk.Canvas(
            self.root, 
            width=self.screen_w, 
            height=self.screen_h, 
            bg='white', 
            highlightthickness=0
        )
        self.canvas.pack()
        
        try:
            self.root.wm_attributes("-transparentcolor", "white")
        except:
            pass

        self.pointer_size = 20
        self.pointer = self.canvas.create_oval(
            0, 0, 
            self.pointer_size, 
            self.pointer_size, 
            fill='red', 
            outline='red'
        )

        self.root.bind("<Escape>", lambda e: self.stop())
        
        self.current_gaze = {"x": 0, "y": 0}
        
        self.debug_w = 320
        self.debug_h = 240
        self.debug_name = "Mini Camera Debug"

    def send_event(self, event_data):
        if self.offline_mode:
            return
            
        try:
            response = requests.post(
                self.server_url,
                json=event_data,
                headers={"Content-Type": "application/json"},
                timeout=1
            )
            if response.status_code == 200:
                print(f"✓ Sent: {event_data['action']}")
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

    def parse_action(self, event):
        if "SWIPE_UP" in event: return "swipe_up"
        elif "SWIPE_DOWN" in event: return "swipe_down"
        elif "SWIPE_LEFT" in event: return "swipe_left"
        elif "SWIPE_RIGHT" in event: return "swipe_right"
        elif "SPECIAL_POSE" in event: return "special_pose"
        else: return "unknown"

    def update_loop(self):
        ret, frame = self.cap.read()
        if not ret:
            self.root.after(10, self.update_loop)
            return

        features, blink = self.gaze_tracker.extract_features(frame)
        
        gaze_detected = False
        if features is not None and not blink:
            coordinates = self.gaze_tracker.predict([features])[0]
            gx, gy = int(coordinates[0]), int(coordinates[1])
            
            gx = max(0, min(gx, self.screen_w))
            gy = max(0, min(gy, self.screen_h))
            
            self.current_gaze = {"x": gx, "y": gy}
            gaze_detected = True

            if self.show_debug:
                self.canvas.coords(
                    self.pointer, 
                    gx - self.pointer_size/2, 
                    gy - self.pointer_size/2, 
                    gx + self.pointer_size/2, 
                    gy + self.pointer_size/2
                )
                self.canvas.itemconfigure(self.pointer, state='normal')
            else:
                self.canvas.itemconfigure(self.pointer, state='hidden')
        else:
             self.canvas.itemconfigure(self.pointer, state='hidden')

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
                if event != "unknown":
                    self.event_queue.put(gesture_event)
                print(f"[{time.strftime('%H:%M:%S')}] DETECTED: {event}")

        if self.show_debug:
            small_frame = cv2.resize(annotated_frame, (self.debug_w, self.debug_h))
            
            cv2.imshow(self.debug_name, small_frame)
            
            cv2.moveWindow(self.debug_name, 0, 0)
            
            cv2.waitKey(1)

        self.root.after(10, self.update_loop)

    def run(self):
        self.running = True
        
        self.http_thread = threading.Thread(target=self.http_worker, daemon=True)
        self.http_thread.start()
        
        print("\n=== SERVICE STARTED ===")
        print(f"Server: {self.server_url}")
        print("- Red dot overlay ACTIVE")
        print("- Mini Camera Debug ACTIVE")
        print("Press ESC to exit\n")
        
        self.update_loop()
        self.root.mainloop()

    def stop(self):
        print("\n=== SHUTTING DOWN ===")
        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()
        self.root.destroy()
        print("Service stopped.")


if __name__ == "__main__":
    service = BackgroundTrackerService(
        server_url="http://localhost:5005/",
        show_debug=True, 
        offline_mode=False
    )
    
    try:
        service.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()