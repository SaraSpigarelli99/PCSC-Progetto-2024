from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from secret import SECRET_KEY
import matplotlib.pyplot as plt
from datetime import datetime
import io
import base64
import pandas as pd
import matplotlib.dates as mdates
import mpld3

app = Flask(__name__)
app.secret_key = SECRET_KEY

db_config = {
    "host": "34.121.25.220",
    "user": "smart-home-utente",
    "password": "Ragnetto.99",
    "database": "smart-home-db"
}


def get_db_connection():
    return mysql.connector.connect(**db_config)


@app.route('/')
def home():
    # Reindirizza subito alla pagina di registrazione
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
            # Utente non registrato
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
    if 'username' not in session:
        flash("Devi effettuare il login per accedere alla dashboard.")
        return redirect(url_for('login'))

    # Recupero il range di date dal db
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT MIN(timestamp) AS earliest, MAX(timestamp) AS latest FROM sensor_data")
    result = cursor.fetchone()

    earliest = result['earliest']
    latest = result['latest']
    earliest_date_str = earliest.strftime('%Y-%m-%d') if earliest else None
    latest_date_str = latest.strftime('%Y-%m-%d') if latest else None

    # Recupero le stanze disponibili
    cursor.execute("SELECT DISTINCT SUBSTRING_INDEX(sensor_name, '_', 1) AS room FROM sensor_data")
    rooms = [row['room'] for row in cursor.fetchall()]

    # Controllo stato sensori (ultimi dati ricevuti)
    cursor.execute("SELECT sensor_name, MAX(timestamp) AS last_ts FROM sensor_data GROUP BY sensor_name")
    sensors_data = cursor.fetchall()
    cursor.close()
    conn.close()

    # Definisco la soglia di inattività (es: 60 secondi)
    inactivity_threshold = 600
    now = datetime.now()
    inactive_sensors = []
    for row in sensors_data:
        sensor = row['sensor_name']
        last_ts = row['last_ts']
        if last_ts is not None:
            diff = now - last_ts
            if diff.total_seconds() > inactivity_threshold:
                inactive_sensors.append(sensor)

    if inactive_sensors:
        flash(
            f"Attenzione: i seguenti sensori non producono dati da più di {inactivity_threshold} secondi: {', '.join(inactive_sensors)}")

    # Aggiungo "All" e ordino le stanze
    rooms = sorted(rooms)
    rooms.insert(0, "All")

    graph = None

    if request.method == 'POST':
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        selected_room = request.form.get('room')

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

            # Gestione duplicati con pivot_table
            df_pivot = df.pivot_table(index='timestamp', columns='sensor_name', values='value', aggfunc='mean')

            fig, ax = plt.subplots(figsize=(12, 8))
            df_pivot.plot(marker='o', ax=ax)

            if selected_room == "All":
                plt.title('Dati sensori - Tutta la casa')
            else:
                plt.title(f'Dati sensori per la stanza: {selected_room}')

            plt.xlabel('Data/Ora')
            plt.ylabel('Valore')
            plt.grid(True)
            plt.legend(title='Sensori', bbox_to_anchor=(1.05, 1), loc='upper left')

            # Formattazione asse X per data/ora
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m %H:%M'))
            ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
            plt.tight_layout()

            # Grafico interattivo con mpld3
            graph = mpld3.fig_to_html(fig)

    return render_template('dashboard.html',
                           graph=graph,
                           earliest_date=earliest_date_str,
                           latest_date=latest_date_str,
                           rooms=rooms)


@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logout effettuato.")
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(debug=True)
