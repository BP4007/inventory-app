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
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        data = cursor.fetchall() if fetch else None
        conn.commit()
    except sqlite3.OperationalError as e:
        print("DB error:", e)
        data = None
    finally:
        conn.close()
    return data

def init_db():
    # Create table if it doesn't exist
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
            report_name TEXT
        )
    """, fetch=False)
    
    # Add "status" column if it doesn't exist
    columns = run_query("PRAGMA table_info(inventory_reports)")
    column_names = [col[1] for col in columns] if columns else []
    if "status" not in column_names:
        run_query("ALTER TABLE inventory_reports ADD COLUMN status TEXT", fetch=False)

# ---------- FILE LOAD ----------
def load_file(file_path):
    df = pd.read_csv(file_path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df[["product_no", "description"]]

# ---------- ROUTES ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method=="POST":
        user = request.form.get("username")
        pwd = request.form.get("password")
        if USERS.get(user) == pwd:
            session["logged_in"] = True
            return redirect("/")
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

# ---------- START SESSION ----------
@app.route("/start_session", methods=["GET", "POST"])
@login_required
def start_session():
    if request.method == "POST":
        report_name = request.form.get("report_name")
        if not report_name:
            flash("Please enter a report name", "warning")
            return redirect("/start_session")
        session["session_id"] = str(uuid.uuid4())
        session["report_name"] = report_name
        # Save a dummy entry to register report name and status
        run_query("""INSERT INTO inventory_reports (session_id, report_name, status, created_at) 
                     VALUES (?, ?, ?, ?)""",
                  (session["session_id"], report_name, "In Progress", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                  fetch=False)
        flash("New report started!", "success")
        return redirect("/")
    return render_template("start_session.html")

# ---------- REPORT LIST ----------
@app.route("/reports")
@login_required
def reports():
    data = run_query("""
        SELECT session_id,
               MIN(created_at) as start_time,
               COUNT(*) as entries,
               MAX(report_name) as report_name,
               MAX(status) as status
        FROM inventory_reports
        GROUP BY session_id
        ORDER BY start_time DESC
    """)
    reports = [{"session_id": r[0], "start_time": r[1], "count": r[2], "report_name": r[3], "status": r[4]} for r in data]
    return render_template("reports.html", reports=reports)

# ---------- LOAD OLD REPORT ----------
@app.route("/load_report/<sid>")
@login_required
def load_report(sid):
    session["session_id"] = sid
    report = run_query("SELECT report_name FROM inventory_reports WHERE session_id=? LIMIT 1", (sid,))
    if report:
        session["report_name"] = report[0][0]
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
        df = pd.DataFrame(columns=["product_no", "description"])
    return {"data": df.values.tolist()}

# ---------- SAVE ----------
@app.route("/save", methods=["POST"])
@login_required
def save():
    sid = session.get("session_id")
    report_name = session.get("report_name")
    if not sid or not report_name:
        return {"error": "Start a new report first"}

    run_query("""INSERT INTO inventory_reports 
                 (session_id, source, product_no, description, quantity, comment, created_at, report_name, status)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (
                  sid,
                  request.form.get("table"),
                  request.form.get("product"),
                  request.form.get("description"),
                  request.form.get("qty"),
                  request.form.get("comment",""),
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  report_name,
                  "In Progress"
              ),
              fetch=False)
    return {"status": "success"}

# ---------- GET ENTRIES ----------
@app.route("/get_entries")
@login_required
def get_entries():
    sid = session.get("session_id")
    data = run_query("""SELECT id, product_no, description, quantity, comment, created_at
                        FROM inventory_reports WHERE session_id=? ORDER BY id DESC""",(sid,))
    return {"entries":[{"id":r[0], "product_no":r[1], "description":r[2], "quantity":r[3], "comment":r[4], "created_at":r[5]} for r in data]}

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

# ---------- EXPORT ----------
@app.route("/export")
@login_required
def export():
    sid = request.args.get("sid") or session.get("session_id")
    data = run_query("""SELECT product_no, description, quantity, comment, created_at
                        FROM inventory_reports WHERE session_id=? ORDER BY id""",(sid,))
    df = pd.DataFrame(data, columns=["Product","Description","Qty","Comment","Time"])
    output = BytesIO()
    df.to_excel(output,index=False)
    output.seek(0)
    return send_file(output, download_name=f"report_{sid}.xlsx", as_attachment=True)
    
# ---------- COMPLETE REPORT ----------
@app.route("/complete_report", methods=["POST"])
@login_required
def complete_report():
    sid = session.get("session_id")
    if not sid:
        return {"error": "No active report"}
    run_query("UPDATE inventory_reports SET status='Complete' WHERE session_id=?", (sid,), fetch=False)
    flash("Report marked as Complete", "success")
    # Clear session to force new report
    session.pop("session_id", None)
    session.pop("report_name", None)
    return {"status":"success"}

# ---------- RUN ----------
if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))