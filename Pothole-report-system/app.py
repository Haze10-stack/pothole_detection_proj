from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import NoCredentialsError
import uuid
from datetime import datetime
import os
from functools import wraps
import json
from dotenv import load_dotenv

# ✅ Load environment variables before using them
load_dotenv()

import pymysql
pymysql.install_as_MySQLdb()

# Debug print (optional)
print("DB URI:", f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
AWS_REGION = os.getenv('AWS_REGION')

# Initialize extensions
db = SQLAlchemy(app)
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# Database Models
class CustomUser(db.Model):
    __tablename__ = 'custom_user'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone_number = db.Column(db.String(15))
    password_hash = db.Column(db.String(255), nullable=False)
    credits = db.Column(db.Integer, default=0)
    is_staff = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    reports = db.relationship('PotholeReport', backref='user', lazy=True)

class PotholeReport(db.Model):
    __tablename__ = 'pothole_report'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('custom_user.user_id'), nullable=False)
    image_url = db.Column(db.String(500))  # S3 URL path
    s3_bucket_path = db.Column(db.String(300))  # S3 bucket path/key
    description = db.Column(db.Text)
    location_name = db.Column(db.String(200))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    severity = db.Column(db.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='severity_enum'), nullable=False)
    status = db.Column(db.Enum('PENDING', 'VERIFIED', 'REJECTED', 'IN_PROGRESS', 'COMPLETED', name='status_enum'), default='PENDING')
    credits_awarded = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    verification = db.relationship('MunicipalVerification', backref='report', uselist=False)

class MunicipalVerification(db.Model):
    __tablename__ = 'municipal_verification'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_id = db.Column(db.String(36), db.ForeignKey('pothole_report.report_id'), nullable=False)
    verified_by = db.Column(db.String(100))
    verification_status = db.Column(db.Enum('APPROVED', 'REJECTED', 'NEED_INFO', name='verification_status_enum'))
    verification_notes = db.Column(db.Text)
    verification_date = db.Column(db.DateTime, default=datetime.utcnow)
    estimated_repair_date = db.Column(db.Date)

# Helper Functions
def upload_to_s3(file, filename):
    """Upload file to S3 bucket"""
    try:
        s3_key = f"pothole-images/{filename}"
        s3_client.upload_fileobj(
            file,
            AWS_BUCKET_NAME,
            s3_key,
            ExtraArgs={
                'ContentType': 'image/jpeg',
                'ACL': 'public-read'
            }
        )
        s3_url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        return s3_url, s3_key
    except NoCredentialsError:
        return None, None

def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    """Decorator for routes that require staff privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = CustomUser.query.filter_by(user_id=session['user_id']).first()
        if not user or not user.is_staff:
            return jsonify({'error': 'Staff access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        
        # Check if user already exists
        if CustomUser.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if CustomUser.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Create new user
        user = CustomUser(
            username=data['username'],
            email=data['email'],
            phone_number=data.get('phone_number'),
            password_hash=generate_password_hash(data['password'])
        )
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'User registered successfully', 'user_id': user.user_id}), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        user = CustomUser.query.filter_by(username=data['username']).first()
        
        if user and check_password_hash(user.password_hash, data['password']):
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['is_staff'] = user.is_staff
            return jsonify({'message': 'Login successful', 'is_staff': user.is_staff}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = CustomUser.query.filter_by(user_id=session['user_id']).first()
    if user.is_staff:
        return render_template('municipal_dashboard.html')
    else:
        return render_template('user_dashboard.html')

@app.route('/report-pothole', methods=['GET', 'POST'])
@login_required
def report_pothole():
    if request.method == 'POST':
        # Handle file upload
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Generate unique filename
        filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
        
        # Upload to S3
        s3_url, s3_key = upload_to_s3(file, filename)
        if not s3_url:
            return jsonify({'error': 'Failed to upload image'}), 500
        
        # Create local image URL
        local_image_url = url_for('serve_image', s3_key=s3_key, _external=True)
        
        # Create report
        report = PotholeReport(
            user_id=session['user_id'],
            image_url=local_image_url,
            s3_bucket_path=s3_key,
            description=request.form.get('description'),
            location_name=request.form.get('location_name'),
            latitude=float(request.form.get('latitude')) if request.form.get('latitude') else None,
            longitude=float(request.form.get('longitude')) if request.form.get('longitude') else None,
            severity=request.form.get('severity')
        )
        
        db.session.add(report)
        
        # Award credits to user
        user = CustomUser.query.filter_by(user_id=session['user_id']).first()
        user.credits += 5
        
        db.session.commit()
        
        return jsonify({'message': 'Report submitted successfully', 'report_id': report.report_id}), 201
    
    return render_template('report_pothole.html')

@app.route('/api/my-reports')
@login_required
def my_reports():
    reports = PotholeReport.query.filter_by(user_id=session['user_id']).order_by(PotholeReport.created_at.desc()).all()
    
    reports_data = []
    for report in reports:
        reports_data.append({
            'report_id': report.report_id,
            'description': report.description,
            'location_name': report.location_name,
            'severity': report.severity,
            'status': report.status,
            'credits_awarded': report.credits_awarded,
            'created_at': report.created_at.strftime('%Y-%m-%d %H:%M'),
            'image_url': report.image_url
        })
    
    return jsonify(reports_data)

@app.route('/api/user-profile')
@login_required
def user_profile():
    user = CustomUser.query.filter_by(user_id=session['user_id']).first()
    return jsonify({
        'username': user.username,
        'email': user.email,
        'phone_number': user.phone_number,
        'credits': user.credits,
        'is_staff': user.is_staff
    })

# Municipal/Staff Routes
@app.route('/api/pending-reports')
@staff_required
def pending_reports():
    reports = PotholeReport.query.filter_by(status='PENDING').order_by(PotholeReport.created_at.desc()).all()
    
    reports_data = []
    for report in reports:
        reports_data.append({
            'report_id': report.report_id,
            'username': report.user.username,
            'description': report.description,
            'location_name': report.location_name,
            'severity': report.severity,
            'status': report.status,
            'created_at': report.created_at.strftime('%Y-%m-%d %H:%M'),
            'image_url': report.image_url,
            'latitude': report.latitude,
            'longitude': report.longitude
        })
    
    return jsonify(reports_data)

@app.route('/api/verify-report', methods=['POST'])
@staff_required
def verify_report():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        report = PotholeReport.query.filter_by(report_id=data['report_id']).first()
        
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        action_mapping = {
            'approve': 'APPROVED',
            'reject': 'REJECTED', 
            'need_info': 'NEED_INFO'
        }
        
        if data['action'] == 'approve':
            report.status = 'VERIFIED'
            user = CustomUser.query.filter_by(user_id=report.user_id).first()
            if user:
                user.credits += 10
        elif data['action'] == 'reject':
            report.status = 'REJECTED'
        elif data['action'] == 'need_info':
            report.status = 'PENDING'
        
        estimated_date = None
        if data.get('estimated_repair_date'):
            try:
                estimated_date = datetime.strptime(data['estimated_repair_date'], '%Y-%m-%d').date()
            except ValueError:
                pass
        
        verification = MunicipalVerification(
            report_id=report.report_id,
            verified_by=data.get('verified_by', session.get('username', 'Unknown')),
            verification_status=action_mapping.get(data['action'], 'APPROVED'),
            verification_notes=data.get('notes', ''),
            estimated_repair_date=estimated_date
        )
        
        db.session.add(verification)
        db.session.commit()
        
        return jsonify({'message': 'Report verification updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update report: {str(e)}'}), 500

@app.route('/api/update-progress', methods=['POST'])
@staff_required
def update_progress():
    data = request.get_json()
    report = PotholeReport.query.filter_by(report_id=data['report_id']).first()
    
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    
    report.status = data['status']
    
    # Award completion bonus
    if data['status'] == 'COMPLETED':
        user = CustomUser.query.filter_by(user_id=report.user_id).first()
        user.credits += 5
    
    db.session.commit()
    return jsonify({'message': 'Progress updated successfully'})

@app.route('/api/public-reports')
def public_reports():
    """Get verified reports for public view"""
    reports = PotholeReport.query.filter(PotholeReport.status.in_(['VERIFIED', 'IN_PROGRESS', 'COMPLETED'])).all()
    
    reports_data = []
    for report in reports:
        reports_data.append({
            'report_id': report.report_id,
            'description': report.description,
            'location_name': report.location_name,
            'severity': report.severity,
            'status': report.status,
            'created_at': report.created_at.strftime('%Y-%m-%d'),
            'latitude': report.latitude,
            'longitude': report.longitude
        })
    
    return jsonify(reports_data)

@app.route('/image/<path:s3_key>')
def serve_image(s3_key):
    """Generate presigned URL for S3 image"""
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': AWS_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=3600  # 1 hour
        )
        return redirect(url)
    except Exception as e:
        return jsonify({'error': 'Image not found'}), 404
    
@app.route('/municipal-register', methods=['GET', 'POST'])
def municipal_register():
    if request.method == 'POST':
        data = request.get_json()
        
        if CustomUser.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        if CustomUser.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        user = CustomUser(
            username=data['username'],
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            is_staff=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'Staff user registered successfully', 'user_id': user.user_id}), 201
    
    return render_template('municipal_register.html')

@app.route('/municipal-login', methods=['GET', 'POST'])
def municipal_login():
    if request.method == 'POST':
        data = request.get_json()
        user = CustomUser.query.filter_by(username=data['username']).first()

        if user and check_password_hash(user.password_hash, data['password']) and user.is_staff:
            session['user_id'] = user.user_id
            session['username'] = user.username
            session['is_staff'] = user.is_staff
            return jsonify({'message': 'Login successful', 'is_staff': user.is_staff}), 200
        
        return jsonify({'error': 'Invalid credentials or insufficient privileges'}), 401
    
    return render_template('municipal_login.html')

@app.route('/municipal-dashboard')
@staff_required
def municipal_dashboard():
    return render_template('municipal_dashboard.html')

@app.route('/api/all-reports')
@staff_required
def all_reports():
    reports = PotholeReport.query.order_by(PotholeReport.created_at.desc()).all()

    reports_data = []
    for report in reports:
        reports_data.append({
            'report_id': report.report_id,
            'username': report.user.username,
            'description': report.description,
            'location_name': report.location_name,
            'severity': report.severity,
            'status': report.status,
            'created_at': report.created_at.strftime('%Y-%m-%d %H:%M'),
            'image_url': report.image_url,
            'latitude': report.latitude,
            'longitude': report.longitude
        })

    return jsonify(reports_data)

@app.route('/create-staff-user', methods=['POST'])
def create_staff_user():
    data = request.get_json()

    if CustomUser.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = CustomUser(
        username=data['username'],
        email=data['email'],
        password_hash=generate_password_hash(data['password']),
        is_staff=True
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({'message': 'Staff user created successfully'}), 201


# Initialize database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)