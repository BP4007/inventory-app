from flask import Flask, render_template, request, redirect, send_file, flash, session, url_for
import sqlite3
import pandas as pd
from io import BytesIO
import os
from datetime import datetime
import uuid

# ---------------- CONFIG ----------------
DB_NAME = r"C:/Users/starb/OneDrive/Documentos/App_Project/Inventory App/PROD/inventory.db"
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# 2 USERS
USERS = {
    os.environ["APP_USER"]: os.environ["APP_PASS"],
    os.environ.get("APP_USER2"): os.environ.get("APP_PASS2")
}

# ---------------- LOGIN DECORATOR ----------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- DATABASE ----------------
def run_query(query, params=(), fetch=True):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def init_db():
    run_query("""
        CREATE TABLE IF NOT EXISTS inventory_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            source_table TEXT,
            product_no TEXT,
            description TEXT,
            quantity INTEGER,
            created_at TEXT
        )
    """, fetch=False)

# ---------------- ROUTES ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username")
        pwd = request.form.get("password")

        if USERS.get(user) == pwd:
            session["logged_in"] = True
            session["user"] = user
            return redirect("/")
        else:
            flash("Invalid login", "warning")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/start_session")
@login_required
def start_session():
    session["session_id"] = str(uuid.uuid4())
    flash("New report started!", "success")
    return redirect("/")

@app.route("/get_products/<table>")
@login_required
def get_products(table):
    data = run_query(f"SELECT * FROM {table}")
    return {"data": data}

@app.route("/save", methods=["POST"])
@login_required
def save():
    session_id = session.get("session_id")
    if not session_id:
        return {"error": "Start a session first"}

    table = request.form.get("table")
    product = request.form.get("product")
    description = request.form.get("description")
    qty = request.form.get("qty")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    run_query("""
        INSERT INTO inventory_reports 
        (session_id, source_table, product_no, description, quantity, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, table, product, description, qty, timestamp), fetch=False)

    return {"status": "success"}

@app.route("/get_entries")
@login_required
def get_entries():
    session_id = session.get("session_id")
    if not session_id:
        return {"entries": []}
    data = run_query(
        "SELECT product_no, description, quantity, created_at "
        "FROM inventory_reports WHERE session_id=? ORDER BY id DESC",
        (session_id,)
    )
    entries = [{"product_no":r[0],"description":r[1],"quantity":r[2],"created_at":r[3]} for r in data]
    return {"entries": entries}

@app.route("/export")
@login_required
def export():
    session_id = session.get("session_id")
    if not session_id:
        flash("No active session!", "warning")
        return redirect("/")

    data = run_query(
        "SELECT product_no, description, quantity, created_at "
        "FROM inventory_reports WHERE session_id=? ORDER BY id",
        (session_id,)
    )
    
    df = pd.DataFrame(data, columns=["Product","Description","Quantity","Timestamp"])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name="report.xlsx", as_attachment=True)

# ---------------- RUN ----------------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)