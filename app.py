from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
import sqlite3, os
import re
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.units import cm
import io

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
DB = "eco_farms.db"

# ─── AUTH HELPERS ───────────────────────────────────────────────────────────
@app.context_processor
def inject_user():
    return {
        "current_user": session.get("user"),
        "current_date": datetime.now().strftime("%d %b %Y")
    }

def get_current_user_id():
    return session.get("user_id")

@app.before_request
def require_login():
    if request.endpoint in ("login", "logout", "register", "static"):
        return
    if not session.get("user"):
        return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            session["user_id"] = user["id"]
            flash(f"Welcome back, {username}.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()

        if not username or not password or not password_confirm:
            flash("Username and password are required.", "error")
            return render_template("register.html")
        if password != password_confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")
        if email and not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")

        conn = get_db()
        existing = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            conn.close()
            flash("Username is already taken.", "error")
            return render_template("register.html")
        conn.execute("INSERT INTO users (username,password_hash,full_name,email,created_at) VALUES (?,?,?,?,?)",
                     (username, generate_password_hash(password), full_name, email, now_str()))
        conn.commit(); conn.close()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# ─── DB SETUP ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_column_exists(conn, table_name, column_name, column_type):
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in existing:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS farmers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        address TEXT,
        id_number TEXT,
        join_date TEXT,
        status TEXT DEFAULT 'Active',
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        email TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farmer_id INTEGER,
        farm_name TEXT,
        location TEXT,
        area_acres REAL,
        crop_type TEXT,
        season TEXT,
        start_date TEXT,
        status TEXT DEFAULT 'Active',
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farmer_id) REFERENCES farmers(id)
    );
    CREATE TABLE IF NOT EXISTS seeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farm_id INTEGER,
        seed_name TEXT,
        variety TEXT,
        quantity_kg REAL,
        sow_date TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farm_id) REFERENCES farms(id)
    );
    CREATE TABLE IF NOT EXISTS supplies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farm_id INTEGER,
        supply_name TEXT,
        supply_type TEXT,
        quantity REAL,
        unit TEXT,
        rate_per_unit REAL DEFAULT 0,
        total_cost REAL DEFAULT 0,
        cost_deducted INTEGER DEFAULT 0,
        supply_date TEXT,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farm_id) REFERENCES farms(id)
    );
    CREATE TABLE IF NOT EXISTS daily_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farm_id INTEGER,
        update_date TEXT,
        update_time TEXT,
        growth_stage TEXT,
        weather TEXT,
        description TEXT,
        issue_reported TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farm_id) REFERENCES farms(id)
    );
    CREATE TABLE IF NOT EXISTS harvests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farm_id INTEGER,
        harvest_date TEXT,
        total_output_kg REAL,
        quality_grade TEXT,
        rate_per_kg REAL,
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farm_id) REFERENCES farms(id)
    );
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        farmer_id INTEGER,
        farm_id INTEGER,
        amount REAL,
        payment_type TEXT,
        payment_date TEXT,
        payment_time TEXT,
        reference TEXT,
        status TEXT DEFAULT 'Pending',
        notes TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(farmer_id) REFERENCES farmers(id),
        FOREIGN KEY(farm_id) REFERENCES farms(id)
);
    """)
    conn.commit()
    ensure_column_exists(conn, "supplies", "rate_per_unit", "REAL DEFAULT 0")
    ensure_column_exists(conn, "supplies", "total_cost", "REAL DEFAULT 0")
    ensure_column_exists(conn, "supplies", "cost_deducted", "INTEGER DEFAULT 0")

    # Add user ownership columns for multi-user isolation.
    ensure_column_exists(conn, "farmers", "user_id", "INTEGER")
    ensure_column_exists(conn, "farms", "user_id", "INTEGER")
    ensure_column_exists(conn, "seeds", "user_id", "INTEGER")
    ensure_column_exists(conn, "supplies", "user_id", "INTEGER")
    ensure_column_exists(conn, "daily_updates", "user_id", "INTEGER")
    ensure_column_exists(conn, "harvests", "user_id", "INTEGER")
    ensure_column_exists(conn, "payments", "user_id", "INTEGER")
    conn.commit()
    # Note: Remove or randomize default admin creation for production
    # admin = conn.execute("SELECT id FROM users WHERE username=?", ("admin",)).fetchone()
    # if not admin:
    #     conn.execute("INSERT INTO users (username,password_hash,full_name,email,created_at) VALUES (?,?,?,?,?)",
    #                  ("admin", generate_password_hash("admin123"), "Administrator", "admin@ecofarms.local", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    #     conn.commit()
    conn.close()

init_db()
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def today_str():
    return datetime.now().strftime("%Y-%m-%d")

def is_valid_email(email):
    if not email:
        return True
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None

def is_valid_phone(phone):
    if not phone:
        return True
    digits = re.sub(r"\D", "", phone)
    return 7 <= len(digits) <= 15

def is_valid_id_number(id_number):
    if not id_number:
        return False
    return re.match(r"^[A-Za-z0-9\- ]{5,25}$", id_number) is not None

# ─── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    user_id = get_current_user_id()
    conn = get_db()
    stats = {
        "farmers": conn.execute("SELECT COUNT(*) FROM farmers WHERE status='Active' AND user_id=?", (user_id,)).fetchone()[0],
        "farms":   conn.execute("SELECT COUNT(*) FROM farms WHERE status='Active' AND user_id=?", (user_id,)).fetchone()[0],
        "payments_pending": conn.execute("SELECT COUNT(*) FROM payments WHERE status='Pending' AND user_id=?", (user_id,)).fetchone()[0],
        "total_paid": conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='Paid' AND user_id=?", (user_id,)).fetchone()[0],
    }
    recent_updates = conn.execute("""
        SELECT du.*, f.farm_name, fa.name as farmer_name
        FROM daily_updates du
        JOIN farms f ON du.farm_id = f.id
        JOIN farmers fa ON f.farmer_id = fa.id
        WHERE du.user_id=?
        ORDER BY du.created_at DESC LIMIT 5
    """, (user_id,)).fetchall()
    recent_payments = conn.execute("""
        SELECT p.*, fa.name as farmer_name, f.farm_name
        FROM payments p
        JOIN farmers fa ON p.farmer_id = fa.id
        JOIN farms f ON p.farm_id = f.id
        WHERE p.user_id=?
        ORDER BY p.created_at DESC LIMIT 5
    """, (user_id,)).fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, recent_updates=recent_updates, recent_payments=recent_payments)

# ─── FARMERS ─────────────────────────────────────────────────────────────────
@app.route("/farmers")
def farmers():
    user_id = get_current_user_id()
    conn = get_db()
    rows = conn.execute("SELECT * FROM farmers WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return render_template("farmers/list.html", farmers=rows)

@app.route("/farmers/add", methods=["GET","POST"])
def add_farmer():
    farmer_data = {
        "name": "",
        "phone": "",
        "email": "",
        "address": "",
        "id_number": "",
        "status": "Active"
    }
    if request.method == "POST":
        farmer_data = {
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "address": request.form.get("address", "").strip(),
            "id_number": request.form.get("id_number", "").strip(),
            "status": "Active"
        }
        if not farmer_data["name"]:
            flash("Name is required.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_email(farmer_data["email"]):
            flash("Please enter a valid email address.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_phone(farmer_data["phone"]):
            flash("Please enter a valid phone number.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_id_number(farmer_data["id_number"]):
            flash("Please enter a valid ID number (5-25 letters, numbers, spaces, or dashes).", "error")
            return render_template("farmers/form.html", farmer=farmer_data)

        conn = get_db()
        conn.execute("INSERT INTO farmers (user_id,name,phone,email,address,id_number,join_date,status) VALUES (?,?,?,?,?,?,?,?)",
            (get_current_user_id(), farmer_data["name"], farmer_data["phone"], farmer_data["email"],
             farmer_data["address"], farmer_data["id_number"],
             request.form.get("join_date") or today_str(), "Active"))
        conn.commit(); conn.close()
        flash("Farmer added successfully!", "success")
        return redirect(url_for("farmers"))
    return render_template("farmers/form.html", farmer=farmer_data)

@app.route("/farmers/<int:id>")
def farmer_detail(id):
    user_id = get_current_user_id()
    conn = get_db()
    farmer = conn.execute("SELECT * FROM farmers WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    if not farmer:
        conn.close()
        flash("Farmer not found or access denied.", "error")
        return redirect(url_for("farmers"))
    farms  = conn.execute("SELECT * FROM farms WHERE farmer_id=? AND user_id=?", (id, user_id)).fetchall()
    payments = conn.execute("""SELECT p.*, f.farm_name FROM payments p
        JOIN farms f ON p.farm_id=f.id WHERE p.farmer_id=? AND p.user_id=? ORDER BY p.payment_date DESC""", (id, user_id)).fetchall()
    conn.close()
    return render_template("farmers/detail.html", farmer=farmer, farms=farms, payments=payments)

@app.route("/farmers/<int:id>/edit", methods=["GET","POST"])
def edit_farmer(id):
    user_id = get_current_user_id()
    conn = get_db()
    farmer = conn.execute("SELECT * FROM farmers WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    if not farmer:
        conn.close()
        flash("Farmer not found or access denied.", "error")
        return redirect(url_for("farmers"))
    if request.method == "POST":
        farmer_data = {
            "id": id,
            "name": request.form.get("name", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "email": request.form.get("email", "").strip(),
            "address": request.form.get("address", "").strip(),
            "id_number": request.form.get("id_number", "").strip(),
            "status": request.form.get("status", "Active")
        }
        if not farmer_data["name"]:
            flash("Name is required.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_email(farmer_data["email"]):
            flash("Please enter a valid email address.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_phone(farmer_data["phone"]):
            flash("Please enter a valid phone number.", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        if not is_valid_id_number(farmer_data["id_number"]):
            flash("Please enter a valid ID number (5-25 letters, numbers, spaces, or dashes).", "error")
            return render_template("farmers/form.html", farmer=farmer_data)
        conn.execute("UPDATE farmers SET name=?,phone=?,email=?,address=?,id_number=?,status=? WHERE id=? AND user_id=?",
            (farmer_data["name"], farmer_data["phone"], farmer_data["email"],
             farmer_data["address"], farmer_data["id_number"], farmer_data["status"], id, user_id))
        conn.commit(); conn.close()
        flash("Farmer updated!", "success")
        return redirect(url_for("farmer_detail", id=id))
    conn.close()
    return render_template("farmers/form.html", farmer=farmer)

@app.route("/farmers/<int:id>/delete", methods=["POST"])
def delete_farmer(id):
    user_id = get_current_user_id()
    conn = get_db()
    farmer = conn.execute("SELECT id FROM farmers WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    if not farmer:
        conn.close()
        flash("Farmer not found or access denied.", "error")
        return redirect(url_for("farmers"))
    farm_rows = conn.execute("SELECT id FROM farms WHERE farmer_id=? AND user_id=?", (id, user_id)).fetchall()
    farm_ids = [row[0] for row in farm_rows]
    if farm_ids:
        placeholders = ",".join(["?"] * len(farm_ids))
        conn.execute(f"DELETE FROM seeds WHERE farm_id IN ({placeholders}) AND user_id=?", farm_ids + [user_id])
        conn.execute(f"DELETE FROM supplies WHERE farm_id IN ({placeholders}) AND user_id=?", farm_ids + [user_id])
        conn.execute(f"DELETE FROM daily_updates WHERE farm_id IN ({placeholders}) AND user_id=?", farm_ids + [user_id])
        conn.execute(f"DELETE FROM harvests WHERE farm_id IN ({placeholders}) AND user_id=?", farm_ids + [user_id])
        conn.execute(f"DELETE FROM payments WHERE farm_id IN ({placeholders}) AND user_id=?", farm_ids + [user_id])
    conn.execute("DELETE FROM payments WHERE farmer_id=? AND user_id=?", (id, user_id))
    conn.execute("DELETE FROM farms WHERE farmer_id=? AND user_id=?", (id, user_id))
    conn.execute("DELETE FROM farmers WHERE id=? AND user_id=?", (id, user_id))
    conn.commit(); conn.close()
    flash("Farmer deleted successfully.", "success")
    return redirect(url_for("farmers"))

# ─── FARMS ────────────────────────────────────────────────────────────────────
@app.route("/farms")
def farms():
    user_id = get_current_user_id()
    conn = get_db()
    rows = conn.execute("""SELECT f.*, fa.name as farmer_name
        FROM farms f JOIN farmers fa ON f.farmer_id=fa.id
        WHERE f.user_id=? ORDER BY f.id DESC""", (user_id,)).fetchall()
    conn.close()
    return render_template("farms/list.html", farms=rows)

@app.route("/farms/add", methods=["GET","POST"])
def add_farm():
    user_id = get_current_user_id()
    conn = get_db()
    farmers_list = conn.execute("SELECT id,name FROM farmers WHERE status='Active' AND user_id=?", (user_id,)).fetchall()
    if request.method == "POST":
        conn.execute("INSERT INTO farms (user_id,farmer_id,farm_name,location,area_acres,crop_type,season,start_date,status) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, request.form["farmer_id"], request.form["farm_name"], request.form["location"],
             request.form["area_acres"], request.form["crop_type"], request.form["season"],
             request.form.get("start_date") or today_str(), "Active"))
        conn.commit(); conn.close()
        flash("Farm added!", "success")
        return redirect(url_for("farms"))
    conn.close()
    return render_template("farms/form.html", farm=None, farmers_list=farmers_list)

@app.route("/farms/<int:id>")
def farm_detail(id):
    user_id = get_current_user_id()
    conn = get_db()
    farm   = conn.execute("SELECT f.*,fa.name as farmer_name FROM farms f JOIN farmers fa ON f.farmer_id=fa.id WHERE f.id=? AND f.user_id=?", (id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    seeds  = conn.execute("SELECT * FROM seeds WHERE farm_id=? AND user_id=? ORDER BY sow_date DESC", (id, user_id)).fetchall()
    supplies = conn.execute("SELECT * FROM supplies WHERE farm_id=? AND user_id=? ORDER BY supply_date DESC", (id, user_id)).fetchall()
    updates  = conn.execute("SELECT * FROM daily_updates WHERE farm_id=? AND user_id=? ORDER BY update_date DESC, update_time DESC", (id, user_id)).fetchall()
    harvests = conn.execute("SELECT * FROM harvests WHERE farm_id=? AND user_id=? ORDER BY harvest_date DESC", (id, user_id)).fetchall()
    payments = conn.execute("SELECT * FROM payments WHERE farm_id=? AND user_id=? ORDER BY payment_date DESC", (id, user_id)).fetchall()
    conn.close()
    return render_template("farms/detail.html", farm=farm, seeds=seeds, supplies=supplies,
                           updates=updates, harvests=harvests, payments=payments)

@app.route("/farms/<int:id>/edit", methods=["GET","POST"])
def edit_farm(id):
    user_id = get_current_user_id()
    conn = get_db()
    farm = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (id, user_id)).fetchone()
    farmers_list = conn.execute("SELECT id,name FROM farmers WHERE status='Active' AND user_id=?", (user_id,)).fetchall()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    if request.method == "POST":
        conn.execute("UPDATE farms SET farm_name=?,location=?,area_acres=?,crop_type=?,season=?,status=? WHERE id=? AND user_id=?",
            (request.form["farm_name"], request.form["location"], request.form["area_acres"],
             request.form["crop_type"], request.form["season"], request.form["status"], id, user_id))
        conn.commit(); conn.close()
        flash("Farm updated!", "success")
        return redirect(url_for("farm_detail", id=id))
    conn.close()
    return render_template("farms/form.html", farm=farm, farmers_list=farmers_list)

# ─── SEEDS ───────────────────────────────────────────────────────────────────
@app.route("/farms/<int:farm_id>/seeds/add", methods=["GET","POST"])
def add_seed(farm_id):
    user_id = get_current_user_id()
    conn = get_db()
    farm = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (farm_id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    if request.method == "POST":
        conn.execute("INSERT INTO seeds (user_id,farm_id,seed_name,variety,quantity_kg,sow_date,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, farm_id, request.form["seed_name"], request.form["variety"],
             request.form["quantity_kg"], request.form["sow_date"], request.form["notes"], now_str()))
        conn.commit(); conn.close()
        flash("Seed record added!", "success")
        return redirect(url_for("farm_detail", id=farm_id))
    conn.close()
    return render_template("farms/seed_form.html", farm=farm)

# ─── SUPPLIES ─────────────────────────────────────────────────────────────────
@app.route("/supplies")
def supplies():
    user_id = get_current_user_id()
    conn = get_db()
    rows = conn.execute("""SELECT s.*, f.farm_name, fa.id as farmer_id, fa.name as farmer_name
        FROM supplies s JOIN farms f ON s.farm_id=f.id JOIN farmers fa ON f.farmer_id=fa.id
        WHERE s.user_id=? ORDER BY s.supply_date DESC""", (user_id,)).fetchall()
    conn.close()
    return render_template("supplies/list.html", supplies=rows)

@app.route("/farms/<int:farm_id>/supplies/add", methods=["GET","POST"])
def add_supply(farm_id):
    user_id = get_current_user_id()
    conn = get_db()
    farm = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (farm_id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    if request.method == "POST":
        supply_date = request.form.get("supply_date")
        if not supply_date or not parse_date(supply_date):
            flash("Please enter a valid supply date.", "error")
            conn.close()
            return render_template("supplies/form.html", farm=farm)
        try:
            quantity = float(request.form.get("quantity") or 0)
            rate_per_unit = float(request.form.get("rate_per_unit") or 0)
        except (ValueError, TypeError):
            flash("Please enter valid quantity and rate values.", "error")
            conn.close()
            return render_template("supplies/form.html", farm=farm)
        total_cost = quantity * rate_per_unit
        conn.execute("INSERT INTO supplies (user_id,farm_id,supply_name,supply_type,quantity,unit,rate_per_unit,total_cost,supply_date,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, farm_id, request.form["supply_name"], request.form["supply_type"],
             quantity, request.form["unit"], rate_per_unit, total_cost,
             supply_date, request.form["notes"], now_str()))
        conn.commit(); conn.close()
        flash("Supply recorded!", "success")
        return redirect(url_for("farm_detail", id=farm_id))
    conn.close()
    return render_template("supplies/form.html", farm=farm)

# ─── DAILY UPDATES ────────────────────────────────────────────────────────────
@app.route("/updates")
def updates():
    user_id = get_current_user_id()
    conn = get_db()
    rows = conn.execute("""SELECT du.*, f.farm_name, fa.name as farmer_name
        FROM daily_updates du JOIN farms f ON du.farm_id=f.id JOIN farmers fa ON f.farmer_id=fa.id
        WHERE du.user_id=?
        ORDER BY du.update_date DESC, du.update_time DESC""", (user_id,)).fetchall()
    conn.close()
    return render_template("updates/list.html", updates=rows)

@app.route("/farms/<int:farm_id>/updates/add", methods=["GET","POST"])
def add_update(farm_id):
    user_id = get_current_user_id()
    conn = get_db()
    farm = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (farm_id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    if request.method == "POST":
        now = datetime.now()
        conn.execute("INSERT INTO daily_updates (user_id,farm_id,update_date,update_time,growth_stage,weather,description,issue_reported,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, farm_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"),
             request.form["growth_stage"], request.form["weather"],
             request.form["description"], request.form["issue_reported"], now_str()))
        conn.commit(); conn.close()
        flash("Daily update logged!", "success")
        return redirect(url_for("farm_detail", id=farm_id))
    conn.close()
    return render_template("updates/form.html", farm=farm)

# ─── HARVESTS ─────────────────────────────────────────────────────────────────
def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None

@app.route("/farms/<int:farm_id>/harvest/add", methods=["GET","POST"])
def add_harvest(farm_id):
    user_id = get_current_user_id()
    conn = get_db()
    farm = conn.execute("SELECT * FROM farms WHERE id=? AND user_id=?", (farm_id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    if request.method == "POST":
        harvest_date = parse_date(request.form["harvest_date"])
        if not harvest_date:
            flash("Please enter a valid harvest date.", "error")
            conn.close()
            return render_template("farms/harvest_form.html", farm=farm)
        seed_rows = conn.execute("SELECT sow_date FROM seeds WHERE farm_id=? AND user_id=?", (farm_id, user_id)).fetchall()
        valid_seed = False
        for row in seed_rows:
            sow_date = parse_date(row["sow_date"])
            if sow_date and sow_date <= harvest_date:
                valid_seed = True
                break
        if not valid_seed:
            conn.close()
            flash("A harvest can only be recorded after seeds have been sown.", "error")
            return render_template("farms/harvest_form.html", farm=farm)
        try:
            output = float(request.form["total_output_kg"])
            rate = float(request.form["rate_per_kg"])
        except (ValueError, TypeError):
            flash("Please enter valid harvest output and rate values.", "error")
            conn.close()
            return render_template("farms/harvest_form.html", farm=farm)
        gross_amount = output * rate
        supply_rows = conn.execute("SELECT id, total_cost FROM supplies WHERE farm_id=? AND user_id=? AND cost_deducted=0 AND supply_date IS NOT NULL AND supply_date <> '' AND supply_date<=?", (farm_id, user_id, harvest_date.strftime("%Y-%m-%d"))).fetchall()
        supply_cost = sum(row["total_cost"] or 0 for row in supply_rows)
        for row in supply_rows:
            conn.execute("UPDATE supplies SET cost_deducted=1 WHERE id=? AND user_id=?", (row["id"], user_id))
        net_amount = gross_amount - supply_cost
        conn.execute("INSERT INTO harvests (user_id,farm_id,harvest_date,total_output_kg,quality_grade,rate_per_kg,notes,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, farm_id, request.form["harvest_date"], output,
             request.form["quality_grade"], rate, request.form["notes"], now_str()))
        farmer_id = farm["farmer_id"]
        conn.execute("INSERT INTO payments (user_id,farmer_id,farm_id,amount,payment_type,payment_date,payment_time,reference,status,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, farmer_id, farm_id, net_amount, "Harvest Payment",
             request.form["harvest_date"], datetime.now().strftime("%H:%M:%S"),
             f"HARVEST-{farm_id}-{datetime.now().strftime('%Y%m%d')}", "Pending",
             f"Gross ₹{gross_amount:,.2f} minus supplies ₹{supply_cost:,.2f}", now_str()))
        conn.commit(); conn.close()
        flash(f"Harvest recorded! Net payment of ₹{net_amount:,.2f} created after supplies.", "success")
        return redirect(url_for("farm_detail", id=farm_id))
    conn.close()
    return render_template("farms/harvest_form.html", farm=farm)

# ─── PAYMENTS ─────────────────────────────────────────────────────────────────
@app.route("/payments")
def payments():
    user_id = get_current_user_id()
    conn = get_db()
    rows = conn.execute("""SELECT p.*, fa.name as farmer_name, f.farm_name
        FROM payments p JOIN farmers fa ON p.farmer_id=fa.id JOIN farms f ON p.farm_id=f.id
        WHERE p.user_id=? ORDER BY p.payment_date DESC""", (user_id,)).fetchall()
    conn.close()
    return render_template("payments/list.html", payments=rows)

@app.route("/payments/<int:id>/pay", methods=["POST"])
def mark_paid(id):
    user_id = get_current_user_id()
    conn = get_db()
    now = datetime.now()
    conn.execute("UPDATE payments SET status='Paid', payment_date=?, payment_time=? WHERE id=? AND user_id=?",
        (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), id, user_id))
    conn.commit(); conn.close()
    flash("Payment marked as Paid!", "success")
    return redirect(url_for("payments"))

@app.route("/payments/add", methods=["GET","POST"])
def add_payment():
    user_id = get_current_user_id()
    conn = get_db()
    farmers_list = conn.execute("SELECT id,name FROM farmers WHERE status='Active' AND user_id=?", (user_id,)).fetchall()
    farms_list   = conn.execute("SELECT f.id,f.farm_name,fa.name as farmer_name FROM farms f JOIN farmers fa ON f.farmer_id=fa.id WHERE f.user_id=?", (user_id,)).fetchall()
    if request.method == "POST":
        now = datetime.now()
        conn.execute("INSERT INTO payments (user_id,farmer_id,farm_id,amount,payment_type,payment_date,payment_time,reference,status,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, request.form["farmer_id"], request.form["farm_id"], request.form["amount"],
             request.form["payment_type"], request.form.get("payment_date") or today_str(),
             now.strftime("%H:%M:%S"), request.form["reference"],
             request.form.get("status","Pending"), request.form["notes"], now_str()))
        conn.commit(); conn.close()
        flash("Payment recorded!", "success")
        return redirect(url_for("payments"))
    conn.close()
    return render_template("payments/form.html", farmers_list=farmers_list, farms_list=farms_list)

# ─── PDF REPORT ───────────────────────────────────────────────────────────────
@app.route("/farms/<int:id>/report")
def farm_report(id):
    user_id = get_current_user_id()
    conn = get_db()
    farm     = conn.execute("SELECT f.*,fa.name as farmer_name,fa.phone,fa.address FROM farms f JOIN farmers fa ON f.farmer_id=fa.id WHERE f.id=? AND f.user_id=?", (id, user_id)).fetchone()
    if not farm:
        conn.close()
        flash("Farm not found or access denied.", "error")
        return redirect(url_for("farms"))
    seeds    = conn.execute("SELECT * FROM seeds WHERE farm_id=? AND user_id=?", (id, user_id)).fetchall()
    supplies = conn.execute("SELECT * FROM supplies WHERE farm_id=? AND user_id=?", (id, user_id)).fetchall()
    updates  = conn.execute("SELECT * FROM daily_updates WHERE farm_id=? AND user_id=? ORDER BY update_date,update_time", (id, user_id)).fetchall()
    harvests = conn.execute("SELECT * FROM harvests WHERE farm_id=? AND user_id=?", (id, user_id)).fetchall()
    payments = conn.execute("SELECT * FROM payments WHERE farm_id=? AND user_id=?", (id, user_id)).fetchall()
    conn.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    GREEN  = colors.HexColor("#2d6a4f")
    LGREEN = colors.HexColor("#d8f3dc")
    GOLD   = colors.HexColor("#b7791f")

    title_style = ParagraphStyle("Title", parent=styles["Title"], textColor=GREEN, fontSize=20, spaceAfter=4)
    h2_style    = ParagraphStyle("H2", parent=styles["Heading2"], textColor=GREEN, fontSize=13, spaceBefore=12, spaceAfter=4)
    normal      = styles["Normal"]

    def section_table(headers, data, col_widths=None):
        tdata = [headers] + data
        t = Table(tdata, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), GREEN),
            ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0), (-1,-1), 8),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGREEN]),
            ("GRID",       (0,0), (-1,-1), 0.4, colors.HexColor("#95d5b2")),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("PADDING",    (0,0), (-1,-1), 5),
        ]))
        return t

    story = []
    story.append(Paragraph("🌿 ECO FARMS", title_style))
    story.append(Paragraph("Farm Activity Report", ParagraphStyle("sub", parent=normal, textColor=GOLD, fontSize=11)))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", ParagraphStyle("gen", parent=normal, fontSize=8, textColor=colors.grey)))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GREEN, spaceAfter=10))

    # Farm Info
    story.append(Paragraph("Farm Information", h2_style))
    info = [
        ["Farm Name", farm["farm_name"], "Farmer", farm["farmer_name"]],
        ["Location", farm["location"], "Phone", farm["phone"] or "—"],
        ["Crop", farm["crop_type"], "Area", f"{farm['area_acres']} acres"],
        ["Season", farm["season"], "Status", farm["status"]],
        ["Start Date", farm["start_date"], "Address", farm["address"] or "—"],
    ]
    info_table = Table(info, colWidths=[3.5*cm, 7*cm, 3*cm, 4.5*cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME",(0,0),(-1,-1),"Helvetica"), ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
        ("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9),
        ("BACKGROUND",(0,0),(-1,-1),LGREEN), ("GRID",(0,0),(-1,-1),0.4,GREEN),
        ("PADDING",(0,0),(-1,-1),5),
    ]))
    story.append(info_table)

    # Seeds
    story.append(Paragraph("Seeds Sown", h2_style))
    if seeds:
        story.append(section_table(
            ["Seed Name","Variety","Qty (kg)","Sow Date","Notes"],
            [[s["seed_name"],s["variety"],s["quantity_kg"],s["sow_date"],s["notes"] or "—"] for s in seeds],
            [4*cm,4*cm,3*cm,4*cm,3*cm]
        ))
    else:
        story.append(Paragraph("No seed records.", normal))

    # Supplies
    story.append(Paragraph("Supplies Provided", h2_style))
    if supplies:
        story.append(section_table(
            ["Item","Type","Qty","Unit","Date","Notes"],
            [[s["supply_name"],s["supply_type"],s["quantity"],s["unit"],s["supply_date"],s["notes"] or "—"] for s in supplies],
            [3.5*cm,3*cm,2*cm,2*cm,3.5*cm,4*cm]
        ))
    else:
        story.append(Paragraph("No supply records.", normal))

    # Daily Updates
    story.append(Paragraph("Daily Updates", h2_style))
    if updates:
        story.append(section_table(
            ["Date","Time","Stage","Weather","Notes","Issue"],
            [[u["update_date"],u["update_time"],u["growth_stage"],u["weather"],
              (u["description"] or "")[:50],u["issue_reported"] or "None"] for u in updates],
            [2.5*cm,2*cm,3*cm,2.5*cm,5*cm,3*cm]
        ))
    else:
        story.append(Paragraph("No updates logged.", normal))

    # Harvest
    story.append(Paragraph("Harvest Summary", h2_style))
    if harvests:
        story.append(section_table(
            ["Date","Output (kg)","Grade","Rate/kg","Total Value","Notes"],
            [[h["harvest_date"],h["total_output_kg"],h["quality_grade"],
              f"₹{h['rate_per_kg']}",f"₹{h['total_output_kg']*h['rate_per_kg']:,.2f}",h["notes"] or "—"] for h in harvests],
            [2.5*cm,3*cm,2.5*cm,2.5*cm,4*cm,3.5*cm]
        ))
        total = sum(h["total_output_kg"]*h["rate_per_kg"] for h in harvests)
        story.append(Paragraph(f"<b>Total Harvest Value: ₹{total:,.2f}</b>",
            ParagraphStyle("tot", parent=normal, textColor=GREEN, fontSize=10, spaceBefore=6)))
    else:
        story.append(Paragraph("No harvest recorded.", normal))

    # Payments
    story.append(Paragraph("Payment Records", h2_style))
    if payments:
        story.append(section_table(
            ["Date","Type","Amount","Status","Reference","Notes"],
            [[p["payment_date"],p["payment_type"],f"₹{p['amount']:,.2f}",p["status"],p["reference"] or "—",p["notes"] or "—"] for p in payments],
            [2.5*cm,3.5*cm,3*cm,2.5*cm,4*cm,2.5*cm]
        ))
        total_paid = sum(p["amount"] for p in payments if p["status"]=="Paid")
        story.append(Paragraph(f"<b>Total Paid: ₹{total_paid:,.2f}</b>",
            ParagraphStyle("tot2", parent=normal, textColor=GOLD, fontSize=10, spaceBefore=6)))
    else:
        story.append(Paragraph("No payments.", normal))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREEN))
    story.append(Paragraph("Eco Farms Management System — Confidential Report", 
        ParagraphStyle("footer", parent=normal, fontSize=7, textColor=colors.grey, alignment=1)))

    doc.build(story)
    buf.seek(0)
    resp = make_response(buf.read())
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename=farm_{id}_report.pdf"
    return resp

if __name__ == "__main__":
    app.run(debug=True, port=5000)
