"""RGB waveform data generation for the frontend visualizer.

Splits the spectrogram into 3 frequency bands (low/mid/high)
and computes per-band RMS energy. The frontend Canvas renderer maps:
  R = low (bass, 0–250 Hz)
  G = mid (250 Hz–4 kHz)
  B = high (4 kHz+)
"""

import librosa
import numpy as np


def compute_rgb_waveform(
    signal: np.ndarray, sr: int, target_fps: int = 60
) -> dict:
    """Compute 3-band waveform amplitude data.

    Returns dict with low/mid/high arrays (values 0–1) at target_fps,
    ready for Canvas rendering where R=low, G=mid, B=high.
    """
    n_fft = 2048
    hop_length = max(1, sr // target_fps)

    S = np.abs(librosa.stft(signal, n_fft=n_fft, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    # Frequency band masks
    low_mask  = freqs <= 250
    mid_mask  = (freqs > 250) & (freqs <= 4000)
    high_mask = freqs > 4000

    # RMS energy per band per frame
    low  = np.sqrt(np.mean(S[low_mask]  ** 2, axis=0))
    mid  = np.sqrt(np.mean(S[mid_mask]  ** 2, axis=0))
    high = np.sqrt(np.mean(S[high_mask] ** 2, axis=0))

    def normalize(arr):
        mx = np.max(arr)
        if mx > 0:
            return (arr / mx).tolist()
        return arr.tolist()

    return {
        "sample_rate": target_fps,
        "duration": float(len(signal) / sr),
        "low": normalize(low),
        "mid": normalize(mid),
        "high": normalize(high),
    }
