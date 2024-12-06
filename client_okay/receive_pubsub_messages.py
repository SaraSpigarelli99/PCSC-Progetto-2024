import json
import mysql.connector
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from datetime import datetime

key_path = "C:/Users/saras/PycharmProjects/OpenSmartHomeData/civic-source-442810-h8-9f4060aa9287.json"
credentials = service_account.Credentials.from_service_account_file(key_path)
project_id = "civic-source-442810-h8"
subscription_id = "smart_home_subscriptions"

db_config = {
    "host": "34.121.25.220",
    "user": "smart-home-utente",
    "password": "Ragnetto.99",
    "database": "smart-home-db"
}


def save_to_database(data):
    conn = None
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        unix_ts = float(data["timestamp"])
        dt = datetime.fromtimestamp(
            unix_ts)  # dt dovrebbe essere l'ora corrente se inviato da client.py con datetime.now()

        # DEBUG: stampa il timestamp per capire se è attuale
        print(f"Sto per inserire dati con timestamp={dt} (now={datetime.now()})")

        for sensor in data["dati"]:
            query = """
                INSERT INTO sensor_data (timestamp, sensor_name, value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE value = VALUES(value)
            """
            cursor.execute(query, (dt, sensor["sensore"], sensor["valore"]))
            print(
                f"Inserito/Aggiornato nel database: timestamp={dt}, sensore={sensor['sensore']}, valore={sensor['valore']}")

        conn.commit()
    except mysql.connector.Error as e:
        print(f"Errore durante il salvataggio nel database: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
            print("Connessione al database chiusa.")


def callback(message):
    try:
        print(f"Messaggio ricevuto: {message.data.decode('utf-8')}")
        data = json.loads(message.data.decode('utf-8'))
        save_to_database(data)
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
