import sys
import time
import os
import io
import uuid
import json
import numpy as np
import librosa
import scipy.io.wavfile as wavfile
from scipy.stats import kurtosis
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

SAMPLE_RATE = 22050
CHUNK_DURATION = 1.0
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)
SENSOR_ID = "bras_robot"

ASSET_UUID = "bras_robot_001"
WAV_FILE = "/etc/telegraf/test.wav"

# --------------------------------------------------------
# CONFIGURATION ALARIK (S3) via Boto3
# --------------------------------------------------------
ALARIK_ENDPOINT = os.getenv("ALARIK_ENDPOINT", "alarik:8080")
ALARIK_ACCESS_KEY = os.getenv("ALARIK_ACCESS_KEY")
ALARIK_SECRET_KEY = os.getenv("ALARIK_SECRET_KEY")
BUCKET_NAME = "labusine"

try:
    # Initialisation du client Boto3
    s3_client = boto3.client(
        's3',
        endpoint_url=f"http://{ALARIK_ENDPOINT}",
        aws_access_key_id=ALARIK_ACCESS_KEY,
        aws_secret_access_key=ALARIK_SECRET_KEY
    )
    
    # Vérification de l'existence du bucket, et création si absent
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            s3_client.create_bucket(Bucket=BUCKET_NAME)
        else:
            raise
except Exception as e:
    print(f"Erreur d'initialisation Alarik: {e}", file=sys.stderr)
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
    
    wav_io = io.BytesIO()
    wavfile.write(wav_io, SAMPLE_RATE, chunk)
    
    try:
        # Envoi via Boto3 (getvalue() extrait directement les octets du buffer)
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=filename,
            Body=wav_io.getvalue(),
            ContentType="audio/wav"
        )
        return filename
    except Exception as e:
        print(f"Erreur d'upload Alarik pour {filename}: {e}", file=sys.stderr)
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
            created_at = datetime.utcnow().isoformat() + "Z"
            
            audio_filename = upload_chunk(chunk, timestamp_ns)
            
            metrics = {
                "Rms": round(rms, 6),
                "CrestFactor": round(crest_factor, 4),
                "Kurtosis": round(kurt, 4),
                "Zcr": round(zcr, 4),
                "PeakFreq": round(peak_freq, 2),
                "Centroid": round(centroid, 2),
                "Bandwidth": round(bandwidth, 2),
                "Rolloff": round(rolloff, 2),
                "AudioFile": audio_filename
            }
            
            for idx, val in enumerate(mfccs):
                metrics[f"Mfcc{idx}"] = round(val, 4)
            
            json_payload = json.dumps(metrics).replace('"', '\\"')
            
            line = (
                f"AssetsMetrics,"
                f"AssetUuid={ASSET_UUID},Id={SENSOR_ID},Type=AudioSensor,Tag=AudioAnalysis "
                f"Value=\"{json_payload}\",CreatedAt=\"{created_at}\" "
                f"{timestamp_ns}"
            )
            
            print(line)
            sys.stdout.flush()
            time.sleep(CHUNK_DURATION)
            
        print("Fin du fichier, redémarrage de la boucle...", file=sys.stderr)

if __name__ == "__main__":
    main()