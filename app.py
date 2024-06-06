from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
from datetime import datetime
import cv2
from pyzbar.pyzbar import decode
import numpy as np
import os
 
app = Flask(__name__) 
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key')

# Database configuration
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', '')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'academic_support_system')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app) 

# Create tables if they do not exist
def create_tables():
    with app.app_context():
        cur = mysql.connection.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usersss (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(100)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                course_name VARCHAR(255) NOT NULL,
                lecturer_id INT NOT NULL,
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                lecturer_id INT NOT NULL,
                appointment_time DATETIME NOT NULL,
                reason TEXT NOT NULL,
                feedback TEXT,
                FOREIGN KEY (student_id) REFERENCES usersss(id),
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                appointment_id INT NOT NULL,
                lecturer_id INT NOT NULL,
                student_id INT NOT NULL,
                FOREIGN KEY (appointment_id) REFERENCES appointments(id),
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id),
                FOREIGN KEY (student_id) REFERENCES usersss(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                course_id INT NOT NULL,
                attendance_date DATE NOT NULL,
                present TINYINT(1) NOT NULL DEFAULT 0,
                mark FLOAT NOT NULL DEFAULT 0,
                FOREIGN KEY (student_id) REFERENCES usersss(id),
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        """)
        mysql.connection.commit()
        cur.close()

create_tables()

@app.route('/')
def landing_page():
    if 'user_id' in session:
        return redirect(url_for('landing_after_login'))
    return render_template('landing.html')

@app.route('/home')
def home():
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    role = request.form['role']

    if password == confirm_password:
        hashed_password = generate_password_hash(password)
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO usersss (email, password, role) VALUES (%s, %s, %s)", (email, hashed_password, role))
        mysql.connection.commit()
        cur.close()
        flash("Signup successful. You can now login.")
        return redirect(url_for('home'))
    else:
        flash("Passwords do not match. Try again.")
        return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM usersss WHERE email = %s", [email])
    user = cur.fetchone()
    cur.close()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['user_abbr'] = user['email'][:5].upper()
        flash(f"You were successfully logged in as {session['user_abbr']}")

        if user['role'] == 'Student':
            return redirect(url_for('student_dashboard'))
        elif user['role'] == 'Lecturer':
            return redirect(url_for('lecturer_dashboard'))
        elif user['role'] == 'Parent':
            return redirect(url_for('parent_dashboard'))
    else:
        flash("Invalid login credentials. Please try again.")
        return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You were successfully logged out")
    return render_template('landing.html')

@app.route('/landing2')
def landing_after_login():
    if 'user_id' in session:
        user_id = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("SELECT email FROM usersss WHERE id = %s", [user_id])
        user = cur.fetchone()
        cur.close()

        user_abbr = user['email'][:5].upper() if user else ''
        return render_template('landing.html', user_abbr=user_abbr)
    else:
        return redirect(url_for('home'))

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM appointments WHERE lecturer_id = %s AND feedback IS NULL", [lecturer_id])
        appointments = cur.fetchall()
        cur.close()

        return render_template('notifications.html', appointments=appointments)
    else:
        return redirect(url_for('home'))

@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, email, role FROM usersss WHERE role = 'Lecturer'")
    lecturers = cur.fetchall()

    if request.method == 'POST':
        student_id = session['user_id']
        lecturer_id = request.form['lecturer_id']
        appointment_time = request.form['appointment_time']
        reason = request.form['reason']

        cur.execute("INSERT INTO appointments (student_id, lecturer_id, appointment_time, reason) VALUES (%s, %s, %s, %s)",
                    (student_id, lecturer_id, appointment_time, reason))
        mysql.connection.commit()
        appointment_id = cur.lastrowid

        cur.execute("INSERT INTO notifications (appointment_id, lecturer_id, student_id) VALUES (%s, %s, %s)",
                    (appointment_id, lecturer_id, student_id))
        mysql.connection.commit()
        cur.close()

        flash("Appointment scheduled successfully.")
        return redirect(url_for('appointments'))

    return render_template('appointments.html', lecturers=lecturers)

@app.route('/appointments/feedback/<int:appointment_id>', methods=['POST'])
def provide_feedback(appointment_id):
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    feedback = request.form['feedback']
    cur = mysql.connection.cursor()
    cur.execute("UPDATE appointments SET feedback = %s WHERE id = %s", (feedback, appointment_id))
    mysql.connection.commit()
    cur.close()

    flash("Feedback provided successfully.")
    return redirect(url_for('notifications'))

@app.route('/qr-code/<data>')
def generate_qr(data):
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    img_bytes = buf.getvalue()
    img_b64 = base64.b64encode(img_bytes).decode('utf-8')

    return jsonify({"qr_code": img_b64})

@app.route('/scan-qr', methods=['POST'])
def scan_qr():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    file = request.files['qr_code']
    np_img = np.fromstring(file.read(), np.uint8)
    img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)
    barcodes = decode(img)
    results = []

    for barcode in barcodes:
        barcode_data = barcode.data.decode('utf-8')
        results.append(barcode_data)

    return jsonify({"results": results})

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    student_id = request.form['student_id']
    course_id = request.form['course_id']
    attendance_date = request.form['date']
    present = int(request.form['present'])
    mark = float(request.form['mark'])

    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO attendance (student_id, course_id, attendance_date, present, mark) VALUES (%s, %s, %s, %s, %s)",
                (student_id, course_id, attendance_date, present, mark))
    mysql.connection.commit()
    cur.close()

    flash("Attendance marked successfully.")
    return redirect(url_for('lecturer_dashboard'))

@app.route('/view_attendance/<int:course_id>')
def view_attendance(course_id):
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    cur = mysql.connection.cursor() 
    cur.execute("""
        SELECT a.*, u.email AS student_email
        FROM attendance a
        JOIN usersss u ON a.student_id = u.id
        WHERE a.course_id = %s
    """, [course_id])
    attendance_records = cur.fetchall()
    cur.close()
                       
    return render_template('view_attendance.html', attendance_records=attendance_records)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))