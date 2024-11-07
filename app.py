from flask import Flask, render_template, url_for, redirect, request, flash, make_response, send_file, session
import io
import os
from xhtml2pdf import pisa
from PIL import Image
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static'
app.secret_key = 'your_secret_key'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

MONGO_URI = "mongodb://localhost:27017/"
client = MongoClient(MONGO_URI)
db = client['college']

students_collection = db['students']
results_collection = db['results']
faculty_collection = db['faculty']
user_collection = db['details']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    user = user_collection.find_one({"username": session.get('email')})
    if user:
        if user['user_type'] == 'admin':
            return render_template('home.html', user_type='admin')
        elif user['user_type'] == 'student':
            return render_template('home.html', user_type='student')
        else:
            return render_template('home.html', user_type='faculty')
    return render_template('home.html')

@app.route('/aboutus')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/submit_contact',methods=['POST'])
def submit_contact():
    return render_template('home.html')

@app.route('/student')
def student():
    students = list(students_collection.find())
    for student in students:
        student['_id'] = str(student['_id'])
    return render_template('student.html', students=students)

@app.route('/faculty_students')
def faculty_students():
    if 'logged_in' not in session or not session['logged_in'] or session.get('user_type') != 'faculty':
        return redirect(url_for('login'))
    
    faculty_id = session.get('faculty_id')
    faculty = faculty_collection.find_one({"faculty_id": faculty_id})
    
    if not faculty or 'subjects' not in faculty:
        return redirect(url_for('login'))

    faculty_subjects = {subject.strip() for subject in faculty['subjects'].split(',')}
    
    students = list(students_collection.find())
    student_results = list(results_collection.find())

    results_by_student = {}
    for result in student_results:
        student_id = result['student_id']
        if student_id not in results_by_student:
            results_by_student[student_id] = set()
        results_by_student[student_id].add(result['subject'])
    
    filtered_students = []
    for student in students:
        student_id = student['student_id']
        student_subjects = results_by_student.get(student_id, set())
        if student_subjects & faculty_subjects:
            filtered_students.append(student)

    return render_template('student.html', students=filtered_students, faculty_subjects=faculty_subjects)

@app.route('/faculty')
def faculty():
    faculties = list(faculty_collection.find())
    for faculty in faculties:
        faculty['_id'] = str(faculty['_id'])
    return render_template('faculty.html', faculties=faculties)

@app.route('/add_form')
def form():
    return render_template('form.html', student=None, results=[])

@app.route('/add_faculty_form')
def add_faculty_form():
    return render_template('add_faculty_form.html', faculty=None)

@app.route('/view')
def view():
    student_id = session.get('user_id')
    return redirect(url_for('results', student_id=student_id))

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/loginn', methods=['POST'])
def login_post():
    email = request.form['email']
    password = request.form['password']
    user = user_collection.find_one({"username": email, "password": password})
    if user:
        session['logged_in'] = True
        session['email'] = email
        session['user_type'] = user['user_type']
        session['user_id'] = str(user['user_id'])
        if user['user_type'] == 'admin':
            return redirect(url_for('home'))
        elif user['user_type'] == 'faculty':
            session['faculty_id'] = str(user['user_id'])
            return redirect(url_for('home'))
        elif user['user_type'] == 'student':
            session['student_id'] = str(user['user_id'])
            return redirect(url_for('home'))
    else:
        return redirect(url_for('login'))

@app.route('/faculty_profile')
def faculty_profile():
    if 'logged_in' not in session or not session['logged_in']:
        return redirect(url_for('login'))
    
    faculty_id = session.get('faculty_id')
    faculty = faculty_collection.find_one({"faculty_id":(faculty_id)})
    
    if not faculty:
        flash('Faculty not found!', 'danger')
        return redirect(url_for('login'))

    return render_template('faculty_profile.html', faculty=faculty)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('email', None)
    return redirect(url_for('home'))

@app.route('/submit', methods=['POST'])
def submit():
    name = request.form['InputName']
    student_id = request.form['Inputroll']
    branch = request.form['InputBranch']
    username = request.form['InputUser']
    password = request.form['InputPass']

    if students_collection.find_one({"student_id": student_id}):
        flash('Student ID already exists!', 'danger')
        return redirect(url_for('student'))

    student = {
        "name": name,
        "student_id": student_id,
        "branch": branch,
        "username": username,
        "password": password
    }
    students_collection.insert_one(student)

    user = {
        "username": username,
        "password": password,
        "user_type": "student",
        "user_id": student_id
    }
    user_collection.insert_one(user)

    subjects = request.form.getlist('subject[]')
    total_marks = request.form.getlist('total_marks[]')
    obtained_marks = request.form.getlist('obtained_marks[]')

    for subject, total, obtained in zip(subjects, total_marks, obtained_marks):
        result = {
            "student_id": student_id,
            "subject": subject,
            "total_marks": total,
            "obtained_marks": obtained
        }
        results_collection.insert_one(result)

    if 'photo' in request.files:
        photo_file = request.files['photo']
        if photo_file.filename != '':
            original_filename = secure_filename(photo_file.filename)
            extension = original_filename.rsplit('.', 1)[1].lower()
            new_filename = f"{secure_filename(student_id)}.{extension}"
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            photo_file.save(photo_path)
            
    flash('Student added successfully!', 'success')
    return redirect(url_for('student'))

@app.route('/submit_faculty', methods=['POST'])
def submit_faculty():
    name = request.form['InputName']
    faculty_id = request.form['InputFacultyID']
    department = request.form['InputDepartment']
    fusername = request.form['InputFUser']
    fpassword = request.form['InputFPass']
    subjects = request.form['InputSubjects']

    if faculty_collection.find_one({"faculty_id": faculty_id}):
        flash('Faculty ID already exists!', 'danger')
        return redirect(url_for('faculty'))

    faculty = {
        "name": name,
        "faculty_id": faculty_id,
        "department": department,
        "username": fusername,
        "password": fpassword,
        "subjects": subjects
    }
    faculty_collection.insert_one(faculty)

    user = {
        "username": fusername,
        "password": fpassword,
        "user_type": "faculty",
        "user_id": faculty_id
    }
    user_collection.insert_one(user)

    if 'photo' in request.files:
        photo_file = request.files['photo']
        if photo_file.filename != '':
            original_filename = secure_filename(photo_file.filename)
            extension = original_filename.rsplit('.', 1)[1].lower()
            new_filename = f"{secure_filename(faculty_id)}.{extension}"
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            photo_file.save(photo_path)

    flash('Faculty added successfully!', 'success')
    return redirect(url_for('faculty'))

@app.route('/results/<student_id>')
def results(student_id):
    student = students_collection.find_one({"student_id": student_id})
    user_type = session.get('user_type')
    user_id = session.get('user_id')
    if user_type == 'student' and user_id != student_id:
        flash('please login first!')
        return redirect(url_for('login'))

    if not student:
        return "Student not found", 404

    student_results = list(results_collection.find({"student_id": student_id}))

    passorfail = 'PASS'
    for result in student_results:
        obtained_marks = int(result['obtained_marks'])
        total_marks = int(result['total_marks'])
        if obtained_marks < total_marks * 0.4:
            passorfail = 'FAIL'
            break 

    faculty_subjects = []
    if 'logged_in' in session and session['logged_in'] and session.get('user_type') == 'faculty':
        faculty_id = session.get('faculty_id')
        faculty = faculty_collection.find_one({"faculty_id": faculty_id})
        if faculty and 'subjects' in faculty: 
            faculty_subjects = faculty['subjects'].split(',')

    return render_template('results.html', student=student, results=student_results, passorfail=passorfail,faculty_subjects=faculty_subjects)

from flask import request, redirect, url_for

@app.route('/edit_result/<student_id>', methods=['POST'])
def edit_result(student_id):
    if request.method == 'POST':
        subjects = request.form.getlist('subject[]')
        total_marks = request.form.getlist('total_marks[]')
        obtained_marks = request.form.getlist('obtained_marks[]')

        # Delete subjects not present in the form
        existing_subjects = set(subjects)
        results_collection.delete_many({"student_id": student_id, "subject": {"$nin": list(existing_subjects)}})

        # Update or insert results in MongoDB
        for i in range(len(subjects)):
            subject = subjects[i]
            total = total_marks[i]
            obtained = obtained_marks[i]
            
            result = results_collection.find_one({"student_id": student_id, "subject": subject})
            if result:
                results_collection.update_one({"_id": result["_id"]}, {"$set": {"total_marks": total, "obtained_marks": obtained}})
            else:
                results_collection.insert_one({"student_id": student_id, "subject": subject, "total_marks": total, "obtained_marks": obtained})

        flash('result edited successfully!', 'success')
        return redirect(url_for('student'))

    return "Method not allowed", 405

@app.route('/student/<student_id>/<int:width>x<int:height>')
def generate_image(student_id, width, height):
    filename = None
    extensions = ['jpg', 'jpeg', 'png', 'gif']
    for ext in extensions:
        possible_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{student_id}.{ext}")
        if os.path.exists(possible_image_path):
            filename = possible_image_path
            break

    if filename:
        img = Image.open(filename)
        img_resized = img.resize((width, height))
        img_io = io.BytesIO()
        img_resized.save(img_io, format=img.format)
        img_io.seek(0)
        return send_file(img_io, mimetype=f'image/{img.format.lower()}')
    else:
        return "Image not found", 404

@app.route('/faculty/<faculty_id>/<int:width>x<int:height>')
def generateimage(faculty_id, width, height):
    filename = None
    extensions = ['jpg', 'jpeg', 'png', 'gif']
    for ext in extensions:
        possible_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{faculty_id}.{ext}")
        if os.path.exists(possible_image_path):
            filename = possible_image_path
            break

    if filename:
        img = Image.open(filename)
        img_resized = img.resize((width, height))
        img_io = io.BytesIO()
        img_resized.save(img_io, format=img.format)
        img_io.seek(0)
        return send_file(img_io, mimetype=f'image/{img.format.lower()}')
    else:
        return "Image not found", 404
    
def convert_html_to_pdf(html_string):
    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.BytesIO(html_string.encode("UTF-8")), dest=result)
    return result.getvalue()

@app.route('/edit_student/<student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    # Find the student record from the database
    student = students_collection.find_one({"student_id": student_id})

    # Handle POST request when the form is submitted
    if request.method == 'POST':
        try:
            print(request.form)
            # Retrieve form data
            name = request.form['name']
            branch = request.form['branch']
            username = request.form['username']
            password = request.form['password']

            # Update student record in the database
            students_collection.update_one(
                {"student_id": student_id},
                {"$set": {
                    "name": name,
                    "branch": branch,
                    "username": username,
                    "password": password
                }}
            )

            user_collection.update_one(
                {"user_id": student_id},
                {"$set": {
                    "username": username,
                    "password": password
                }}
            )
            return redirect(url_for('student'))
        except KeyError as e:
            # Handle missing form field error
            return redirect(url_for('edit_student', student_id=student_id))

    # Render the edit student form
    return render_template('edit_student.html', student=student)

@app.route('/edit_faculty/<faculty_id>', methods=['GET', 'POST'])
def edit_faculty(faculty_id):
    # Find the student record from the database
    faculty = faculty_collection.find_one({"faculty_id": faculty_id})

    # Handle POST request when the form is submitted
    if request.method == 'POST':
        try:
            # Retrieve form data
            name = request.form['name']
            department = request.form['department']
            username = request.form['username']
            password = request.form['password']
            subjects = request.form['subjects']

            # Update student record in the database
            faculty_collection.update_one(
                {"faculty_id": faculty_id},
                {"$set": {
                    "name": name,
                    "department": department,
                    "username": username,
                    "password": password,
                    "subjects": subjects
                }}
            )

            user_collection.update_one(
                {"user_id": faculty_id},
                {"$set": {
                    "username": username,
                    "password": password
                }}
            )
            return redirect(url_for('faculty'))
        except KeyError as e:
            # Handle missing form field error
            return redirect(url_for('edit_faculty', faculty_id=faculty_id))

    # Render the edit student form
    return render_template('edit_faculty.html', faculty=faculty)

@app.route('/delete_student/<student_id>', methods=['POST'])
def delete_student(student_id):
    
    students_collection.delete_one({"student_id": student_id})
    
    results_collection.delete_many({"student_id": student_id})
    
    user_collection.delete_one({"user_id": student_id, "user_type": "student"})
    
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('student'))

@app.route('/delete_faculty/<faculty_id>', methods=['POST'])
def delete_faculty(faculty_id):
    # Delete student record from the database
    faculty_collection.delete_one({"faculty_id": faculty_id})
    # Optionally, delete associated user record
    user_collection.delete_one({"user_id": faculty_id, "user_type": "faculty"})
    
    flash('Faculty deleted successfully!', 'success')
    return redirect(url_for('faculty'))

@app.route('/student/results/download/<student_id>')
def download_pdf(student_id):
    results = []
    student_name = ''
    batch = ''
    passorfail = '-'

    # Query MongoDB for student details
    student = students_collection.find_one({"student_id": student_id})
    if student:
        student_name = student.get('name', '')
        batch = student.get('batch', '')

    # Query MongoDB for results
    student_results = results_collection.find({"student_id": student_id})
    for result in student_results:
        results.append(result)

    # Determine pass or fail based on results
    for result in results:
        if int(result.get('obtained_marks', 0)) < 35:
            passorfail = 'FAIL'
            break
        else:
            passorfail = 'PASS'

    rendered = render_template('resultpdf_student.html', student_name=student_name, student_id=student_id, results=results, batch=batch, passorfail=passorfail,student=student)

    pdf = convert_html_to_pdf(rendered)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=results_{student_id}.pdf'

    return response

if __name__ == "__main__":
    app.run(debug=True)