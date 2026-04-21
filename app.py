from flask import Flask, request, render_template, jsonify, session, redirect, render_template_string
import psycopg2
import os
from datetime import datetime

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

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
# DB FUNCTION
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
# TABLES
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
    date TIMESTAMP
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
# SLOT LOGIC (FIXED)
# =========================
def get_available_slots(worker_id, date):
    if not date:
        return SLOTS

    try:
        cur = db_query("""
            SELECT date FROM bookings
            WHERE worker_id=%s AND date::date = %s::date
        """, (worker_id, date))

        rows = cur.fetchall() if cur else []

        booked = []
        for row in rows:
            if row[0]:
                booked.append(row[0].strftime("%H:%M"))

        return [slot for slot in SLOTS if slot not in booked]

    except Exception as e:
        print("SLOTS ERROR:", e)
        return SLOTS


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
# WORKER PUBLIC PAGE
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

    # ✅ FIX: date sempre segura
    date = request.values.get("date") or ""

    # =========================
    # POST BOOKING
    # =========================
    if request.method == "POST":

        nome = request.form.get("nome")
        servico = request.form.get("servico")
        time = request.form.get("time")

        if not date or not time:
            return jsonify({"success": False, "error": "Data inválida"})

        try:
            data = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except:
            return jsonify({"success": False, "error": "Formato inválido"})

        cur = db_query(
            "SELECT 1 FROM bookings WHERE worker_id=%s AND date=%s",
            (worker_id, data)
        )

        if cur and cur.fetchone():
            return jsonify({"success": False, "error": "Horário ocupado"})

        db_query("""
            INSERT INTO bookings (worker_id, client_name, service, date)
            VALUES (%s, %s, %s, %s)
        """, (worker_id, nome, servico, data))

        return jsonify({"success": True})


    # =========================
    # GET
    # =========================
    slots = get_available_slots(worker_id, date) if date else SLOTS

    return render_template(
        "worker.html",
        name=name,
        slots=slots,
        selected_date=date
    )


# =========================
# API SLOTS
# =========================
@app.route("/api/slots/<slug>")
def api_slots(slug):

    date = request.args.get("date") or ""

    cur = db_query("SELECT id FROM workers WHERE slug=%s", (slug,))
    worker = cur.fetchone() if cur else None

    if not worker:
        return jsonify({"slots": []})

    worker_id = worker[0]

    slots = get_available_slots(worker_id, date) if date else SLOTS

    return jsonify({"slots": slots})


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
            Token: <input name="token"><br>
            Profissão: <input name="profession"><br>
            <button type="submit">Criar</button>
        </form>
        """

    if request.form.get("password") != ADMIN_PASSWORD:
        return "Acesso negado"

    db_query("""
        INSERT INTO workers (name, slug, profession, token)
        VALUES (%s, %s, %s, %s)
    """, (
        request.form["name"],
        request.form["slug"],
        request.form.get("profession", "Outros"),
        request.form["token"]
    ))

    return "Worker criado"


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
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)), debug=True)
