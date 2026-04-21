from flask import Flask, request, render_template, render_template_string
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import psycopg2
import json
import os

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = "supersecret"

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

ADMIN_PASSWORD = "1234"

# =========================
# DATABASE CONNECTION
# =========================
conn = psycopg2.connect(
    host="aws-0-eu-west-1.pooler.supabase.com",
    port=6543,
    database="postgres",
    user="postgres.ujfqfvneqigxaiukposa",
    password=os.environ["DB_PASSWORD"],
    sslmode="require"
)

conn.autocommit = True


# =========================
# DB FUNCTION (CORRIGIDA E SEGURA)
# =========================
def db_query(query, params=None):
    try:
        cur = conn.cursor()
        cur.execute(query, params or ())
        return cur
    except Exception as e:
        conn.rollback()
        print("DB ERROR:", e)
        return None


# =========================
# CREATE TABLES
# =========================
db_query("""
CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    name TEXT,
    slug TEXT UNIQUE,
    profession TEXT,
    token TEXT,
    active INTEGER DEFAULT 1
)
""")

db_query("""
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER,
    client_name TEXT,
    service TEXT,
    date TEXT
)
""")


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
# HOME
# =========================
@app.route("/")
def home():
    cur = db_query("SELECT name, slug, profession FROM workers")

    rows = cur.fetchall() if cur else []

    workers = [
        {"name": w[0], "slug": w[1], "profession": w[2] or "Outros"}
        for w in rows
    ]

    return render_template("home.html", workers=workers)


# =========================
# WORKER PAGE
# =========================
@app.route("/<slug>", methods=["GET", "POST"])
def worker_public(slug):

    cur = db_query(
        "SELECT id, name, token, active FROM workers WHERE slug=%s",
        (slug,)
    )

    worker = cur.fetchone() if cur else None

    if not worker or worker[3] == 0:
        return "Trabalhador não encontrado"

    worker_id = worker[0]
    name = worker[1]
    token = worker[2]

    date = request.args.get("date", "")

    # =========================
    # POST BOOKING
    # =========================
    if request.method == "POST":

        nome = request.form["nome"]
        servico = request.form["servico"]
        date = request.form["date"]
        time = request.form["time"]

        data = f"{date} {time}"

        cur = db_query(
            "SELECT * FROM bookings WHERE worker_id=%s AND date=%s",
            (worker_id, data)
        )

        if cur and cur.fetchone():
            return "❌ Horário já ocupado"

        db_query("""
            INSERT INTO bookings (worker_id, client_name, service, date)
            VALUES (%s, %s, %s, %s)
        """, (worker_id, nome, servico, data))

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
    # GET SLOTS
    # =========================
    available_slots = SLOTS

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="pt">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ name }}</title>

    <style>
    body{
        font-family: Arial;
        background: #0b0b10;
        color:white;
    }
    .container{
        max-width:500px;
        margin:auto;
        padding:20px;
    }
    </style>

    </head>
    <body>

    <div class="container">

    <h2>{{ name }}</h2>

    <form method="POST">
        <input name="nome" placeholder="Nome" required><br><br>

        <select name="servico">
            <option>Corte</option>
            <option>Barba</option>
            <option>Corte + Barba</option>
        </select><br><br>

        <input type="date" name="date" required><br><br>

        <select name="time">
            {% for slot in slots %}
                <option value="{{ slot }}">{{ slot }}</option>
            {% endfor %}
        </select><br><br>

        <button type="submit">Marcar</button>
    </form>

    </div>

    </body>
    </html>
    """, name=name, slots=available_slots)


# =========================
# ADMIN CREATE WORKER
# =========================
@app.route("/admin/create_worker", methods=["GET", "POST"])
def create_worker():

    if request.method == "GET":
        return """
        <form method="POST">
            Password: <input name="password"><br>
            Nome: <input name="name"><br>
            Slug: <input name="slug"><br>
            Profissão: <input name="profession"><br>
            <button type="submit">Criar</button>
        </form>
        """

    if request.form.get("password") != ADMIN_PASSWORD:
        return "Acesso negado"

    db_query(
        "INSERT INTO workers (name, slug, profession) VALUES (%s, %s, %s)",
        (request.form["name"], request.form["slug"], request.form.get("profession", "Outros"))
    )

    return f"Worker criado: /{request.form['slug']}"


# =========================
# ADMIN DEACTIVATE
# =========================
@app.route("/admin/deactivate", methods=["POST"])
def deactivate_worker():

    if request.form.get("password") != ADMIN_PASSWORD:
        return "Acesso negado"

    db_query(
        "UPDATE workers SET active=0 WHERE slug=%s",
        (request.form["slug"],)
    )

    return "Worker desativado"


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
