from flask import Flask, render_template, request, redirect, send_file, flash, session, url_for, jsonify
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
app.secret_key = os.environ.get("SECRET_KEY","dev_secret_key")

USERS = {
    os.environ.get("APP_USER","admin"): os.environ.get("APP_PASS","admin")
}

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

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
            source TEXT,
            product_no TEXT,
            description TEXT,
            quantity INTEGER,
            created_at TEXT
        )
    """, fetch=False)

    # Ensure comment column exists
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(inventory_reports)")
    cols = [c[1] for c in cursor.fetchall()]
    if "comment" not in cols:
        cursor.execute("ALTER TABLE inventory_reports ADD COLUMN comment TEXT")
    conn.commit()
    conn.close()

def load_file(file_path):
    df = pd.read_csv(file_path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df[["product_no","description"]]

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
    return render_template("index.html")

@app.route("/start_session")
@login_required
def start_session():
    session["session_id"] = str(uuid.uuid4())
    flash("New report started!","success")
    return redirect("/")

@app.route("/get_products/<source>")
@login_required
def get_products(source):
    if source.lower()=="icecream":
        df=load_file(ICECREAM_FILE)
    else:
        df=load_file(CHOCOLATE_FILE)
    return {"data": df.values.tolist()}

@app.route("/save", methods=["POST"])
@login_required
def save():
    sid = session.get("session_id")
    if not sid:
        return {"error":"Start a session first"}

    run_query("""
        INSERT INTO inventory_reports
        (session_id, source, product_no, description, quantity, comment, created_at)
        VALUES (?,?,?,?,?,?,?)
    """,(
        sid,
        request.form.get("table"),
        request.form.get("product"),
        request.form.get("description"),
        request.form.get("qty"),
        request.form.get("comment",""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ), fetch=False)

    return {"status":"success"}

@app.route("/get_entries")
@login_required
def get_entries():
    sid = session.get("session_id")
    data = run_query("""
        SELECT id, product_no, description, quantity, comment, created_at
        FROM inventory_reports WHERE session_id=? ORDER BY id DESC
    """,(sid,))
    return {"entries":[
        {"id":r[0],"product_no":r[1],"description":r[2],
         "quantity":r[3],"comment":r[4],"created_at":r[5]}
        for r in data
    ]}

@app.route("/delete_entry", methods=["POST"])
@login_required
def delete_entry():
    run_query("DELETE FROM inventory_reports WHERE id=?",
              (request.form.get("id"),), fetch=False)
    return {"status":"ok"}

@app.route("/export")
@login_required
def export():
    sid = session.get("session_id")
    data = run_query("""
        SELECT product_no, description, quantity, comment, created_at
        FROM inventory_reports WHERE session_id=? ORDER BY id
    """,(sid,))
    df = pd.DataFrame(data, columns=["Product","Description","Qty","Comment","Time"])
    output = BytesIO()
    df.to_excel(output,index=False)
    output.seek(0)
    return send_file(output, download_name="report.xlsx", as_attachment=True)

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))