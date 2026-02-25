from flask import Flask, render_template, request, redirect, url_for, session, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import styles
from reportlab.lib.units import inch
import os

app = Flask(__name__)
app.secret_key = "super_secret_key"

DATABASE = "database.db"

# ---------------- DATABASE ---------------- #

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        matric TEXT UNIQUE,
        name TEXT,
        level TEXT,
        password TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        title TEXT,
        unit INTEGER,
        level TEXT,
        semester TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        course_id INTEGER,
        score INTEGER,
        grade TEXT,
        grade_point INTEGER,
        approved INTEGER DEFAULT 0
    )''')

    # Default Admin
    if not c.execute("SELECT * FROM admin").fetchone():
        c.execute("INSERT INTO admin (username, password) VALUES (?,?)",
                  ("admin", generate_password_hash("admin123")))

    conn.commit()
    conn.close()

init_db()

# ---------------- GRADE SYSTEM ---------------- #

def calculate_grade(score):
    if score >= 70:
        return "A", 5
    elif score >= 60:
        return "B", 4
    elif score >= 50:
        return "C", 3
    elif score >= 45:
        return "D", 2
    elif score >= 40:
        return "E", 1
    else:
        return "F", 0

# ---------------- HOME ---------------- #

@app.route("/")
def index():
    return render_template("index.html")

# ---------------- STUDENT LOGIN ---------------- #

@app.route("/student-login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        matric = request.form["matric"]
        password = request.form["password"]

        conn = get_db()
        student = conn.execute("SELECT * FROM students WHERE matric=?", (matric,)).fetchone()
        conn.close()

        if student and check_password_hash(student["password"], password):
            session["student_id"] = student["id"]
            return redirect("/student-dashboard")

    return render_template("student_login.html")

@app.route("/student-dashboard")
def student_dashboard():
    if "student_id" not in session:
        return redirect("/student-login")

    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()

    results = conn.execute('''
        SELECT courses.code, courses.title, courses.unit,
               results.score, results.grade, results.grade_point
        FROM results
        JOIN courses ON results.course_id = courses.id
        WHERE results.student_id=? AND results.approved=1
    ''', (student["id"],)).fetchall()

    total_units = 0
    total_points = 0

    for r in results:
        total_units += r["unit"]
        total_points += r["unit"] * r["grade_point"]

    gpa = round(total_points / total_units, 2) if total_units > 0 else 0

    conn.close()
    return render_template("student_dashboard.html", student=student, results=results, gpa=gpa)

# ---------------- ADMIN LOGIN ---------------- #

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        admin = conn.execute("SELECT * FROM admin WHERE username=?", (username,)).fetchone()
        conn.close()

        if admin and check_password_hash(admin["password"], password):
            session["admin"] = True
            return redirect("/admin-dashboard")

    return render_template("admin_login.html")

@app.route("/admin-dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect("/admin-login")

    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    total_courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    total_results = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
    conn.close()

    return render_template("admin_dashboard.html",
                           students=total_students,
                           courses=total_courses,
                           results=total_results)

# ---------------- ADD STUDENT ---------------- #

@app.route("/add-student", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        matric = request.form["matric"]
        name = request.form["name"]
        level = request.form["level"]
        password = generate_password_hash(request.form["password"])

        conn = get_db()
        conn.execute("INSERT INTO students (matric,name,level,password) VALUES (?,?,?,?)",
                     (matric, name, level, password))
        conn.commit()
        conn.close()
        return redirect("/admin-dashboard")

    return render_template("add_student.html")

# ---------------- ADD COURSE ---------------- #

@app.route("/add-course", methods=["GET", "POST"])
def add_course():
    if request.method == "POST":
        code = request.form["code"]
        title = request.form["title"]
        unit = request.form["unit"]
        level = request.form["level"]
        semester = request.form["semester"]

        conn = get_db()
        conn.execute("INSERT INTO courses (code,title,unit,level,semester) VALUES (?,?,?,?,?)",
                     (code, title, unit, level, semester))
        conn.commit()
        conn.close()
        return redirect("/admin-dashboard")

    return render_template("add_course.html")

# ---------------- UPLOAD RESULT ---------------- #

@app.route("/upload-result", methods=["GET", "POST"])
def upload_result():
    conn = get_db()

    students = conn.execute("SELECT * FROM students").fetchall()
    courses = conn.execute("SELECT * FROM courses").fetchall()

    if request.method == "POST":
        student_id = request.form["student_id"]
        course_id = request.form["course_id"]
        score = int(request.form["score"])

        grade, gp = calculate_grade(score)

        conn.execute("INSERT INTO results (student_id,course_id,score,grade,grade_point) VALUES (?,?,?,?,?)",
                     (student_id, course_id, score, grade, gp))
        conn.commit()
        return redirect("/admin-dashboard")

    return render_template("upload_result.html", students=students, courses=courses)

# ---------------- APPROVE RESULT ---------------- #

@app.route("/approve/<int:id>")
def approve(id):
    conn = get_db()
    conn.execute("UPDATE results SET approved=1 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin-dashboard")

# ---------------- PDF GENERATION ---------------- #

@app.route("/download-pdf")
def download_pdf():
    if "student_id" not in session:
        return redirect("/student-login")

    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE id=?", (session["student_id"],)).fetchone()
    results = conn.execute('''
        SELECT courses.code, courses.title, courses.unit,
               results.score, results.grade
        FROM results
        JOIN courses ON results.course_id = courses.id
        WHERE results.student_id=? AND results.approved=1
    ''', (student["id"],)).fetchall()

    file_path = "result.pdf"
    doc = SimpleDocTemplate(file_path)
    elements = []

    elements.append(Paragraph(f"Name: {student['name']}", styles.getSampleStyleSheet()["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    data = [["Code", "Title", "Unit", "Score", "Grade"]]
    for r in results:
        data.append([r["code"], r["title"], r["unit"], r["score"], r["grade"]])

    table = Table(data)
    table.setStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])

    elements.append(table)
    doc.build(elements)

    conn.close()
    return send_file(file_path, as_attachment=True)
#-------------------View Result------------------#
@app.route("/view-results")
def view_results():
    if "admin" not in session:
        return redirect("/admin-login")

    conn = get_db()
    results = conn.execute('''
        SELECT results.id,
               students.name AS student,
               courses.code || ' - ' || courses.title AS course,
               results.score,
               results.grade,
               results.approved
        FROM results
        JOIN students ON results.student_id = students.id
        JOIN courses ON results.course_id = courses.id
    ''').fetchall()

    conn.close()
    return render_template("view_result.html", results=results)

# ---------------- LOGOUT ---------------- #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
