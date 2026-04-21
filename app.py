from flask import Flask, request, render_template_string, redirect, session
import sqlite3
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json
import os

print("🔥🔥🔥 APP ATUALIZADA 🔥🔥🔥")
SLOTS = [
    "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "12:00", "12:30",
    "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00"
]

app = Flask(__name__)
app.secret_key = "supersecret"

# =========================
# GOOGLE OAUTH
# =========================
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# =========================
# BASE DE DADOS
# =========================
import psycopg2
import os

conn = psycopg2.connect(
    host="aws-0-eu-west-1.pooler.supabase.com",
    port=6543,
    database="postgres",
    user="postgres.ujfqfvneqigxaiukposa",
    password=os.environ["DB_PASSWORD"],
    sslmode="require"
)

cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    name TEXT,
    slug TEXT UNIQUE,
    token TEXT,
    active INTEGER DEFAULT 1
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER,
    client_name TEXT,
    service TEXT,
    date TEXT
)
""")

conn.commit()

# =========================
# ADMIN
# =========================
ADMIN_PASSWORD = "1234"

# =========================
# FORM CLIENTE
# =========================
FORM = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marcações</title>
    <style>
        body {
            font-family: Arial;
            background: #0f0f0f;
            color: white;
            margin: 0;
            padding: 20px;
        }

        .container {
            max-width: 420px;
            margin: auto;
            background: #1c1c1c;
            padding: 20px;
            border-radius: 12px;
        }

        h2 {
            text-align: center;
            margin-bottom: 20px;
        }

        input, select, button {
            width: 100%;
            padding: 12px;
            margin-top: 10px;
            border-radius: 8px;
            border: none;
            font-size: 16px;
        }

        input, select {
            background: #2a2a2a;
            color: white;
        }

        button {
            background: #4CAF50;
            color: white;
            font-weight: bold;
            cursor: pointer;
            margin-top: 20px;
        }

        button:hover {
            background: #45a049;
        }

        .slots {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-top: 10px;
        }

        .slot {
            background: #2a2a2a;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            cursor: pointer;
        }

        .slot:hover {
            background: #3a3a3a;
        }
    </style>
</head>
<body>

<div class="container">
    <h2>{{ name }}</h2>

    <form method="POST">

        <input name="nome" placeholder="O teu nome" required>

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

        <button type="submit">Marcar Agora</button>

    </form>
</div>

</body>
</html>
"""

# =========================
# PÁGINA PÚBLICA (CLIENTE)
# =========================
@app.route("/")
def home():
    return "Sistema de marcações online ativo por mais tempo 🚀"

@app.route("/debug2")
def debug2():
    return "WORKER ROUTE ATUAL"
    
@app.route("/<slug>", methods=["GET", "POST"])
    
def worker_public(slug):
    cursor.execute("SELECT id, name, token, active FROM workers WHERE slug=%s", (slug,))
    worker = cursor.fetchone()

    if not worker or worker[3] == 0:
        return "Trabalhador não encontrado"

    worker_id = worker[0]
    name = worker[1]
    token = worker[2]

    if request.method == "POST":
        nome = request.form["nome"]
        servico = request.form["servico"]
        date = request.form["date"]
        time = request.form["time"]
        data = f"{date}T{time}:00"

        # 🚫 VERIFICAR SE JÁ EXISTE MARCAÇÃO
        cursor.execute("""
            SELECT * FROM bookings 
            WHERE worker_id=%s AND date=%s
        """, (worker_id, data))

        existing = cursor.fetchone()

        if existing:
            return "❌ Este horário já está ocupado. Escolhe outro."

        # ✅ GUARDAR MARCAÇÃO
        cursor.execute("""
            INSERT INTO bookings (worker_id, client_name, service, date)
            VALUES (%s, %s, %s, %s)
        """, (worker_id, nome, servico, data))
        conn.commit()
def get_available_slots(worker_id, date):
   
    cursor.execute("""
        SELECT date FROM bookings
        WHERE worker_id=%s AND date LIKE %s
    """, (worker_id, date + "%"))

    booked = [row[0][11:16] for row in cursor.fetchall()]

    return [slot for slot in SLOTS if slot not in booked]
    
        # =========================
        # GOOGLE CALENDAR EVENT
        # =========================
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
                    "dateTime": data + ":30",  # duração 30 min
                    "timeZone": "Europe/Lisbon"
                }
            }

            service.events().insert(
                calendarId="primary",
                body=event
            ).execute()

        return "✅ Marcação feita com sucesso!"

    date = request.args.get("date", "")

    available_slots = get_available_slots(worker_id, date) if date else SLOTS

    return render_template_string(
        FORM,
        name=name,
        slug=slug,
        slots=available_slots
    )

# =========================
# LOGIN WORKER (GOOGLE)
# =========================
@app.route("/login/<slug>")
def login(slug):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/callback"
    )

    auth_url, state = flow.authorization_url(prompt="consent")

    session["state"] = state
    session["slug"] = slug

    return redirect(auth_url)

# =========================
# CALLBACK GOOGLE
# =========================
@app.route("/callback")
def callback():
    slug = session.get("slug")

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=session["state"],
        redirect_uri="http://localhost:5000/callback"
    )

    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials

    token_json = json.dumps({
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    })

    cursor.execute(
        "UPDATE workers SET token=%s WHERE slug=%s",
        (token_json, slug)
    )
    conn.commit()

    return "Login feito com sucesso!"

# =========================
# DASHBOARD WORKER
# =========================
@app.route("/worker/<slug>")
def worker_dashboard(slug):
    cursor.execute("SELECT id FROM workers WHERE slug=%s", (slug,))
    worker = cursor.fetchone()

    if not worker:
        return "Worker não existe"

    worker_id = worker[0]

    cursor.execute("""
        SELECT client_name, service, date
        FROM bookings
        WHERE worker_id=%s
    """, (worker_id,))

    bookings = cursor.fetchall()

    output = "<h2>Minhas Marcações</h2><br>"

    for b in bookings:
        output += f"<p><b>{b[0]}</b> - {b[1]} - {b[2]}</p>"

    return output

# =========================
# ADMIN - CRIAR WORKER
# =========================
@app.route("/admin/create_worker", methods=["GET", "POST"])
def create_worker():
    if request.method == "GET":
        return """
        <form method="POST">
            Password: <input name="password"><br>
            Nome: <input name="name"><br>
            Slug: <input name="slug"><br>
            <button type="submit">Criar Worker</button>
        </form>
        """

    password = request.form.get("password")

    if password != ADMIN_PASSWORD:
        return "Acesso negado"

    name = request.form["name"]
    slug = request.form["slug"]

    cursor.execute(
        "INSERT INTO workers (name, slug) VALUES (%s, %s)",
        (name, slug)
    )
    conn.commit()

    return f"Worker criado: /{slug}"

# =========================
# ADMIN - DESATIVAR WORKER
# =========================
@app.route("/admin/deactivate", methods=["POST"])
def deactivate_worker():
    password = request.form.get("password")

    if password != ADMIN_PASSWORD:
        return "Acesso negado"

    slug = request.form["slug"]

    cursor.execute(
        "UPDATE workers SET active=0 WHERE slug=%s",
        (slug,)
    )
    conn.commit()

    return "Worker desativado"

# =========================
# RUN APP
# =========================
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
