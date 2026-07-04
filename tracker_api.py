from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import hashlib
import secrets
import json
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Allow your GitHub Pages site to securely send requests to this API
CORS(app, resources={r"/api/*": {"origins": "https://rakesh2798.github.io"}})

# Pull the Connection String directly from your Render Environment variables
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is missing!")
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Users Table
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS users
                           (
                               id
                               SERIAL
                               PRIMARY
                               KEY,
                               username
                               TEXT
                               UNIQUE
                               NOT
                               NULL,
                               password_hash
                               TEXT
                               NOT
                               NULL,
                               api_key
                               TEXT
                               UNIQUE
                               NOT
                               NULL,
                               created_at
                               TEXT
                               NOT
                               NULL
                           )
                           """)
            # Tracker Data Table (using standard Postgres constraint)
            cursor.execute("""
                           CREATE TABLE IF NOT EXISTS tracker_data
                           (
                               id
                               SERIAL
                               PRIMARY
                               KEY,
                               user_id
                               INTEGER
                               NOT
                               NULL
                               REFERENCES
                               users
                           (
                               id
                           ) ON DELETE CASCADE,
                               key TEXT NOT NULL,
                               value TEXT NOT NULL,
                               updated_at TEXT NOT NULL,
                               UNIQUE
                           (
                               user_id,
                               key
                           )
                               )
                           """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracker_user ON tracker_data(user_id)")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_api_key():
    return secrets.token_urlsafe(32)


# Initialize PostgreSQL database tables on start
init_db()


@app.route('/api/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    password_hash = hash_password(password)
    api_key = generate_api_key()
    created_at = datetime.utcnow().isoformat()

    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, api_key, created_at) VALUES (%s, %s, %s, %s)",
                    (username, password_hash, api_key, created_at)
                )
        return jsonify({'api_key': api_key, 'username': username}), 201
    except psycopg2.IntegrityError:
        return jsonify({'error': 'Username already exists'}), 409


@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    password_hash = hash_password(password)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, api_key FROM users WHERE username = %s AND password_hash = %s",
                (username, password_hash)
            )
            user = cursor.fetchone()

    if user:
        return jsonify({'api_key': user['api_key'], 'username': username}), 200
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


def verify_api_key():
    api_key = request.headers.get('X-API-Key')
    if not api_key:
        return None

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM users WHERE api_key = %s", (api_key,))
            user = cursor.fetchone()

    return user['id'] if user else None


@app.route('/api/data', methods=['GET'])
def get_data():
    user_id = verify_api_key()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT key, value, updated_at FROM tracker_data WHERE user_id = %s",
                (user_id,)
            )
            rows = cursor.fetchall()

    data = {row['key']: {'value': json.loads(row['value']), 'updated_at': row['updated_at']} for row in rows}
    return jsonify(data), 200


@app.route('/api/data', methods=['POST'])
def save_data():
    user_id = verify_api_key()
    if not user_id:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    data = request.json or {}
    updated_at = datetime.utcnow().isoformat()

    with get_db() as conn:
        with conn.cursor() as cursor:
            for key, value in data.items():
                # Postgres "ON CONFLICT" UPSERT format using excluded namespace
                cursor.execute(
                    """
                    INSERT INTO tracker_data (user_id, key, value, updated_at)
                    VALUES (%s, %s, %s, %s) ON CONFLICT(user_id, key) DO
                    UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
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
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM tracker_data WHERE user_id = %s AND key = %s", (user_id, key))

    return jsonify({'success': True}), 200


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)