import asyncio
from datetime import timedelta
import os
import traceback

import grpc
import click
from quart import Quart, request, jsonify, Response
from quart_rate_limiter import RateLimiter, RateLimit
from prometheus_client import generate_latest, Counter, Summary, CONTENT_TYPE_LATEST

import registry_pb2
import registry_pb2_grpc
from db import get_db
from prometheus_utils import inc_counter

from auth import register, create_session, logout, verify_token


# Service discovery
hostname = os.getenv('HOSTNAME', '0.0.0.0')
service_name = os.getenv('SERVICE_NAME')
port = int(os.getenv('PORT', 5000))


app = Quart(__name__)
SECRET_KEY = "your_secret_key"

# Load environment variables starting with QUART_
# into the app config
app.config.from_prefixed_env()

rate_limiter = RateLimiter(app, default_limits=[
    RateLimit(3, timedelta(seconds=10))
])


# Prometheus counter
req_counter = Counter('request_count', 'Number of HTTP requests handled')
req_time = Summary('request_latency_seconds', 'Request latency')


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


async def WAL_store(transaction_id, query):
    conn = await get_db()
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                "INSERT INTO WAL (transaction_id, query)\
                VALUES (%s, %s)", (transaction_id, query)
            )
            await conn.commit()
        except Exception as e:
            print(e)

    print(f'Stored query: {query}')


async def WAL_restore(transaction_id):
    conn = await get_db()
    async with conn.cursor() as cur:
        q = 'SELECT query FROM WAL WHERE transaction_id=%s'
        await cur.execute(q, (transaction_id,))
        query = (await cur.fetchone())[0]
    print(f'Restoring query: {query}')

    return query


@app.route('/delete/prepare', methods=['POST'])
async def delete_prepare_view():
    data = await request.get_json()
    transaction_id = data['transaction_id']
    username = data['username']
    fail_on_prepare = data['fail_on_prepare']

    if fail_on_prepare:
        await asyncio.sleep(5 * 1000)

    # TODO Need ClientCursor for mogrify
    # conn = await get_db()
    # async with conn.cursor() as cur:
    #     query = cur.mogrify('DELETE ', (username,)).decode("utf-8")
    query = f'DELETE FROM users WHERE username = \'{username}\''

    try:
        await WAL_store(transaction_id, query)
    except:
        return Response("Couldn't prepare", status=500)

    print(f'Transaction {transaction_id}: PREPARED (delete user {username})')
    return "Prepared"


@app.route('/delete/commit', methods=['POST'])
async def delete_commit_view():
    data = await request.get_json()
    transaction_id = data['transaction_id']

    query = await WAL_restore(transaction_id)
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(query)
    await conn.commit()

    print(f'Transaction {transaction_id}: COMMITED.')
    return "Commited"


# Prometheus endpoint
@app.route('/metrics')
async def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/status')
@inc_counter(req_counter)
@req_time.time()
async def status_view():
    return jsonify({"status": "Alive"})


@app.route('/register', methods=['POST'])
@inc_counter(req_counter)
@req_time.time()
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
@inc_counter(req_counter)
@req_time.time()
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
@inc_counter(req_counter)
@req_time.time()
async def logout_view():
    token = request.headers.get('Authorization').split()[1]
    await logout(token)
    return jsonify({"message": "Logged out"}), 200


@app.route('/verify', methods=['GET'])
@inc_counter(req_counter)
@req_time.time()
async def verify_view():
    token = request.headers.get('Authorization').split()[1]

    exists = await verify_token(token)
    if not exists:
        return jsonify({"message": "Invalid token"}), 401

    return jsonify({"message": "Token is valid"}), 200


async def register_service(service_name, address):

    async def send_info():
        with grpc.insecure_channel('service-registry:50051') as channel:
            registry_stub = registry_pb2_grpc.ServiceRegistryStub(channel)

            # Create the service info object
            service_info = registry_pb2.ServiceInfo(
                service_name=service_name,
                address=address
            )

            # Register the service with the registry
            try:
                response = registry_stub.RegisterService(service_info)
                if response.success:
                    print(f"Registered {service_name}")
                else:
                    print(f"Failed register")
            except grpc.RpcError as e:
                print(f"RPC error: {e}")

    while True:
        try:
            await send_info()
        except RuntimeError as e:
            print(e)
        await asyncio.sleep(15)


def task_done_callback(task):
    try:
        task.result()  # This will raise any exceptions that happened in the task
    except Exception as e:
        print(f"Error in async task: {e}")
        # Print the full traceback
        traceback.print_exc()


@app.before_serving
async def startup_RPC_task():
    loop = asyncio.get_event_loop()
    app.register_task = loop.create_task(register_service(
        service_name, f"{hostname}:{port}"))

    app.register_task.add_done_callback(task_done_callback)
    print("Registered RPC task")


@app.after_serving
async def shutdown_RPC_task():
    app.register_task.cancel()
    print("Shut down RPC task")


@app.before_serving
async def startup():
    # either init db from here,
    # or for persistency call this func from CLI
    await _init_db()
