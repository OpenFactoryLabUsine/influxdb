import sys
import time
import numpy as np
import librosa
from scipy.stats import kurtosis
import warnings

warnings.filterwarnings("ignore")

SAMPLE_RATE = 22050
CHUNK_DURATION = 1.0
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
SENSOR_ID = "bras_robot"
WAV_FILE = "/etc/telegraf/test.wav"

def process_audio(chunk):
    # --------------------------------------------------------
    # 1. INDICATEURS TEMPORELS (Dynamique et Chocs)
    # --------------------------------------------------------
    rms = float(np.sqrt(np.mean(chunk**2)))
    
    if rms == 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [0.0] * 13

    # Facteur de crête (Crest Factor) : rapport entre le pic max et la moyenne RMS
    crest_factor = float(np.max(np.abs(chunk)) / rms)
    
    # Kurtosis : détection de chocs impulsifs (usure des roulements)
    kurt = float(kurtosis(chunk, fisher=False))
    
    # Zero Crossing Rate (ZCR) : taux de passage par zéro (bon pour détecter les frictions)
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(chunk)))

    # --------------------------------------------------------
    # 2. INDICATEURS SPECTRAUX (Fréquences)
    # --------------------------------------------------------
    fft_spectrum = np.fft.rfft(chunk)
    frequencies = np.fft.rfftfreq(len(chunk), d=1.0/SAMPLE_RATE)
    peak_freq = float(frequencies[np.argmax(np.abs(fft_spectrum))])
    
    # Centre de Gravité Spectral (la "brillance" du son)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=SAMPLE_RATE)))
    
    # Largeur de bande (dispersion des fréquences)
    bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(y=chunk, sr=SAMPLE_RATE)))
    
    # Roll-off : fréquence sous laquelle 85% de l'énergie se trouve
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=chunk, sr=SAMPLE_RATE, roll_percent=0.85)))

    # --------------------------------------------------------
    # 3. PROFIL SPECTRAL (MFCC  13 coefficients)
    # --------------------------------------------------------
    mfccs = librosa.feature.mfcc(y=chunk, sr=SAMPLE_RATE, n_mfcc=13)
    mfccs_mean = np.mean(mfccs, axis=1).tolist()

    return rms, crest_factor, kurt, zcr, peak_freq, centroid, bandwidth, rolloff, mfccs_mean

def main():
    try:
        y, _ = librosa.load(WAV_FILE, sr=SAMPLE_RATE)
    except Exception as e:
        print(f"Erreur de lecture: {e}", file=sys.stderr)
        sys.exit(1)

    total_samples = len(y)

    while True:
        for i in range(0, total_samples, CHUNK_SAMPLES):
            chunk = y[i:i + CHUNK_SAMPLES]
            
            if len(chunk) < CHUNK_SAMPLES:
                chunk = np.pad(chunk, (0, CHUNK_SAMPLES - len(chunk)), mode='constant')

            (rms, crest_factor, kurt, zcr, peak_freq, centroid, 
             bandwidth, rolloff, mfccs) = process_audio(chunk)
            
            timestamp_ns = time.time_ns()
            
            mfcc_str = ",".join([f"Mfcc{idx}={val:.4f}" for idx, val in enumerate(mfccs)])
            
            line = (
                f"Micro,sensor={SENSOR_ID} "
                f"Rms={rms:.6f},CrestFactor={crest_factor:.4f},Kurtosis={kurt:.4f},"
                f"Zcr={zcr:.4f},PeakFreq={peak_freq:.2f},Centroid={centroid:.2f},"
                f"Bandwidth={bandwidth:.2f},Rolloff={rolloff:.2f},"
                f"{mfcc_str} "
                f"{timestamp_ns}"
            )
            
            print(line)
            sys.stdout.flush()
            time.sleep(CHUNK_DURATION)
            
        print("Fin du fichier, redémarrage de la boucle...", file=sys.stderr)

if __name__ == "__main__":
    main()