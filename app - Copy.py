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
    os.environ["APP_USER"]: os.environ["APP_PASS"],
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
            report_name TEXT,
            source TEXT,
            product_no TEXT,
            description TEXT,
            quantity INTEGER,
            comment TEXT,
            is_completed INTEGER DEFAULT 0,
            created_at TEXT
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
        user=request.form.get("username")
        pwd=request.form.get("password")
        if USERS.get(user)==pwd:
            session["logged_in"]=True
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
    report_name = session.get("report_name")
    completed = False
    if sid:
        data = run_query("SELECT MAX(is_completed) FROM inventory_reports WHERE session_id=?", (sid,))
        completed = data[0][0]==1 if data else False
    return render_template("index.html", report_name=report_name, completed=completed)

# ---------- START SESSION ----------
@app.route("/start_session", methods=["GET","POST"])
@login_required
def start_session():
    if request.method=="POST":
        report_name = request.form.get("report_name")
        if not report_name.strip():
            flash("Report name is required", "warning")
            return redirect("/start_session")
        session["session_id"] = str(uuid.uuid4())
        session["report_name"] = report_name.strip()
        flash("New report started!", "success")
        return redirect("/")
    return render_template("start_session.html")

# ---------- COMPLETE REPORT ----------
@app.route("/complete_report", methods=["POST"])
@login_required
def complete_report():
    sid = session.get("session_id")
    if sid:
        run_query("UPDATE inventory_reports SET is_completed=1 WHERE session_id=?", (sid,), fetch=False)
        flash("Report marked as Completed!", "success")
    return redirect("/")

# ---------- REPORT LIST ----------
@app.route("/reports")
@login_required
def reports():
    data = run_query("""
        SELECT session_id, MIN(report_name), MIN(created_at), COUNT(*), MAX(is_completed)
        FROM inventory_reports
        GROUP BY session_id
        ORDER BY MIN(created_at) DESC
    """)
    reports = [
        {
            "session_id": r[0],
            "report_name": r[1],
            "start_time": r[2],
            "count": r[3],
            "status": "Completed" if r[4]==1 else "In Progress"
        }
        for r in data
    ]
    return render_template("reports.html", reports=reports)

# ---------- LOAD OLD REPORT ----------
@app.route("/load_report/<sid>")
@login_required
def load_report(sid):
    session["session_id"] = sid
    data = run_query("SELECT report_name FROM inventory_reports WHERE session_id=? LIMIT 1", (sid,))
    if data:
        session["report_name"] = data[0][0]
    flash("Loaded previous report","info")
    return redirect("/")

# ---------- GET PRODUCTS ----------
@app.route("/get_products/<source>")
@login_required
def get_products(source):
    if source.lower()=="icecream":
        df=load_file(ICECREAM_FILE)
    else:
        df=load_file(CHOCOLATE_FILE)
    return {"data": df.values.tolist()}

# ---------- SAVE ----------
@app.route("/save", methods=["POST"])
@login_required
def save():
    sid = session.get("session_id")
    report_name = session.get("report_name")
    if not sid or not report_name:
        return {"error":"Start a session with a report name first"}
    run_query("""
        INSERT INTO inventory_reports
        (session_id, report_name, source, product_no, description, quantity, comment, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """,(
        sid,
        report_name,
        request.form.get("table"),
        request.form.get("product"),
        request.form.get("description"),
        request.form.get("qty"),
        request.form.get("comment",""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ), fetch=False)
    return {"status":"success"}

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
        {"id":r[0], "product_no":r[1], "description":r[2], "quantity":r[3], "comment":r[4], "created_at":r[5]}
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
    df.to_excel(output,index=False)
    output.seek(0)
    return send_file(output, download_name=f"report_{sid}.xlsx", as_attachment=True)

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))