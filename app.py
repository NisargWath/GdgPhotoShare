from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
        event_data = {
            'name': request.form['name'],
            'description': request.form['description'],
            'event_type': request.form['event_type'],
            'date': request.form['date'],
            'created_at': datetime.now().isoformat(),
            'created_by': request.form['created_by']
        }
        
        events[event_id] = event_data
        save_data(events, photos)
        
        flash(f'Event "{event_data["name"]}" created successfully!', 'success')
        return redirect(url_for('event_gallery', event_id=event_id))
    
    return render_template('create_event.html')

@app.route('/event/<event_id>')
def event_gallery(event_id):
    events, photos = load_data()
    
    if event_id not in events:
        flash('Event not found!', 'error')
        return redirect(url_for('index'))
    
    event = events[event_id]
    event_photos = [p for p in photos.values() if p['event_id'] == event_id]
    event_photos.sort(key=lambda x: x['uploaded_at'], reverse=True)
    
    return render_template('event_gallery.html', event=event, photos=event_photos, event_id=event_id)

@app.route('/upload/<event_id>', methods=['POST'])
def upload_photo(event_id):
    events, photos = load_data()
    
    if event_id not in events:
        return jsonify({'error': 'Event not found'}), 404
    
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

if __name__ == "__main__":
    app.run(debug=True)

