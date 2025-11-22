import tkinter as tk
import cv2
from eyetrax import GazeEstimator, run_9_point_calibration

class GazeTrackerApp:
    def __init__(self):
        self.tracker = GazeEstimator(filter='kalman')
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            raise ValueError("Kamera nije pronađena!")

        print("Pokrećem kalibraciju... Prati tačke.")
        run_9_point_calibration(self.tracker)
        print("Kalibracija završena. Pokrećem vizuelizaciju.")

        self.root = tk.Tk()
        self.root.title("EyeTrax Visualizer")
        
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.7)
        
        self.canvas = tk.Canvas(self.root, width=self.screen_w, height=self.screen_h, bg='white', highlightthickness=0)
        self.canvas.pack()
        
        try:
            self.root.wm_attributes("-transparentcolor", "white")
        except:
            pass

        self.pointer_size = 20
        self.pointer = self.canvas.create_oval(0, 0, self.pointer_size, self.pointer_size, fill='red', outline='red')

        self.root.bind("<Escape>", lambda e: self.close_app())

        self.update_gaze()
        self.root.mainloop()

    def update_gaze(self):
        ret, frame = self.cap.read()
        if ret:
            features, blink = self.tracker.extract_features(frame)
            
            if features is not None and not blink:
                coordinates = self.tracker.predict([features])[0]
                x, y = int(coordinates[0]), int(coordinates[1])
                
                x = max(0, min(x, self.screen_w))
                y = max(0, min(y, self.screen_h))

                self.canvas.coords(self.pointer, 
                                   x - self.pointer_size/2, y - self.pointer_size/2, 
                                   x + self.pointer_size/2, y + self.pointer_size/2)
        
        self.root.after(10, self.update_gaze)

    def close_app(self):
        self.cap.release()
        self.root.destroy()
        print("Aplikacija ugašena.")

if __name__ == "__main__":
    app = GazeTrackerApp()