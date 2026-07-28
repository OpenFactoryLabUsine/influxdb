import sys
import threading
import time
import pyodbc
import re
import os

# --- CONFIGURATION ---
DB_CONN = os.environ.get("SQL_DB_CONN")
CACHE_REFRESH_INTERVAL = 60

active_assets_cache = set()
cache_lock = threading.Lock()

def fetch_active_assets():
    """Exécute la requête SQL et met à jour le cache."""
    query = """
        SELECT e.OpenFactoryAssetUuid 
        FROM VariableRecordingRequest v
        JOIN Equipment e ON v.EquipmentId = e.Id
        WHERE (v.LocalEndTime IS NULL OR v.LocalEndTime = '')
        AND v.Statut = 'TelegrafAutomation'
    """
    try:
        conn = pyodbc.connect(DB_CONN)
        cursor = conn.cursor()
        cursor.execute(query)
        
        new_active_assets = {str(row[0]).strip() for row in cursor.fetchall()}
        
        with cache_lock:
            global active_assets_cache
            active_assets_cache = new_active_assets
            
        conn.close()
    except Exception as e:
        sys.stderr.write(f"Erreur SQL: {e}\n")
        sys.stderr.flush()

def update_cache_loop():
    """Boucle d'arrière-plan."""
    while True:
        time.sleep(CACHE_REFRESH_INTERVAL)
        fetch_active_assets()

def process_metrics():
    # 1. Remplir le cache AVANT de commencer à lire les métriques
    fetch_active_assets()
    
    # 2. Lancer la mise à jour périodique
    cache_thread = threading.Thread(target=update_cache_loop, daemon=True)
    cache_thread.start()

    uuid_regex = re.compile(r'AssetUuid=([^,\s]+)')

    while True:
        line = sys.stdin.readline()
        if not line:
            break
            
        line = line.strip()
        if not line:
            continue

        match = uuid_regex.search(line)
        target_bucket = "ephemeral"
        
        if match:
            asset_uuid = match.group(1)
            with cache_lock:
                if asset_uuid in active_assets_cache:
                    target_bucket = "lifetime"

        parts = line.split(" ", 1)
        if len(parts) == 2:
            tags_part, rest = parts
            new_line = f"{tags_part},TargetBucket={target_bucket} {rest}\n"
            sys.stdout.write(new_line)
            sys.stdout.flush()

if __name__ == "__main__":
    process_metrics()