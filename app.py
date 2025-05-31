from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('data', exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Simple in-memory storage (replace with database in production)
EVENTS_FILE = 'data/events.json'
PHOTOS_FILE = 'data/photos.json'

def load_data():
    events = {}
    photos = {}
    
    if os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'r') as f:
            events = json.load(f)
    
    if os.path.exists(PHOTOS_FILE):
        with open(PHOTOS_FILE, 'r') as f:
            photos = json.load(f)
    
    return events, photos

def save_data(events, photos):
    with open(EVENTS_FILE, 'w') as f:
        json.dump(events, f, indent=2)
    
    with open(PHOTOS_FILE, 'w') as f:
        json.dump(photos, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_access_key():
    """Generate a simple 6-character access key"""
    import random
    import string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def is_authenticated(event_id):
    """Check if user is authenticated for this event"""
    return session.get(f'auth_{event_id}', False)

@app.route('/')
def index():
    events, photos = load_data()
    
    # Get recent events with photo counts
    event_list = []
    for event_id, event in events.items():
        event_photos = [p for p in photos.values() if p['event_id'] == event_id]
        event['photo_count'] = len(event_photos)
        event['id'] = event_id
        event_list.append(event)
    
    # Sort by creation date (most recent first)
    event_list.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template('index.html', events=event_list)

@app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    if request.method == 'POST':
        events, photos = load_data()
        
        event_id = str(uuid.uuid4())
        access_key = generate_access_key()
        
        event_data = {
            'name': request.form['name'],
            'description': request.form['description'],
            'event_type': request.form['event_type'],
            'date': request.form['date'],
            'created_at': datetime.now().isoformat(),
            'created_by': request.form['created_by'],
            'access_key': access_key
        }
        
        events[event_id] = event_data
        save_data(events, photos)
        
        # Auto-authenticate the creator
        session[f'auth_{event_id}'] = True
        
        flash(f'Event "{event_data["name"]}" created successfully! Access Key: {access_key}', 'success')
        return redirect(url_for('event_gallery', event_id=event_id))
    
    return render_template('create_event.html')

@app.route('/event/<event_id>')
def event_gallery(event_id):
    events, photos = load_data()
    
    if event_id not in events:
        flash('Event not found!', 'error')
        return redirect(url_for('index'))
    
    # Check if user is authenticated
    if not is_authenticated(event_id):
        return redirect(url_for('authenticate', event_id=event_id))
    
    event = events[event_id]
    event_photos = [p for p in photos.values() if p['event_id'] == event_id]
    event_photos.sort(key=lambda x: x['uploaded_at'], reverse=True)
    
    return render_template('event_gallery.html', event=event, photos=event_photos, event_id=event_id)

@app.route('/auth/<event_id>', methods=['GET', 'POST'])
def authenticate(event_id):
    events, photos = load_data()
    
    if event_id not in events:
        flash('Event not found!', 'error')
        return redirect(url_for('index'))
    
    event = events[event_id]
    
    if request.method == 'POST':
        entered_key = request.form['access_key'].strip().upper()
        if entered_key == event['access_key']:
            session[f'auth_{event_id}'] = True
            flash('Access granted!', 'success')
            return redirect(url_for('event_gallery', event_id=event_id))
        else:
            flash('Invalid access key!', 'error')
    
    return render_template('authenticate.html', event=event, event_id=event_id)

@app.route('/upload/<event_id>', methods=['POST'])
def upload_photo(event_id):
    events, photos = load_data()
    
    if event_id not in events:
        return jsonify({'error': 'Event not found'}), 404
    
    # Check authentication
    if not is_authenticated(event_id):
        return jsonify({'error': 'Authentication required'}), 401
    
    if 'photos' not in request.files:
        return jsonify({'error': 'No files selected'}), 400
    
    files = request.files.getlist('photos')
    uploaded_count = 0
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            photo_id = str(uuid.uuid4())
            photo_data = {
                'filename': unique_filename,
                'original_name': filename,
                'event_id': event_id,
                'uploaded_at': datetime.now().isoformat(),
                'uploaded_by': request.form.get('uploaded_by', 'Anonymous')
            }
            
            photos[photo_id] = photo_data
            uploaded_count += 1
    
    save_data(events, photos)
    
    if uploaded_count > 0:
        return jsonify({'success': f'{uploaded_count} photos uploaded successfully!'})
    else:
        return jsonify({'error': 'No valid photos were uploaded'}), 400

@app.route('/delete_photo/<photo_id>')
def delete_photo(photo_id):
    events, photos = load_data()
    
    if photo_id in photos:
        photo = photos[photo_id]
        event_id = photo['event_id']
        
        # Check authentication
        if not is_authenticated(event_id):
            flash('Authentication required!', 'error')
            return redirect(url_for('authenticate', event_id=event_id))
        
        # Delete file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], photo['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Remove from data
        del photos[photo_id]
        save_data(events, photos)
        
        flash('Photo deleted successfully!', 'success')
        return redirect(url_for('event_gallery', event_id=event_id))
    
    flash('Photo not found!', 'error')
    return redirect(url_for('index'))

@app.route('/logout/<event_id>')
def logout(event_id):
    session.pop(f'auth_{event_id}', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)