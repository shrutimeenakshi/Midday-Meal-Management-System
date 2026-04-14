from flask import Flask, flash, render_template, request, redirect, session, url_for
import sqlite3
import qrcode
import os
from datetime import datetime
import cv2
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "midday_meal_secret"

DATABASE = "database.db"
QR_FOLDER = "static/qr_codes"
os.makedirs(QR_FOLDER, exist_ok=True)

# ---------------- DATABASE CONNECTION ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------- NUTRITION RECOMMENDATION ----------------
# ---------------- NUTRITION RECOMMENDATION ----------------
def get_nutrition_recommendation(student_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT deficiency FROM student_health WHERE student_id=?",
        (student_id,)
    )

    result = cursor.fetchone()
    conn.close()

    if not result:
        return "Standard School Meal"

    deficiency = result[0]

    if deficiency == "Iron":
        return "Spinach + Lentils (Iron rich meal)"

    elif deficiency == "Protein":
        return "Egg + Dal (High protein meal)"

    elif deficiency == "Calcium":
        return "Milk + Paneer (Calcium rich meal)"

    return "Standard School Meal"

# ---------------- BMI + DEFICIENCY DETECTION ----------------
def detect_health_status(height, weight, hemoglobin):
    height_m = height / 100
    bmi = weight / (height_m ** 2)

    bmi_status = "Normal"
    deficiencies = [] # Use a list to catch multiple problems

    # Check for Protein (Underweight)
    if bmi < 14:
        bmi_status = "Underweight"
        deficiencies.append("Protein")
    elif bmi > 22:
        bmi_status = "Overweight"

    # Check for Iron (Anemia)
    if hemoglobin and hemoglobin < 11:
        deficiencies.append("Iron")

    # Combine them into a single string
    if not deficiencies:
        deficiency_str = "None"
    else:
        deficiency_str = " & ".join(deficiencies) # Becomes "Iron", "Protein", or "Protein & Iron"

    return round(bmi, 2), bmi_status, deficiency_str
# ---------------- AUTH DECORATORS ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access only!", "danger")
            return redirect(url_for("staff_dashboard"))
        return f(*args, **kwargs)
    return wrapper

# ---------------- DATABASE INIT ----------------
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )
""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            student_class TEXT NOT NULL,
            section TEXT NOT NULL,
            qr_code TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meal_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            date TEXT,
            time TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            student_id INTEGER,
            timestamp TEXT
        )
    """)

    # Default admin
    cursor.execute("SELECT * FROM staff WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO staff (username, password, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin")
        )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            height REAL,
            weight REAL,
            hemoglobin REAL,
            bmi REAL,
            bmi_status TEXT,
            deficiency TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS foods (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          food_name TEXT,
          calories REAL,
          protein REAL,
          iron REAL,
          calcium REAL
        )
    """)

    # Add this inside your init_db() function in app.py

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT UNIQUE,
            quantity_kg REAL,
            threshold_kg REAL
        )
    """)

    # Seed initial inventory if empty
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] == 0:
        initial_stock = [
            ("Rice", 50.0, 10.0),       # 50kg stock, alert at 10kg
            ("Dal", 20.0, 5.0),         # 20kg stock, alert at 5kg
            ("Vegetables", 30.0, 8.0),  # 30kg stock, alert at 8kg
            ("Eggs (Count)", 200.0, 50.0) # 200 eggs, alert at 50
        ]
        cursor.executemany(
            "INSERT INTO inventory (item_name, quantity_kg, threshold_kg) VALUES (?, ?, ?)",
            initial_stock
        )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_menu (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date TEXT,
          food_items TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_type = request.form["login_type"]
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff WHERE username=?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password) and user[3] == login_type:

            # 🚫 Block deactivated staff
            if user[4] == 0:
                flash("Your account is deactivated. Contact admin.", "danger")
                return redirect(url_for("login"))

            session["user_id"] = user[0]
            session["username"] = user[1]
            session["role"] = user[3]

            return redirect(
                url_for(
                    "admin_dashboard" if user[3] == "admin" else "staff_dashboard"
                )
            )

        flash("Invalid credentials", "danger")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

# ---------------- ADMIN DASHBOARD ----------------
# ---------------- SIMPLIFIED ADMIN DASHBOARD ----------------
@app.route("/admin_dashboard")
@login_required
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Fetch Student & Meal Stats
    cursor.execute("SELECT COUNT(*) FROM students WHERE is_active=1")
    total_students = cursor.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(DISTINCT student_id) FROM meal_records WHERE date=?", (today,))
    meals_taken_result = cursor.fetchone()
    meals_taken = meals_taken_result[0] if meals_taken_result else 0
    not_taken = max(0, total_students - meals_taken)

    cursor.execute("SELECT * FROM students WHERE is_active=1")
    students = cursor.fetchall()
    
    # 2. CHECK FOR LOW INVENTORY (NEW)
    # This checks if any item's current stock is less than or equal to its threshold
    cursor.execute("SELECT COUNT(*) FROM inventory WHERE quantity_kg <= threshold_kg")
    low_stock_count = cursor.fetchone()[0]
    low_stock_alert = low_stock_count > 0  # Becomes True if stock is low

    conn.close()

    return render_template(
        "dashboard.html",
        students=students,
        total_students=total_students,
        meals_taken=meals_taken,
        not_taken=not_taken,
        role="admin",
        low_stock_alert=low_stock_alert # Pass the alert status to HTML
    )
# ---------------- STAFF DASHBOARD ----------------
@app.route("/staff_dashboard")
@login_required
def staff_dashboard():
    if session.get("role") != "staff":
        return redirect(url_for("admin_dashboard"))
    return render_template("staff_dashboard.html")

@app.route("/dashboard")
@login_required
def dashboard_redirect():
    return redirect(
        url_for("admin_dashboard")
        if session.get("role") == "admin"
        else url_for("staff_dashboard")
    )

# ---------------- ADD STAFF ----------------
@app.route("/add_staff", methods=["GET", "POST"])
@login_required
@admin_required
def add_staff():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO staff (username, password, role) VALUES (?, ?, ?)",
                (username, password, role)
            )
            conn.commit()
            flash("Staff added successfully", "success")
            return redirect(url_for("staff_list"))

        except sqlite3.IntegrityError:
            flash("Username already exists", "danger")

        finally:
            conn.close()

    return render_template("add_staff.html")

# ---------------- ADD STUDENT ----------------
@app.route("/add_student", methods=["GET", "POST"])
@login_required
@admin_required
def add_student():
    if request.method == "POST":
        name = request.form["name"]
        student_class = request.form["student_class"]
        section = request.form["section"]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO students (name, student_class, section) VALUES (?, ?, ?)",
            (name, student_class, section)
        )
        student_id = cursor.lastrowid

        qr = qrcode.make(str(student_id))
        qr_path = os.path.join(QR_FOLDER, f"{student_id}.png")
        qr.save(qr_path)

        cursor.execute(
            "UPDATE students SET qr_code=? WHERE id=?",
            (qr_path, student_id)
        )

        conn.commit()
        conn.close()
        flash("Student added successfully", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_student.html")

# ---------------- CAMERA SCAN ----------------
# ---------------- CAMERA SCAN ----------------
@app.route("/camera_scan")
@login_required
def camera_scan():
    cap = cv2.VideoCapture(0)
    detector = cv2.QRCodeDetector()

    scanned = False  # 🔒 prevents multiple scans

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        data, _, _ = detector.detectAndDecode(frame)

        if data and not scanned:
            scanned = True  # 🔒 lock scanning

            student_id = int(data)
            today = datetime.now().strftime("%Y-%m-%d")
            time_now = datetime.now().strftime("%H:%M:%S")

            conn = get_db()
            cursor = conn.cursor()

            # check if already scanned today
            cursor.execute(
                "SELECT 1 FROM meal_records WHERE student_id=? AND date=?",
                (student_id, today)
            )

            if cursor.fetchone():
                flash("Meal already marked today", "warning")
            else:
                cursor.execute(
                    "INSERT INTO meal_records (student_id, date, time) VALUES (?, ?, ?)",
                    (student_id, today, time_now)
                )

                cursor.execute(
                    "INSERT INTO activity_logs (user, action, student_id, timestamp) VALUES (?, ?, ?, ?)",
                    (
                        session["username"],
                        "SCAN_MEAL",
                        student_id,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                )

                # --- AUTOMATIC INVENTORY DEDUCTION ---
                # Deduct 150g (0.15kg) Rice per meal
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity_kg = quantity_kg - 0.15 
                    WHERE item_name = 'Rice' AND quantity_kg >= 0.15
                """)
                # Deduct 50g (0.05kg) Dal per meal
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity_kg = quantity_kg - 0.05 
                    WHERE item_name = 'Dal' AND quantity_kg >= 0.05
                """)
                # Deduct 1 Egg per meal
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity_kg = quantity_kg - 1.0 
                    WHERE item_name = 'Eggs (Count)' AND quantity_kg >= 1.0
                """)
                # --------------------------------------

                conn.commit()
                recommendation = get_nutrition_recommendation(student_id)

                flash(
                    f"Meal marked successfully. Suggested nutrition: {recommendation}",
                    "success"
                )

            conn.close()

            # show success frame for 1 second
            cv2.putText(
                frame,
                "SCAN SUCCESSFUL",
                (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )
            cv2.imshow("Scan QR", frame)
            cv2.waitKey(1000)  # ⏱ pause so staff can see confirmation
            break

        cv2.imshow("Scan QR", frame)

        # allow manual exit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    return redirect(
        url_for("admin_dashboard")
        if session.get("role") == "admin"
        else url_for("staff_dashboard")
    )

# ---------------- SOFT DELETE ----------------
@app.route("/delete_student/<int:student_id>")
@login_required
@admin_required
def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE students SET is_active=0 WHERE id=?", (student_id,))
    cursor.execute(
        "INSERT INTO activity_logs (user, action, student_id, timestamp) VALUES (?, ?, ?, ?)",
        (session["username"], "DELETE_STUDENT", student_id,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

    conn.commit()
    conn.close()
    flash("Student moved to deleted list", "warning")
    return redirect(url_for("admin_dashboard"))

# ---------------- RESTORE ----------------
@app.route("/deleted_students")
@login_required
@admin_required
def deleted_students():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, student_class, section FROM students WHERE is_active=0")
    students = cursor.fetchall()
    conn.close()
    return render_template("deleted_students.html", students=students)

@app.route("/restore_student/<int:student_id>")
@login_required
@admin_required
def restore_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET is_active=1 WHERE id=?", (student_id,))
    cursor.execute(
        "INSERT INTO activity_logs (user, action, student_id, timestamp) VALUES (?, ?, ?, ?)",
        (session["username"], "RESTORE_STUDENT", student_id,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    flash("Student restored", "success")
    return redirect(url_for("deleted_students"))

# ---------------- STAFF LIST ----------------
@app.route("/staff_list")
@login_required
@admin_required
def staff_list():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, is_active FROM staff")
    staff = cursor.fetchall()
    conn.close()
    return render_template("staff_list.html", staff_members=staff)

@app.route("/toggle_staff/<int:staff_id>")
@login_required
@admin_required
def toggle_staff(staff_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE staff SET is_active = CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=?",
        (staff_id,)
    )

    conn.commit()
    conn.close()

    flash("Staff status updated", "info")
    return redirect(url_for("staff_list"))

# ---------------- ACTIVITY LOGS ----------------
@app.route("/activity_logs")
@login_required
@admin_required
def activity_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user, action, student_id, timestamp
        FROM activity_logs
        ORDER BY id DESC
    """)
    logs = cursor.fetchall()
    conn.close()
    return render_template("activity_logs.html", logs=logs)

@app.route("/meals_taken")
@login_required
def meals_taken():
    selected_date = request.args.get("date")

    if not selected_date:
        selected_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.name, s.student_class, s.section
        FROM students s
        JOIN meal_records m ON s.id = m.student_id
        WHERE m.date = ?
          AND s.is_active = 1
    """, (selected_date,))

    students = cursor.fetchall()
    conn.close()

    return render_template(
        "meal_list.html",
        title=f"Students Who Took Meal on {selected_date}",
        students=students
    )


@app.route("/meals_not_taken")
@login_required
def meals_not_taken():
    selected_date = request.args.get("date")

    if not selected_date:
        selected_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, student_class, section
        FROM students
        WHERE is_active = 1
          AND id NOT IN (
              SELECT student_id FROM meal_records WHERE date = ?
          )
    """, (selected_date,))

    students = cursor.fetchall()
    conn.close()

    return render_template(
        "meal_list.html",
        title=f"Students Who Did Not Take Meal on {selected_date}",
        students=students
    )
# ---------------- ADD STUDENT HEALTH ----------------
@app.route("/add_student_health", methods=["GET","POST"])
@login_required
@admin_required
def add_student_health():

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":

        student_id = request.form["student_id"]
        height = float(request.form["height"])
        weight = float(request.form["weight"])
        hemoglobin = float(request.form["hemoglobin"])

        bmi, bmi_status, deficiency = detect_health_status(
            height, weight, hemoglobin
        )

        # 1. SMART UPDATE: Check if student already has a main health record
        cursor.execute("SELECT 1 FROM student_health WHERE student_id=?", (student_id,))
        if cursor.fetchone():
            # Update their existing main record
            cursor.execute("""
                UPDATE student_health 
                SET height=?, weight=?, hemoglobin=?, bmi=?, bmi_status=?, deficiency=?
                WHERE student_id=?
            """, (height, weight, hemoglobin, bmi, bmi_status, deficiency, student_id))
        else:
            # Insert a brand new main record
            cursor.execute("""
                INSERT INTO student_health
                (student_id,height,weight,hemoglobin,bmi,bmi_status,deficiency)
                VALUES (?,?,?,?,?,?,?)
            """,(student_id,height,weight,hemoglobin,bmi,bmi_status,deficiency))

        # 2. THE NEW PART: Always save a copy to the history table for the Growth Chart
        today_date = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            INSERT INTO health_history (student_id, height, weight, bmi, hemoglobin, date_recorded) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_id, height, weight, bmi, hemoglobin, today_date))

        conn.commit()
        conn.close()

        flash("Health data successfully recorded and history updated!", "success")
        return redirect(url_for("admin_dashboard"))

    # If it's a GET request, just load the dropdown
    cursor.execute("SELECT id,name FROM students WHERE is_active=1")
    students = cursor.fetchall()
    conn.close()

    return render_template(
        "add_student_health.html",
        students=students
    )

# ---------------- INDIVIDUAL STUDENT PROFILE (GROWTH TRACKER) ----------------
@app.route("/student_profile/<int:student_id>")
@login_required
def student_profile(student_id):
    conn = get_db()
    cursor = conn.cursor()

    # Get basic student info
    cursor.execute("SELECT * FROM students WHERE id=?", (student_id,))
    student = cursor.fetchone()

    # Get their current health status
    cursor.execute("SELECT * FROM student_health WHERE student_id=?", (student_id,))
    current_health = cursor.fetchone()

    # Get their health history for the chart, ordered by date
    cursor.execute("""
        SELECT date_recorded, height, weight, bmi, hemoglobin 
        FROM health_history 
        WHERE student_id=? 
        ORDER BY date_recorded ASC
    """, (student_id,))
    history = cursor.fetchall()

    conn.close()

    return render_template(
        "student_profile.html", 
        student=student, 
        current_health=current_health, 
        history=history
    )

@app.route("/analytics")
@login_required
@admin_required
def analytics():
    conn = get_db()
    cursor = conn.cursor()

    # 1. HANDLE DATE & MONTH FILTERS
    selected_date = request.args.get("date")
    selected_month = request.args.get("month")

    if not selected_date:
        selected_date = datetime.now().strftime("%Y-%m-%d")
    
    if not selected_month:
        selected_month = datetime.now().strftime("%Y-%m")

    # 2. BASIC MEAL STATS
    cursor.execute("SELECT COUNT(*) FROM students WHERE is_active=1")
    total_students = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT m.student_id)
        FROM meal_records m
        JOIN students s ON s.id = m.student_id
        WHERE m.date = ?
          AND s.is_active = 1
    """, (selected_date,))
    meals_taken_result = cursor.fetchone()
    meals_taken = meals_taken_result[0] if meals_taken_result else 0
    not_taken = max(0, total_students - meals_taken)

    # 3. NUTRITION CHART DATA (COUNTS) - 🛠️ UPDATED FOR COMBINED DEFICIENCIES
    cursor.execute("SELECT COUNT(*) FROM student_health WHERE deficiency LIKE '%Iron%'")
    iron_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM student_health WHERE deficiency LIKE '%Protein%'")
    protein_count = cursor.fetchone()[0]

    # Only count them as healthy if they have absolutely 'None'
    cursor.execute("SELECT COUNT(*) FROM student_health WHERE deficiency='None'")
    healthy_count = cursor.fetchone()[0]

    # 4. HEALTH ALERT TABLE (SPECIFIC STUDENT DETAILS)
    cursor.execute("""
        SELECT s.name, s.student_class, h.hemoglobin, h.deficiency 
        FROM students s 
        JOIN student_health h ON s.id = h.student_id 
        WHERE h.deficiency != 'None' AND s.is_active = 1
    """)
    health_alerts = cursor.fetchall()

    conn.close()

    # 5. RENDER EVERYTHING TO THE DASHBOARD
    return render_template(
        "analytics.html",
        total_students=total_students,
        meals_taken=meals_taken,
        not_taken=not_taken,
        selected_date=selected_date,
        selected_month=selected_month, 
        iron_count=iron_count,
        protein_count=protein_count,
        healthy_count=healthy_count,
        health_alerts=health_alerts
    )

@app.route("/kitchen")
@login_required
@admin_required
def kitchen():
    conn = get_db()
    cursor = conn.cursor()

    # Fetch Live Inventory Data
    cursor.execute("SELECT item_name, quantity_kg, threshold_kg FROM inventory")
    inventory_data = cursor.fetchall()

    # AI WEEKLY MENU PLANNER LOGIC
    cursor.execute("SELECT COUNT(*) FROM student_health WHERE deficiency LIKE '%Iron%'")
    total_iron_issues = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM student_health WHERE deficiency LIKE '%Protein%'")
    total_protein_issues = cursor.fetchone()[0]

    if total_iron_issues > total_protein_issues and total_iron_issues > 0:
        smart_menu = {
            "Monday": "Spinach Dal & Rice (Iron+)",
            "Tuesday": "Ragi Roti & Sabzi (Iron+)",
            "Wednesday": "Egg Curry & Rice (Balanced)",
            "Thursday": "Beetroot Pulao & Raita (Iron+)",
            "Friday": "Chickpea Sundal & Rice (Protein/Iron)"
        }
        menu_focus = "Iron-Rich Diet (Anemia Alert)"
        focus_color = "warning" 
        
    elif total_protein_issues >= total_iron_issues and total_protein_issues > 0:
        smart_menu = {
            "Monday": "Double Dal & Rice (Protein+)",
            "Tuesday": "Soya Chunks Pulao (Protein+)",
            "Wednesday": "Double Egg Curry & Rice (Protein+)",
            "Thursday": "Paneer/Tofu Sabzi & Roti (Protein+)",
            "Friday": "Black Chana & Rice (Protein+)"
        }
        menu_focus = "High Protein Diet (Underweight Alert)"
        focus_color = "danger"

    else:
         smart_menu = {
            "Monday": "Standard Dal & Rice",
            "Tuesday": "Mixed Veg Pulao",
            "Wednesday": "Egg Curry & Rice",
            "Thursday": "Rajma Chawal",
            "Friday": "Lemon Rice & Chana"
        }
         menu_focus = "Standard Balanced Diet"
         focus_color = "success"

    conn.close()

    return render_template(
        "kitchen.html",
        inventory=inventory_data,
        smart_menu=smart_menu,
        menu_focus=menu_focus,
        focus_color=focus_color
    )
# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
