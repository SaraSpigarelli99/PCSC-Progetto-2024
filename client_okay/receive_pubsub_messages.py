import json
import mysql.connector
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from datetime import datetime, timedelta
from collections import defaultdict

key_path = "C:/Users/Fincibec/OneDrive/Desktop/Pervasive and Cloud Computing/Progetto/OpenSmartHomeData (1)/OpenSmartHomeData/civic-source-442810-h8-9f4060aa9287.json"
credentials = service_account.Credentials.from_service_account_file(key_path)
project_id = "civic-source-442810-h8"
subscription_id = "smart_home_subscriptions3"

db_config = {
    "host": "34.154.88.50",
    "user": "smart-home-utente2",
    "password": "Ragnetto.99",
    "database": "smart-home-db2"
}

sensor_last_seen = defaultdict(lambda: None)

def save_to_database(data):
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        current_time = datetime.now()
        print(f"Orario attuale (server): {current_time}")

        for sensor in data["dati"]:
            sensor_name = sensor["sensore"]
            valore = sensor["valore"]

            # Controllo se il sensore era inattivo e ora è di nuovo attivo
            if sensor_name in sensor_last_seen and sensor_last_seen[sensor_name] is None:
                print(f"Sensor {sensor_name} is active again.")

            sensor_last_seen[sensor_name] = current_time
            print(f"Salvataggio: Sensore={sensor_name}, Valore={valore}, Timestamp={current_time}")

            query = """
                INSERT INTO sensor_data (timestamp, sensor_name, value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value)
            """
            cursor.execute(query, (current_time, sensor_name, valore))

        print("Stato attuale dei sensori:")
        for sensor, last_seen in sensor_last_seen.items():
            print(f" - {sensor}: Ultima lettura registrata alle {last_seen}")

        conn.commit()
    except mysql.connector.Error as e:
        print(f"Errore durante il salvataggio nel database: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("Connessione al database chiusa.")


def check_inactive_sensors():
    current_time = datetime.now()
    inactivity_threshold = timedelta(seconds=60)  # 10 minuti

    inactive_sensors = []
    for sensor, last_seen in sensor_last_seen.items():
        if last_seen and (current_time - last_seen > inactivity_threshold):
            inactive_sensors.append(sensor)

    if inactive_sensors:
        print(f"Sensori inattivi rilevati: {inactive_sensors}")
    else:
        print("Tutti i sensori sono attivi.")
    return inactive_sensors


def callback(message):
    try:
        print(f"Messaggio ricevuto: {message.data.decode('utf-8')}")
        data = json.loads(message.data.decode('utf-8'))
        save_to_database(data)
        check_inactive_sensors()  # Controlla i sensori inattivi dopo ogni messaggio
        message.ack()
    except Exception as e:
        print(f"Errore nella gestione del messaggio: {e}")
        message.nack()

def subscribe():
    subscriber = pubsub_v1.SubscriberClient(credentials=credentials)
    subscription_path = subscriber.subscription_path(project_id, subscription_id)

    print(f"Ascolto dei messaggi su {subscription_path}...")
    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)

    try:
        streaming_pull_future.result()
    except Exception as e:
        print(f"Errore nel subscriber: {e}")
        streaming_pull_future.cancel()


if __name__ == "__main__":
    subscribe()
