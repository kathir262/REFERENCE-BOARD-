"""
Audio cue generator for pose transitions (subtle, non-jarring chime).
"""
import math
import struct
import io
import wave
import threading
from PySide6.QtCore import QObject

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

class SoundCue(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cached_wav_bytes = self._generate_chime_wav()

    def _generate_chime_wav(self) -> bytes:
        """Synthesize a dual-harmonic gentle warm chime in memory."""
        sample_rate = 44100
        duration = 0.6  # seconds
        num_samples = int(sample_rate * duration)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            samples = []
            f1 = 880.0   # A5
            f2 = 1320.0  # E6 harmonic
            for i in range(num_samples):
                t = i / sample_rate
                # Exponential decay envelope
                envelope = math.exp(-6.0 * t)
                # Dual tone
                val = 0.6 * math.sin(2.0 * math.pi * f1 * t) + 0.4 * math.sin(2.0 * math.pi * f2 * t)
                sample = int(val * envelope * 24000)
                sample = max(-32767, min(32767, sample))
                samples.append(struct.pack('<h', sample))
            wav.writeframes(b''.join(samples))
        return buf.getvalue()

    def play_chime(self):
        """Play chime asynchronously without blocking the GUI."""
        def _play():
            if HAS_WINSOUND:
                try:
                    winsound.PlaySound(self._cached_wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
                except Exception:
                    pass
        threading.Thread(target=_play, daemon=True).start()
