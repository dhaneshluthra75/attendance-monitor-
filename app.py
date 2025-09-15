from flask import Flask, render_template, Response, redirect, url_for, request, flash, session, jsonify
import sqlite3
import cv2
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"
DATABASE = "attendance.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            dob TEXT,
            designation TEXT,
            year TEXT,
            course TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER,
            name TEXT,
            designation TEXT,
            year TEXT,
            course TEXT,
            date TEXT,
            time TEXT,
            FOREIGN KEY(person_id) REFERENCES people(id)
        )
    """)
    conn.commit()
    conn.close()

create_tables()

@app.route('/')
def splash():
    # Redirect splash immediately to menu instead of welcome
    return redirect(url_for('menu'))

@app.route('/welcome')
def welcome():
    # Keep welcome route if needed
    return render_template('welcome.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == 'admin123':  # Change password here
            session['logged_in'] = True
            return redirect(url_for('menu'))
        else:
            flash('Incorrect password.', 'danger')
    return render_template('login.html')

@app.route('/menu')
def menu():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('menu.html')

@app.route('/attendance')
def attendance():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('attendance.html')

def gen_camera():
    cap = cv2.VideoCapture(0)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    cap.release()

@app.route('/video_feed')
def video_feed():
    return Response(gen_camera(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    conn = get_db()
    person = conn.execute('SELECT * FROM people LIMIT 1').fetchone()
    now = datetime.now()
    if person:
        conn.execute("""
            INSERT INTO attendance (person_id, name, designation, year, course, date, time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            person['id'], person['name'], person['designation'], person['year'], person['course'],
            now.strftime('%Y-%m-%d'), now.strftime('%H:%M:%S')
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('attendance_status', person_name=person['name'], date=now.strftime('%Y-%m-%d'), time=now.strftime('%H:%M:%S'), status='Present'))
    conn.close()
    flash("No person found in DB.", "danger")
    return redirect(url_for('menu'))

@app.route('/attendance_status')
def attendance_status():
    person_name = request.args.get('person_name')
    date = request.args.get('date')
    time = request.args.get('time')
    status = request.args.get('status')
    photo_url = None
    return render_template('attendance_status.html', person_name=person_name, date=date, time=time, status=status, photo_url=photo_url)

@app.route('/attendance_log')
def attendance_log():
    conn = get_db()
    logs = conn.execute('SELECT * FROM attendance ORDER BY id DESC').fetchall()
    conn.close()
    logs = [dict(row) for row in logs]
    return render_template('attendance_log.html', logs=logs)

@app.route('/add_person', methods=['GET', 'POST'])
def add_person():
    if request.method == 'POST':
        name = request.form['name']
        dob = request.form.get('dob','')
        designation = request.form['designation']
        year = request.form.get('year','')
        course = request.form.get('course','')
        conn = get_db()
        conn.execute("""
            INSERT INTO people (name, dob, designation, year, course)
            VALUES (?, ?, ?, ?, ?)
        """, (name, dob, designation, year, course))
        conn.commit()
        conn.close()
        return redirect(url_for('capture_face', person_name=name))
    return render_template('add_person.html')

@app.route('/capture_face/<person_name>')
def capture_face(person_name):
    return render_template('capture_face.html', person_name=person_name)

@app.route('/capture_frame/<person_name>', methods=['POST'])
def capture_frame(person_name):
    return jsonify(success=True, message=f"Image captured for {person_name}")

@app.route('/new_person_success/<person_name>')
def new_person_success(person_name):
    return render_template('new_person_success.html', person_name=person_name)

@app.route('/manage_data', methods=['GET', 'POST'])
def manage_data():
    admin_access = session.get('admin', False)
    if request.method == 'POST' and not admin_access:
        if request.form.get('password') == 'admin123':
            session['admin'] = True
            admin_access = True
        else:
            flash('Wrong admin password', 'danger')
    conn = get_db()
    people = conn.execute('SELECT * FROM people').fetchall()
    conn.close()
    return render_template('manage_data.html', admin_access=admin_access, people=people)

@app.route('/delete_selected', methods=['POST'])
def delete_selected():
    ids = request.form.getlist('person_id')
    conn = get_db()
    for pid in ids:
        conn.execute('DELETE FROM people WHERE id=?', (pid,))
    conn.commit()
    conn.close()
    flash(f'{len(ids)} record(s) deleted.', 'success')
    return render_template('data_deleted.html')

@app.route('/data_deleted')
def data_deleted():
    return render_template('data_deleted.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/analytics_data')
def analytics_data():
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    conn = get_db()
    query = "SELECT name, COUNT(*) as present_count FROM attendance WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " GROUP BY name"
    people_query = "SELECT name FROM people"
    people = conn.execute(people_query).fetchall()
    present = conn.execute(query, params).fetchall()
    conn.close()
    data = []
    for p in people:
        pres = next((x['present_count'] for x in present if x['name'] == p['name']), 0)
        data.append({'name': p['name'], 'ratio': pres})
    return jsonify(data)

@app.errorhandler(404)
def page_not_found(e):
    flash('Page not found!', 'danger')
    return redirect(url_for('menu'))

if __name__ == '__main__':
    app.run(debug=True)
