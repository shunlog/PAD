import os
import uuid
import datetime
import asyncio

import click
import psycopg
from quart import Quart, request, jsonify

from hashing import check_password, hash_password

app = Quart(__name__)
SECRET_KEY = "your_secret_key"


def read_password_file(filepath):
    with open(filepath, 'r') as file:
        return file.read().strip()


async def _get_db():
    user = os.getenv("POSTGRES_USER")
    db = os.getenv("POSTGRES_DB")
    pwd = read_password_file(os.getenv("POSTGRES_PASSWORD_FILE"))
    server = os.getenv("POSTGRES_SERVER")
    db_url = f"postgresql://{user}:{pwd}@{server}/{db}"
    return await psycopg.AsyncConnection.connect(db_url)


async def _init_db():
    conn = await _get_db()
    with open(app.root_path + "/schema.sql", mode="r") as file:
        async with conn.cursor() as cur:
            await cur.execute(file.read())
            await conn.commit()


@app.cli.command()
def init_db():
    click.echo('Recreating database tables.')
    result = asyncio.get_event_loop().run_until_complete(_init_db())


async def _register(username, password) -> bool:
    salt, password_hash = hash_password(password)

    conn = await _get_db()
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                'INSERT INTO users (username, password_hash, salt) VALUES (%s, %s, %s)',
                (username, password_hash, salt)
            )
            await conn.commit()
            return True
        except psycopg.errors.UniqueViolation:
            return False


@app.route('/register', methods=['POST'])
async def register():
    data = await request.get_json()
    username = data['username']
    password = data['password']

    ok = await _register(username, password)
    if not ok:
        return jsonify({"error": "Username already exists"}), 400

    return jsonify({"message": "User registered successfully"}), 201


@app.route('/login', methods=['POST'])
async def login():
    data = await request.get_json()
    username = data['username']
    password = data['password']

    conn = await _get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            'SELECT id, password_hash, salt FROM users WHERE username=%s', (
                username,)
        )
        user = await cur.fetchone()

        if not user:
            return jsonify({"error": "Invalid credentials"}), 401

        id, password_hash, salt = user
        if not check_password(salt, password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401

        # Generate a bearer token
        token = str(uuid.uuid4())
        expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        await cur.execute(
            'INSERT INTO sessions (user_id, token, expires_at) VALUES (%s, %s, %s)',
            (user[0], token, expiration)
        )
        await conn.commit()
        return jsonify({"token": token})


@app.route('/logout', methods=['POST'])
async def logout():
    token = request.headers.get('Authorization').split()[1]  # Bearer token

    conn = await _get_db()
    async with conn.cursor() as cur:
        await cur.execute('DELETE FROM sessions WHERE token=%s', (token,))
        await conn.commit()

    return jsonify({"message": "Logged out"}), 200


@app.before_serving
async def startup():
    # either init db from here,
    # or for persistency call this func from CLI
    await _init_db()

if __name__ == "__main__":
    app.run()
