# JetBrains Hands-Free Navigation Plugin

A JetBrains IDE plugin that enables **hands-free navigation**, **eye-tracking–based code interaction**, and **AI-assisted code explanation**, designed and built during the **Lauz-Hack Hackathon 2025**.

The system integrates **hand-gesture recognition**, **gaze tracking**, and **JetBrains AI Assistant** into a unified workflow that allows developers to navigate, read, and query code without using a keyboard or mouse.

---

## 🎥 Demo
Check out the demo video to see the plugin in action:  

[![JetBrains Hands-Free Plugin](https://img.youtube.com/vi/LSz7CppmXdQ/0.jpg)](https://www.youtube.com/watch?v=LSz7CppmXdQ)

---

## 🎯 Features

### 👁️ Eye-Tracking Integration
- Tracks where the user is looking inside the IDE.
- Determines the active code element or block based on gaze coordinates.
- Enables a “look-and-ask” workflow using JetBrains AI.

### ✋ Hand-Gesture Navigation

Navigate the IDE using natural hand movements detected through the webcam:

| Gesture | Action |
|--------|--------|
| **Swipe Up** | Scroll editor *up* |
| **Swipe Down** | Scroll editor *down* |
| **Swipe Left** | Switch to *previous* tab |
| **Swipe Right** | Switch to *next* tab |

### AI-Powered Code Explanation
A special hand gesture triggers JetBrains AI to:
- Explain the code block the user is currently looking at
- Summarize or clarify complex logic
- Provide refactoring suggestions
- Respond contextually using gaze-based code selection + IDE caret position

### JetBrains Plugin Integration
The plugin communicates with gesture and gaze engines through a local HTTP bridge:
- Receives real-time gesture events
- Receives gaze coordinates
- Translates them into IDE actions or AI calls

---

## System Architecture

    Webcam → Hand Engine (MediaPipe) ┐
                                     ├→ Local API → JetBrains Plugin → IDE Actions + AI Assistant
    Webcam → Gaze Engine (EyeTrax)   ┘

The Python services run independently and stream real-time events to the JetBrains plugin.

---

## 🚀 Installation & Setup

### 1. Clone the Repository

    git clone https://github.com/OgnjenGligoric/lauz-hack.git
    cd lauz-hack

### 2. Prepare the Python Environment

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

### 3. Run the Tracking Engines

Start the gesture and gaze tracking modules:

    python main.py
---

## 🧩 Plugin Usage

1. Build and install the JetBrains plugin from the `CodeHeplerPlugin/` directory (use JetBrains Plugin SDK).  
2. Open any JetBrains IDE (IntelliJ, PyCharm, WebStorm…).  
3. Start both tracking engines (`hand_engine.py` and `eyetrax.py`).  
4. Configure plugin settings to point to the host/port of the Python bridge.  
5. Navigate hands-free using gestures and trigger AI explanations with the Explain gesture.

---

## ✨ Gesture Controls (Full Overview)

### Navigation Gestures

| Gesture | IDE Action |
|--------|------------|
| **Swipe Up** | Scroll up |
| **Swipe Down** | Scroll down |
| **Swipe Left** | Previous editor tab |
| **Swipe Right** | Next editor tab |

### AI Interaction

| Gesture | AI Action |
|--------|-----------|
| **Explain Gesture** | Explains the code the user is looking at (gaze-based selection) |

Flow: **Look → Gesture → AI assistance.**

---

## 🧠 Technologies Used

- **Python**
  - MediaPipe (hand gesture detection)
  - EyeTrax (custom eye-tracking)
  - OpenCV
  - Async event streaming server
- **JetBrains Platform**
  - Java plugin
  - JetBrains AI Assistant API (or configured LLM)

---

## 👥 Team

Developed during **Lauz-Hack 2025** by:

- **Ognjen Gligorić**
- **Nemanja Stjepanović**
- **Stefan Đurica**
- **Nenad Berić**

---

## 🏁 Future Improvements

- Gesture smoothing (Kalman/Bilateral)
- Multi-monitor calibrations
- More IDE actions (debug control, refactorings)
- Voice + gesture hybrid interaction
- Privacy & data-handling guidelines for gaze/camera data

---
