from flask import Flask, render_template, request, redirect, send_file, flash
import sqlite3
import pandas as pd
from io import BytesIO
import os

DB_NAME = "inventory.db"
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecret")

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            product_no TEXT PRIMARY KEY,
            item_name TEXT,
            quantity INTEGER
        )
    """)
    conn.commit()
    conn.close()

def run_query(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    data = cursor.fetchall()
    conn.close()
    return data

# ---------- Routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        product = request.form.get("product").strip()
        name = request.form.get("name").strip()
        qty = request.form.get("quantity").strip()
        qty = int(qty) if qty else None
        try:
            run_query("INSERT INTO inventory VALUES (?, ?, ?)", (product, name, qty))
            flash("Item added successfully!", "success")
        except:
            flash("Product# already exists!", "warning")
        return redirect("/")

    items = run_query("SELECT * FROM inventory")
    return render_template("index.html", items=items)

@app.route("/delete/<product_no>")
def delete(product_no):
    run_query("DELETE FROM inventory WHERE product_no=?", (product_no,))
    flash("Item deleted!", "success")
    return redirect("/")

@app.route("/edit/<product_no>", methods=["GET", "POST"])
def edit(product_no):
    if request.method == "POST":
        qty = request.form.get("quantity")
        try:
            qty = int(qty)
            run_query("UPDATE inventory SET quantity=? WHERE product_no=?", (qty, product_no))
            flash("Quantity updated!", "success")
        except:
            flash("Invalid number", "warning")
        return redirect("/")

    item = run_query("SELECT * FROM inventory WHERE product_no=?", (product_no,))
    return render_template("edit.html", item=item[0])

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file:
        flash("No file selected", "warning")
        return redirect("/")

    df = pd.read_excel(file)
    existing = set(x[0] for x in run_query("SELECT product_no FROM inventory"))
    new_count = 0
    duplicate_count = 0

    for _, row in df.iterrows():
        product = str(row.iloc[0]).strip()
        name = str(row.iloc[1]).strip()

        if not product or product.lower() == "nan":
            continue

        if product in existing:
            duplicate_count += 1
            continue

        run_query("INSERT INTO inventory VALUES (?, ?, ?)", (product, name, None))
        existing.add(product)
        new_count += 1

    flash(f"Upload Summary: New: {new_count}, Duplicates: {duplicate_count}", "info")
    return redirect("/")

@app.route("/export")
def export():
    data = run_query("SELECT * FROM inventory")
    df = pd.DataFrame(data, columns=["Product#", "Item Name", "Quantity"])

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, download_name="inventory.xlsx", as_attachment=True)

# ---------- Run ----------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)