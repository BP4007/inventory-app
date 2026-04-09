from flask import Flask, render_template, request, redirect, send_file, flash, session, url_for
import sqlite3
import pandas as pd
from io import BytesIO
import os
from datetime import datetime
import uuid

DB_NAME = "inventory.db"
ICECREAM_FILE = "Ice Cream Order_Sheet.csv"
CHOCOLATE_FILE = "Case Chocolates Order_Sheet.csv"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

USERS = {
    os.environ.get("APP_USER"): os.environ.get("APP_PASS"),
    os.environ.get("APP_USER2"): os.environ.get("APP_PASS2")
}

# ---------- AUTH ----------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ---------- DB ----------
def run_query(query, params=(), fetch=True):
    conn = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
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
            source TEXT,
            product_no TEXT,
            description TEXT,
            quantity INTEGER,
            comment TEXT,
            created_at TEXT,
            is_completed INTEGER DEFAULT 0
        )
    """, fetch=False)

# ---------- FILE LOAD ----------
def load_file(file_path):
    df = pd.read_csv(file_path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df[["product_no","description"]]

# ---------- ROUTES ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        user = request.form.get("username")
        pwd = request.form.get("password")
        if USERS.get(user) == pwd:
            session["logged_in"] = True
            return redirect("/")
        flash("Invalid login","warning")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
@login_required
def index():
    sid = session.get("session_id")
    completed = 0
    if sid:
        res = run_query("SELECT MAX(is_completed) FROM inventory_reports WHERE session_id=?", (sid,))
        completed = res[0][0] or 0
    return render_template("index.html", report_completed=completed)

@app.route("/start_session")
@login_required
def start_session():
    session["session_id"] = str(uuid.uuid4())
    flash("New report started!", "success")
    return redirect("/")

# ---------- REPORT LIST ----------
@app.route("/reports")
@login_required
def reports():
    data = run_query("""
        SELECT session_id, MIN(created_at) as start_time, COUNT(*), MAX(is_completed)
        FROM inventory_reports
        GROUP BY session_id
        ORDER BY start_time DESC
    """)
    reports = [
        {
            "session_id": r[0],
            "start_time": r[1],
            "count": r[2],
            "completed": r[3]
        }
        for r in data
    ]
    return render_template("reports.html", reports=reports)

@app.route("/load_report/<sid>")
@login_required
def load_report(sid):
    session["session_id"] = sid
    flash("Loaded previous report", "info")
    return redirect("/")

# ---------- GET PRODUCTS ----------
@app.route("/get_products/<source>")
@login_required
def get_products(source):
    if source.lower() == "icecream":
        df = load_file(ICECREAM_FILE)
    elif source.lower() == "case_chocolate":
        df = load_file(CHOCOLATE_FILE)
    else:
        df = pd.DataFrame(columns=["product_no","description"])
    return {"data": df.values.tolist()}

# ---------- SAVE ----------
@app.route("/save", methods=["POST"])
@login_required
def save():
    sid = session.get("session_id")
    if not sid:
        return {"error":"Start a session first"}
    source = request.form.get("table")
    product_no = request.form.get("product")
    description = request.form.get("description")
    qty = request.form.get("qty")
    comment = request.form.get("comment","")
    try:
        run_query("""
            INSERT INTO inventory_reports
            (session_id, source, product_no, description, quantity, comment, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            sid, source, product_no, description, qty, comment,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ), fetch=False)
        return {"status":"success"}
    except sqlite3.OperationalError as e:
        return {"error": str(e)}

# ---------- GET ENTRIES ----------
@app.route("/get_entries")
@login_required
def get_entries():
    sid = session.get("session_id")
    data = run_query("""
        SELECT id, product_no, description, quantity, comment, created_at
        FROM inventory_reports
        WHERE session_id=?
        ORDER BY id DESC
    """,(sid,))
    return {"entries":[
        {"id":r[0], "product_no":r[1], "description":r[2],
         "quantity":r[3], "comment":r[4], "created_at":r[5]}
        for r in data
    ]}

# ---------- UPDATE ----------
@app.route("/update_entry", methods=["POST"])
@login_required
def update_entry():
    entry_id = request.form.get("id")
    qty = request.form.get("qty")
    comment = request.form.get("comment","")
    run_query("UPDATE inventory_reports SET quantity=?, comment=? WHERE id=?", (qty, comment, entry_id), fetch=False)
    return {"status":"updated"}

# ---------- DELETE ----------
@app.route("/delete_entry", methods=["POST"])
@login_required
def delete_entry():
    entry_id = request.form.get("id")
    run_query("DELETE FROM inventory_reports WHERE id=?", (entry_id,), fetch=False)
    return {"status":"deleted"}

# ---------- MARK COMPLETED ----------
@app.route("/complete_report", methods=["POST"])
@login_required
def complete_report():
    sid = session.get("session_id")
    run_query("UPDATE inventory_reports SET is_completed=1 WHERE session_id=?", (sid,), fetch=False)
    return {"status":"completed"}

# ---------- EXPORT ----------
@app.route("/export")
@login_required
def export():
    sid = request.args.get("sid") or session.get("session_id")
    data = run_query("""
        SELECT product_no, description, quantity, comment, created_at
        FROM inventory_reports
        WHERE session_id=?
        ORDER BY id
    """,(sid,))
    df = pd.DataFrame(data, columns=["Product","Description","Qty","Comment","Time"])
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    return send_file(output, download_name=f"report_{sid}.xlsx", as_attachment=True)

# ---------- RUN ----------
if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))