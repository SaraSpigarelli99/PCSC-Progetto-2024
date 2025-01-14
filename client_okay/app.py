import mysql.connector
import matplotlib.pyplot as plt
import mpld3
import pandas as pd
import matplotlib.dates as mdates

from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, timedelta
from collections import defaultdict
from secret import SECRET_KEY

app = Flask(__name__, template_folder="template", static_folder='static')
app.secret_key = SECRET_KEY

db_config = {
    "host": "34.154.88.50",
    "user": "smart-home-utente2",
    "password": "Ragnetto.99",
    "database": "smart-home-db2"
}

# Dizionario per tracciare gli ultimi timestamp visti per ogni sensore
sensor_last_seen = defaultdict(lambda: None)


def get_db_connection():
    return mysql.connector.connect(**db_config)


@app.route('/')
def home():
    return redirect(url_for('register'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user:
            flash("Utente già registrato. Effettua il login.")
            cursor.close()
            conn.close()
            return redirect(url_for('login'))
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Registrazione avvenuta con successo! Ora puoi effettuare il login.")
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user is None:
            flash("Utente non registrato")
            return redirect(url_for('login'))
        else:
            if user['password'] == password:
                session['username'] = user['username']
                return redirect(url_for('dashboard'))
            else:
                flash("Username o password errati")
                return redirect(url_for('login'))

    return render_template('login.html')




@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    import os

    if 'username' not in session:
        flash("Devi effettuare il login per accedere alla dashboard.")
        return redirect(url_for('login'))

    # Recupero il range di date dal database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT MIN(timestamp) AS earliest, MAX(timestamp) AS latest FROM sensor_data")
    result = cursor.fetchone()

    earliest = result['earliest']
    latest = result['latest']
    earliest_date_str = earliest.strftime('%Y-%m-%d') if earliest else None
    today_date_str = datetime.today().strftime('%Y-%m-%d')  # Data di oggi come limite massimo

    # Recupero le stanze disponibili
    cursor.execute("SELECT DISTINCT SUBSTRING_INDEX(sensor_name, '_', 1) AS room FROM sensor_data")
    rooms = [row['room'] for row in cursor.fetchall()]

    # Controllo stato sensori (ultimi dati ricevuti)
    cursor.execute("SELECT sensor_name, MAX(timestamp) AS last_ts FROM sensor_data GROUP BY sensor_name")
    sensors_data = cursor.fetchall()

    # Verifica file CSV attivi
    sensor_directory = "C:/Users/saras/PycharmProjects/OpenSmartHomeData-master/Measurements"
    active_sensors = set()
    if os.path.exists(sensor_directory):
        for file_name in os.listdir(sensor_directory):
            if file_name.endswith(".csv"):
                sensor_name = file_name.replace('.csv', '')
                active_sensors.add(sensor_name)

    cursor.close()
    conn.close()

    # Definisco la soglia di inattività (es: 600 secondi)
    inactivity_threshold = 600
    now = datetime.now()
    inactive_sensors = []
    for row in sensors_data:
        sensor = row['sensor_name']
        last_ts = row['last_ts']
        if last_ts is not None:
            diff = now - last_ts
            if diff.total_seconds() > inactivity_threshold or sensor not in active_sensors:
                inactive_sensors.append(sensor)

    # Mostra un messaggio flash per i sensori inattivi
    if inactive_sensors:
        flash(f"Attenzione: i seguenti sensori sono inattivi o non producono dati: {', '.join(inactive_sensors)}")

    # Filtra solo le stanze relative ai sensori attivi
    rooms = [r for r in rooms if any(r in s for s in active_sensors)]
    rooms = sorted(rooms)
    rooms.insert(0, "All")

    # Date di default
    start_date_str = earliest_date_str  # La data più antica come valore iniziale
    end_date_str = today_date_str       # La data di oggi come valore finale

    graph, brightness_graph, humidity_graph = None, None, None

    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        selected_room = request.form.get('room', 'All')

        # Controllo che la data di fine non sia futura
        if end_date_str > today_date_str:
            flash("Non è possibile selezionare date future.")
            return redirect(url_for('dashboard'))

        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        end_dt = end_dt.replace(hour=23, minute=59, second=59)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if selected_room == "All":
            query = """
                SELECT timestamp, sensor_name, value
                FROM sensor_data
                WHERE timestamp BETWEEN %s AND %s
                ORDER BY timestamp
            """
            cursor.execute(query, (start_dt, end_dt))
        else:
            query = """
                SELECT timestamp, sensor_name, value
                FROM sensor_data
                WHERE timestamp BETWEEN %s AND %s
                  AND sensor_name LIKE %s
                ORDER BY timestamp
            """
            cursor.execute(query, (start_dt, end_dt, f"{selected_room}_%"))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if rows:
            df = pd.DataFrame(rows)
            # Escludi sensori inattivi dai grafici
            active_sensor_names = [s for s in active_sensors if s in df['sensor_name'].unique()]
            df = df[df['sensor_name'].isin(active_sensor_names)]
            df_pivot = df.pivot_table(index='timestamp', columns='sensor_name', values='value', aggfunc='mean')

            # Grafico luminosità
            brightness_sensors = [col for col in df_pivot.columns if 'Brightness' in col]
            if brightness_sensors:
                fig, ax = plt.subplots(figsize=(12, 6))
                df_pivot[brightness_sensors].plot(marker='o', ax=ax, linewidth=0.5)
                plt.title('Luminosità', fontsize=16)
                plt.xlabel('Orario', fontsize=14, labelpad=-15)
                plt.ylabel('Valore', fontsize=14)
                plt.grid(True)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
                ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
                plt.tight_layout()
                plt.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=12)
                brightness_graph = mpld3.fig_to_html(fig)

            # Grafico umidità
            humidity_sensors = [col for col in df_pivot.columns if 'Humidity' in col]
            if humidity_sensors:
                fig, ax = plt.subplots(figsize=(12, 6))
                df_pivot[humidity_sensors].plot(marker='o', ax=ax, linewidth=0.5)
                plt.title('Umidità', fontsize=16)
                plt.xlabel('Orario', fontsize=14, labelpad=-15)
                plt.ylabel('Valore', fontsize=14)
                plt.grid(True)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
                ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
                plt.tight_layout()
                plt.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=12)
                humidity_graph = mpld3.fig_to_html(fig)

            # Grafico altri dati
            other_sensors = [col for col in df_pivot.columns if 'Brightness' not in col and 'Humidity' not in col]
            if other_sensors:
                fig, ax = plt.subplots(figsize=(14, 8))
                df_pivot[other_sensors].plot(marker='o', ax=ax, linewidth=0.5)
                plt.title('Temperatura', fontsize=16)
                plt.xlabel('Orario', fontsize=14, labelpad=-15)
                plt.ylabel('Valore', fontsize=14)
                plt.grid(True)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
                ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
                plt.tight_layout()
                plt.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=12)
                graph = mpld3.fig_to_html(fig)

    return render_template('dashboard.html',
                           graph=graph,
                           brightness_graph=brightness_graph,
                           humidity_graph=humidity_graph,
                           earliest_date=earliest_date_str,
                           latest_date=today_date_str,  # Usa la data di oggi come massimo
                           rooms=rooms,
                           start_date=start_date_str,
                           end_date=end_date_str)





@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logout effettuato.")
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(debug=True)
