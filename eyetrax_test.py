import tkinter as tk
import cv2
from eyetrax import GazeEstimator, run_9_point_calibration

class GazeTrackerApp:
    def __init__(self):
        # 1. Inicijalizacija EyeTrax-a
        self.tracker = GazeEstimator()
        self.cap = cv2.VideoCapture(0)
        
        if not self.cap.isOpened():
            raise ValueError("Kamera nije pronađena!")

        # 2. Pokretanje kalibracije (ovo je obavezno za preciznost)
        print("Pokrećem kalibraciju... Prati tačke.")
        run_9_point_calibration(self.tracker)
        print("Kalibracija završena. Pokrećem vizuelizaciju.")

        # 3. Podešavanje Tkinter prozora (Overlay)
        self.root = tk.Tk()
        self.root.title("EyeTrax Visualizer")
        
        # Uzimamo dimenzije ekrana
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        
        # Postavljamo prozor preko celog ekrana bez ivica
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        self.root.overrideredirect(True) # Uklanja naslovnu liniju i dugmad
        self.root.attributes("-topmost", True) # Uvek na vrhu
        self.root.attributes("-alpha", 0.7) # Blaga providnost pozadine (0.0 je skroz providno)
        
        # Postavljamo sivu pozadinu da bi video tačku, ali da vidiš i aplikacije ispod
        # Ako želiš skroz providno, koristi: self.root.wm_attributes("-transparentcolor", "white") na Windows-u
        self.canvas = tk.Canvas(self.root, width=self.screen_w, height=self.screen_h, bg='white', highlightthickness=0)
        self.canvas.pack()
        
        # Windows trik za potpunu providnost (bela boja postaje providna)
        try:
            self.root.wm_attributes("-transparentcolor", "white")
        except:
            pass # Ako si na Linuxu/Macu ovo možda radi drugačije

        # Kreiranje "oka" (crvene tačke)
        self.pointer_size = 20
        self.pointer = self.canvas.create_oval(0, 0, self.pointer_size, self.pointer_size, fill='red', outline='red')

        # Dugme za izlaz (Escape)
        self.root.bind("<Escape>", lambda e: self.close_app())

        # Pokretanje petlje za ažuriranje
        self.update_gaze()
        self.root.mainloop()

    def update_gaze(self):
        ret, frame = self.cap.read()
        if ret:
            # Izdvajanje karakteristika i predviđanje
            features, blink = self.tracker.extract_features(frame)
            
            if features is not None and not blink:
                # Dobijanje koordinata
                coordinates = self.tracker.predict([features])[0]
                x, y = int(coordinates[0]), int(coordinates[1])
                
                # Ograničavanje da tačka ne pobegne van ekrana
                x = max(0, min(x, self.screen_w))
                y = max(0, min(y, self.screen_h))

                # Pomeranje crvene tačke
                self.canvas.coords(self.pointer, 
                                   x - self.pointer_size/2, y - self.pointer_size/2, 
                                   x + self.pointer_size/2, y + self.pointer_size/2)
        
        # Pozovi ponovo ovu funkciju za 10 milisekundi
        self.root.after(10, self.update_gaze)

    def close_app(self):
        self.cap.release()
        self.root.destroy()
        print("Aplikacija ugašena.")

if __name__ == "__main__":
    app = GazeTrackerApp()