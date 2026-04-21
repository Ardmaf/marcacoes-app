from flask import Flask, request, render_template_string, redirect, session
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import psycopg2
import json
import os


# =========================
# SLOTS
# =========================
SLOTS = [
    "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "12:00", "12:30",
    "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00"
]

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = "supersecret"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# =========================
# DATABASE (POSTGRES)
# =========================
conn = psycopg2.connect(
    host="aws-0-eu-west-1.pooler.supabase.com",
    port=6543,
    database="postgres",
    user="postgres.ujfqfvneqigxaiukposa",
    password=os.environ["DB_PASSWORD"],
    sslmode="require"
)

cursor = conn.cursor()

cursor = db_query("""
CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    name TEXT,
    slug TEXT UNIQUE,
    profession TEXT,
    token TEXT,
    active INTEGER DEFAULT 1
)
""")

cursor = db_query("""
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER,
    client_name TEXT,
    service TEXT,
    date TEXT
)
""")

conn.commit()

def db_query(query, params=None):
    try:
        cursor = db_query(query, params or ())
        return cursor
    except Exception:
        conn.rollback()
        raise

# =========================
# ADMIN
# =========================
ADMIN_PASSWORD = "1234"

# =========================
# FUNÇÃO: SLOTS DISPONÍVEIS
# =========================
def get_available_slots(worker_id, date):
    cursor = db_query("""
        SELECT date FROM bookings
        WHERE worker_id=%s AND date LIKE %s
    """, (worker_id, date + "%"))

    booked = [row[0][11:16] for row in cursor.fetchall()]

    return [slot for slot in SLOTS if slot not in booked]

# =========================
# FORM
# =========================
FORM = """
<h2>{{ name }}</h2>

<form method="POST">
    <input name="nome" placeholder="Nome" required>

    <select name="servico">
        <option>Corte</option>
        <option>Barba</option>
        <option>Corte + Barba</option>
    </select>

    <input type="date" name="date" required>

    <select name="time">
        {% for slot in slots %}
            <option value="{{ slot }}">{{ slot }}</option>
        {% endfor %}
    </select>

    <button type="submit">Marcar</button>
</form>
"""

# =========================
# HOME
# =========================
from flask import render_template

@app.route("/")
def home():
    try:
        cursor = db_query("SELECT name, slug, profession FROM workers")
        rows = cursor.fetchall()
    except Exception as e:
        conn.rollback()
        return f"Erro na base de dados: {e}"

    workers = []

    for w in rows:
        workers.append({
            "name": w[0],
            "slug": w[1],
            "profession": w[2] if w[2] else "Outros"
        })

    return render_template("home.html", workers=workers)

# =========================
# WORKER PAGE (CLIENTE)
# =========================
@app.route("/<slug>", methods=["GET", "POST"])
def worker_public(slug):

    cursor = db_query(
        "SELECT id, name, token, active FROM workers WHERE slug=%s",
        (slug,)
    )
    worker = cursor.fetchone()

    if not worker or worker[3] == 0:
        return "Trabalhador não encontrado"

    worker_id = worker[0]
    name = worker[1]
    token = worker[2]

    # =========================
    # POST (CRIAR MARCAÇÃO)
    # =========================
    if request.method == "POST":
        nome = request.form["nome"]
        servico = request.form["servico"]
        date = request.form["date"]
        time = request.form["time"]

        data = f"{date} {time}"

        # verificar conflito
        cursor = db_query("""
            SELECT * FROM bookings
            WHERE worker_id=%s AND date=%s
        """, (worker_id, data))

        if cursor.fetchone():
            return "❌ Horário já ocupado"

        # guardar
        cursor = db_query("""
            INSERT INTO bookings (worker_id, client_name, service, date)
            VALUES (%s, %s, %s, %s)
        """, (worker_id, nome, servico, data))

        conn.commit()

        # GOOGLE CALENDAR
        if token:
            creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
            service = build("calendar", "v3", credentials=creds)

            event = {
                "summary": f"{servico} - {nome}",
                "start": {
                    "dateTime": data + ":00",
                    "timeZone": "Europe/Lisbon"
                },
                "end": {
                    "dateTime": f"{date} {time}:30",
                    "timeZone": "Europe/Lisbon"
                }
            }

            service.events().insert(calendarId="primary", body=event).execute()

        return "✅ Marcação feita com sucesso!"

    # =========================
    # GET (MOSTRAR SLOTS)
    # =========================
    date = request.form.get("date")

    available_slots = SLOTS

    return render_template_string(
        FORM,
        name=name,
        slots=available_slots
    )

# =========================
# ADMIN CREATE WORKER
# =========================
@app.route("/admin/create_worker", methods=["GET", "POST"])
def create_worker():

    # =========================
    # GET → mostra formulário
    # =========================
    if request.method == "GET":
        return """
        <h2>Criar Worker</h2>

        <form method="POST">
            Password:<br>
            <input name="password" type="password"><br><br>

            Nome:<br>
            <input name="name" required><br><br>

            Slug (URL):<br>
            <input name="slug" required><br><br>

            Profissão:<br>
            <input name="profession" placeholder="Barbeiro, Nails, Estética..."><br><br>

            <button type="submit">Criar Worker</button>
        </form>
        """

    # =========================
    # POST → cria worker
    # =========================
    if request.form.get("password") != ADMIN_PASSWORD:
        return "Acesso negado"

    name = request.form["name"]
    slug = request.form["slug"]
    profession = request.form.get("profession", "Outros")

    cursor = db_query(
        "INSERT INTO workers (name, slug, profession) VALUES (%s, %s, %s)",
        (name, slug, profession)
    )

    conn.commit()

    return f"Worker criado com sucesso: /{slug}"

# =========================
# ADMIN DEACTIVATE
# =========================
@app.route("/admin/deactivate", methods=["POST"])
def deactivate_worker():

    if request.form.get("password") != ADMIN_PASSWORD:
        return "Acesso negado"

    slug = request.form["slug"]

    cursor = db_query("""
        UPDATE workers SET active=0 WHERE slug=%s
    """, (slug,))

    conn.commit()

    return "Worker desativado"

# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
