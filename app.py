from flask import Flask, request, render_template, jsonify
import psycopg2
import os
from datetime import datetime

# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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
# SLOTS FUNCTION
# =========================
def get_available_slots(worker_id, date):
    if not date:
        return SLOTS

    cur = db_query("""
        SELECT date FROM bookings
        WHERE worker_id=%s AND date::date = %s::date
    """, (worker_id, date))

    if not cur:
        return SLOTS

    rows = cur.fetchall()

    booked = [row[0].strftime("%H:%M") for row in rows if row[0]]

    return [slot for slot in SLOTS if slot not in booked]


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

    date = request.values.get("date", "")

    # =========================
    # POST BOOKING
    # =========================
    if request.method == "POST":

        nome = request.form["nome"]
        servico = request.form["servico"]
        time = request.form["time"]

        if not date or not time:
            return jsonify({"success": False, "error": "Data inválida"})

        try:
            data = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        except:
            return jsonify({"success": False, "error": "Formato inválido"})

        cur = db_query(
            "SELECT 1 FROM bookings WHERE worker_id=%s AND date=%s LIMIT 1",
            (worker_id, data)
        )

        if cur and cur.fetchone():
            return jsonify({"success": False, "error": "Horário já ocupado"})

        db_query("""
            INSERT INTO bookings (worker_id, client_name, service, date)
            VALUES (%s, %s, %s, %s)
        """, (worker_id, nome, servico, data))

        return jsonify({
            "success": True,
            "slots": get_available_slots(worker_id, date)
        })

    # =========================
    # GET
    # =========================
    available_slots = get_available_slots(worker_id, date) if date else SLOTS

    return render_template(
        "worker.html",
        name=name,
        slots=available_slots,
        selected_date=date
    )


# =========================
# API SLOTS
# =========================
@app.route("/api/slots/<slug>")
def get_slots_api(slug):
    date = request.args.get("date")

    cur = db_query("SELECT id FROM workers WHERE slug=%s", (slug,))
    worker = cur.fetchone() if cur else None

    if not worker:
        return jsonify({"slots": []})

    worker_id = worker[0]

    return jsonify({
        "slots": get_available_slots(worker_id, date) if date else SLOTS
    })


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
    app.run(host="0.0.0.0", port=port, debug=True)
