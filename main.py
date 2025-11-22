import tkinter as tk
import cv2
import time
from eyetrax import GazeEstimator, run_9_point_calibration
from hand_engine import HandTracker

class CombinedEyeHandApp:
    def __init__(self):
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

        self.root.bind("<Escape>", lambda e: self.close_app())

        print("\n=== SYSTEM STARTED ===")
        print("- Red dot follows eye")
        print("- Hand gestures shown in CV2 window")
        print("- ESC to exit\n")
        
        self.update_loop()
        self.root.mainloop()

    def update_loop(self):
        ret, frame = self.cap.read()
        if not ret:
            print("Camera read error!")
            self.root.after(10, self.update_loop)
            return

        features, blink = self.gaze_tracker.extract_features(frame)
        
        if features is not None and not blink:
            coordinates = self.gaze_tracker.predict([features])[0]
            gx, gy = int(coordinates[0]), int(coordinates[1])
            
            gx = max(0, min(gx, self.screen_w))
            gy = max(0, min(gy, self.screen_h))

            self.canvas.coords(
                self.pointer, 
                gx - self.pointer_size/2, 
                gy - self.pointer_size/2, 
                gx + self.pointer_size/2, 
                gy + self.pointer_size/2
            )

        annotated_frame, events = self.hand_tracker.process(frame)
        
        if events:
            timestamp = time.strftime('%H:%M:%S')
            for event in events:
                print(f"[{timestamp}] {event}")

        cv2.imshow("Hand Gestures Debug", annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == 27:
            self.close_app()
            return

        self.root.after(10, self.update_loop)

    def close_app(self):
        print("\n=== SHUTTING DOWN ===")
        self.cap.release()
        cv2.destroyAllWindows()
        self.root.destroy()
        print("Application closed.")


if __name__ == "__main__":
    try:
        app = CombinedEyeHandApp()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()