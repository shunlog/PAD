import asyncio

import click
from quart import Quart, request, jsonify

from db import get_db
from auth import register, create_session, logout, verify_token


app = Quart(__name__)
SECRET_KEY = "your_secret_key"


async def _init_db():
    sql_file = app.root_path + "/schema.sql"
    conn = await get_db()
    with open(sql_file, mode="r") as file:
        async with conn.cursor() as cur:
            await cur.execute(file.read())
            await conn.commit()


@app.cli.command()
def cli_init_db():
    click.echo('Recreating database tables.')
    asyncio.get_event_loop().run_until_complete(_init_db())


@app.route('/register', methods=['POST'])
async def register_view():
    data = await request.get_json()
    username = data['username']
    password = data['password']

    try:
        await register(username, password)
    except ValueError:
        return jsonify({"error": "Username already exists"}), 400

    return jsonify({"message": "User registered successfully"}), 201


@app.route('/login', methods=['POST'])
async def login():
    data = await request.get_json()
    username = data['username']
    password = data['password']

    try:
        token = await create_session(username, password)
    except ValueError:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"token": token})


@app.route('/logout', methods=['POST'])
async def logout_view():
    token = request.headers.get('Authorization').split()[1]
    await logout(token)
    return jsonify({"message": "Logged out"}), 200


@app.route('/verify', methods=['GET'])
async def verify_view():
    token = request.headers.get('Authorization').split()[1]

    exists = await verify_token(token)
    if not exists:
        return jsonify({"message": "Invalid token"}), 401

    return jsonify({"message": "Token is valid"}), 200


@app.before_serving
async def startup():
    # either init db from here,
    # or for persistency call this func from CLI
    await _init_db()

if __name__ == "__main__":
    app.run()
