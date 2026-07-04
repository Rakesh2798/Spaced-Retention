from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import sqlite3
import hashlib
import secrets
import json
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Database setup
DB_PATH = Path(__file__).resolve().parent / "tracker_users.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracker_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, key),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_user ON tracker_data(user_id)")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_api_key():
    return secrets.token_urlsafe(32)

# Initialize database
init_db()

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    password_hash = hash_password(password)
    api_key = generate_api_key()
    created_at = datetime.utcnow().isoformat()
    
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, api_key, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, api_key, created_at)
            )
        return jsonify({'api_key': api_key, 'username': username}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    password_hash = hash_password(password)
    
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, api_key FROM users WHERE username = ? AND password_hash = ?",
            (username, password_hash)
        ).fetchone()
    
    if user:
        return jsonify({'api_key': user['api_key'], 'username': username}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

def verify_api_key():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return None
    
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE api_key = ?", (api_key,)).fetchone()
    
    return user['id'] if user else None

@app.route('/api/data', methods=['GET'])
def get_data():
    user_id = verify_api_key()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM tracker_data WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    
    data = {row['key']: {'value': json.loads(row['value']), 'updated_at': row['updated_at']} for row in rows}
    return jsonify(data), 200

@app.route('/api/data', methods=['POST'])
def save_data():
    user_id = verify_api_key()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    data = request.json
    updated_at = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        for key, value in data.items():
            conn.execute(
                """
                INSERT INTO tracker_data (user_id, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (user_id, key, json.dumps(value), updated_at)
            )
    
    return jsonify({'success': True, 'updated_at': updated_at}), 200

@app.route('/api/data/<key>', methods=['DELETE'])
def delete_data(key):
    user_id = verify_api_key()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401
    
    with get_db() as conn:
        conn.execute("DELETE FROM tracker_data WHERE user_id = ? AND key = ?", (user_id, key))
    
    return jsonify({'success': True}), 200

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
