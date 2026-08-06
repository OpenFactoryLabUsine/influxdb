import sys
import time
import os
import io
import numpy as np
import librosa
import scipy.io.wavfile as wavfile
from scipy.stats import kurtosis
from minio import Minio
import warnings

warnings.filterwarnings("ignore")

SAMPLE_RATE = 22050
CHUNK_DURATION = 1.0
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
SENSOR_ID = "bras_robot"
WAV_FILE = "/etc/telegraf/test.wav"

# CONFIGURATION MINIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD")
BUCKET_NAME = "labusine"

try:
    minio_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    # Création du bucket s'il n'existe pas
    if not minio_client.bucket_exists(BUCKET_NAME):
        minio_client.make_bucket(BUCKET_NAME)
except Exception as e:
    print(f"Erreur d'initialisation MinIO: {e}", file=sys.stderr)
    sys.exit(1)


def process_audio(chunk):
    rms = float(np.sqrt(np.mean(chunk**2)))
    
    if rms == 0.0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [0.0] * 13

    crest_factor = float(np.max(np.abs(chunk)) / rms)
    kurt = float(kurtosis(chunk, fisher=False))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(chunk)))

    fft_spectrum = np.fft.rfft(chunk)
    frequencies = np.fft.rfftfreq(len(chunk), d=1.0/SAMPLE_RATE)
    peak_freq = float(frequencies[np.argmax(np.abs(fft_spectrum))])
    
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=SAMPLE_RATE)))
    bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(y=chunk, sr=SAMPLE_RATE)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=chunk, sr=SAMPLE_RATE, roll_percent=0.85)))

    mfccs = librosa.feature.mfcc(y=chunk, sr=SAMPLE_RATE, n_mfcc=13)
    mfccs_mean = np.mean(mfccs, axis=1).tolist()

    return rms, crest_factor, kurt, zcr, peak_freq, centroid, bandwidth, rolloff, mfccs_mean

def upload_chunk(chunk, timestamp_ns):
    filename = f"{SENSOR_ID}_{timestamp_ns}.wav"
    
    # 1. Création d'un fichier virtuel en mémoire
    wav_io = io.BytesIO()
    
    # 2. Écriture des données audio dans ce buffer virtuel
    wavfile.write(wav_io, SAMPLE_RATE, chunk)
    
    # 3. On remet le curseur de lecture au début du buffer avant l'upload
    wav_io.seek(0)
    
    try:
        minio_client.put_object(
            BUCKET_NAME,
            filename,
            wav_io,
            length=wav_io.getbuffer().nbytes,
            content_type="audio/wav"
        )
        return filename
    except Exception as e:
        print(f"Erreur d'upload MinIO pour {filename}: {e}", file=sys.stderr)
        return "upload_failed"

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
            
            # UPLOAD DU CHUNK
            # On passe le chunk brut et le timestamp pour générer un nom unique
            audio_filename = upload_chunk(chunk, timestamp_ns)
            
            mfcc_str = ",".join([f"Mfcc{idx}={val:.4f}" for idx, val in enumerate(mfccs)])
            
            # FORMATAGE INFLUXDB line protocol
            line = (
                f"Micro,sensor={SENSOR_ID} "
                f"Rms={rms:.6f},CrestFactor={crest_factor:.4f},Kurtosis={kurt:.4f},"
                f"Zcr={zcr:.4f},PeakFreq={peak_freq:.2f},Centroid={centroid:.2f},"
                f"Bandwidth={bandwidth:.2f},Rolloff={rolloff:.2f},"
                f"{mfcc_str},"
                f"AudioFile=\"{audio_filename}\" "
                f"{timestamp_ns}"
            )
            
            print(line)
            sys.stdout.flush()
            time.sleep(CHUNK_DURATION)
            
        print("Fin du fichier, redémarrage de la boucle...", file=sys.stderr)

if __name__ == "__main__":
    main()