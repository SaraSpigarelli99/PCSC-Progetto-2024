import os
import time
import pandas as pd
import json
from collections import defaultdict
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from datetime import datetime

# === CONFIGURAZIONI ===
SENSOR_DIRECTORY = "C:/Users/saras/PycharmProjects/OpenSmartHomeData-master/Measurements"
SEND_INTERVAL = 1  # secondi di attesa tra invii

# Credenziali GCP
key_path = "C:/Users/saras/PycharmProjects/OpenSmartHomeData-master/civic-source-442810-h8-9f4060aa9287.json"
credentials = service_account.Credentials.from_service_account_file(key_path)

# Config Pub/Sub
project_id = "civic-source-442810-h8"
topic_id = "smart_home_data2"
client = pubsub_v1.PublisherClient(credentials=credentials)
project_path = f"projects/{project_id}/topics/{topic_id}"


def load_data():
    """Carica i dati dei sensori dai file CSV in un dizionario {sensore: DataFrame}."""
    sensors_data = {}
    for file_name in os.listdir(SENSOR_DIRECTORY):
        if file_name.endswith(".csv"):
            file_path = os.path.join(SENSOR_DIRECTORY, file_name)
            df = pd.read_csv(file_path, header=None, names=["timestamp", "valore"], sep='\t')

            # Converti i timestamp del 2017 in date odierne
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["timestamp"] = df["timestamp"].apply(lambda x: x.replace(year=datetime.now().year))

            sensor_name = file_name.replace('.csv', '')
            sensors_data[sensor_name] = df
    return sensors_data


def read_and_send_data():
    # Carica i dati iniziali
    sensors_data = load_data()
    sensors_indices = {s: 0 for s in sensors_data}
    previously_removed_sensors = set()

    while True:
        # Controlla se i file dei sensori esistono ancora
        current_sensors = set(os.listdir(SENSOR_DIRECTORY))
        active_sensors = set(sensors_data.keys())

        for s in list(sensors_data.keys()):
            file_path = os.path.join(SENSOR_DIRECTORY, s + ".csv")
            if not os.path.exists(file_path):
                print(f"Sensor {s} file removed, stop producing data.")
                del sensors_data[s]
                del sensors_indices[s]
                previously_removed_sensors.add(s)

        # Controlla se nuovi file sono stati aggiunti
        new_files = set(os.listdir(SENSOR_DIRECTORY))
        for file_name in new_files:
            if file_name.endswith(".csv"):
                sensor_name = file_name.replace('.csv', '')
                if sensor_name in previously_removed_sensors:
                    print(f"Sensor {sensor_name} file re-added, resuming data production.")
                    previously_removed_sensors.remove(sensor_name)
                    file_path = os.path.join(SENSOR_DIRECTORY, file_name)
                    df = pd.read_csv(file_path, header=None, names=["timestamp", "valore"], sep='\t')

                    # Converti i timestamp del 2017 in date odierne
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df["timestamp"] = df["timestamp"].apply(lambda x: x.replace(year=datetime.now().year))

                    sensors_data[sensor_name] = df
                    sensors_indices[sensor_name] = 0

        # Se non ci sono sensori, attendi prima di riprovare a caricare
        if not sensors_data:
            print("No sensors available. Waiting before re-checking.")
            time.sleep(5)
            sensors_data = load_data()
            for s in sensors_data:
                if s not in sensors_indices:
                    sensors_indices[s] = 0
            continue

        data_by_timestamp = defaultdict(list)

        # Invia una lettura per ogni sensore in questo ciclo
        for sensor_name, df in sensors_data.items():
            if len(df) == 0:
                continue

            idx = sensors_indices[sensor_name]
            row = df.iloc[idx]
            # Usa datetime.now() per avere timestamp sempre aggiornati
            current_timestamp = datetime.now().timestamp()
            valore = float(row["valore"])

            data_by_timestamp[current_timestamp].append({
                "sensore": sensor_name,
                "valore": valore
            })

            # Passa alla riga successiva, tornando a 0 se arrivi in fondo
            idx = (idx + 1) % len(df)
            sensors_indices[sensor_name] = idx

        # Invia i dati raccolti
        for t, values in data_by_timestamp.items():
            payload = {
                "timestamp": float(t),
                "dati": values
            }
            payload_json = json.dumps(payload)
            payload_bytes = payload_json.encode('utf-8')
            client.publish(project_path, data=payload_bytes)
            print(f"Sent to {project_path}: {payload_json}")

        time.sleep(SEND_INTERVAL)


if __name__ == "__main__":
    read_and_send_data()
