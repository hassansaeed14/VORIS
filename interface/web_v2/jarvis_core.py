import os
import subprocess
import shutil
import time
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import speech_recognition as sr

class JarvisSystemManager:
    def __init__(self):
        self.pending_action = None
        self.pending_target = None
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        
        # CALIBRATE ONCE AT STARTUP: Fixes the looping lag trap
        print("[VORIS] Booting System... Calibrating microphone for room noise.")
        try:
            calibration = sd.rec(int(1.0 * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype='int16')
            sd.wait()
            ambient_energy = np.sqrt(np.mean(calibration.astype(np.float64)**2))
            self.threshold = max(ambient_energy * 1.5, 200) # Highly sensitive threshold
            print(f"[VORIS] Calibration successful. Core engine standing by.\n")
        except Exception as e:
            print(f"[VORIS] Calibration failed using sounddevice: {str(e)}. Setting default threshold.")
            self.threshold = 300

    def listen_and_transcribe(self) -> str:
        """Streams microphone data instantly without re-calibrating."""
        with sr.Microphone(sample_rate=self.sample_rate) as source:
            self.recognizer.energy_threshold = self.threshold
            try:
                print("[VORIS] Listening...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                print("[VORIS] Processing speech...")
                text = self.recognizer.recognize_google(audio)
                return text
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                return ""
            except Exception as e:
                return f"Voice Error: {str(e)}"

if __name__ == "__main__":
    manager = JarvisSystemManager()