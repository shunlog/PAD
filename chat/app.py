import asyncio
from datetime import timedelta
import os
import traceback
import uuid

import httpx
import grpc
from quart import (Quart, render_template, websocket, jsonify, Response, request,
                   url_for, send_from_directory)
from quart_rate_limiter import RateLimiter, RateLimit
import psycopg
from prometheus_client import generate_latest, Counter, Summary, CONTENT_TYPE_LATEST

import registry_pb2
import registry_pb2_grpc
from db import get_db
from prometheus_utils import inc_counter

# seconds, after which the transaction is aborted
PREPARE_PHASE_REQUEST_TIMEOUT = 3.0

# Service discovery
hostname = os.getenv('HOSTNAME', '0.0.0.0')
service_name = os.getenv('SERVICE_NAME')
port = int(os.getenv('PORT', 5000))
# TODO de-hardcode
gateway_addr = 'http://gateway:5000'


# set the static URL as it will appear in the HTML page (mind the gateway)
app = Quart(__name__, static_url_path=f'/{service_name}/static')
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


# The gateway strips the service-name from the URL,
# so we have to override the static folder path
@app.route('/static/<path:filename>')
async def custom_static(filename):
    return await send_from_directory('static', filename)


# Prometheus endpoint
@app.route('/metrics')
async def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/status')
@inc_counter(req_counter)
@req_time.time()
async def status_view():
    return jsonify({"status": "Alive"})


async def get_users_list():
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute('SELECT username FROM users')
        rows = await cur.fetchall()
    return [row[0] for row in rows]


@app.get("/")
@inc_counter(req_counter)
@req_time.time()
async def index():
    return await render_template("index.html", hostname=hostname, port=port,
                                 login_url=f'http://127.0.0.1:{port}/login',
                                 delete_url=f'http://127.0.0.1:{port}/delete',
                                 users=await get_users_list())


async def verify_user(username, password):
    async with httpx.AsyncClient() as client:
        response = await client.post(f'{gateway_addr}/users/login',
                                     json={'username': username, 'password': password})
    if response.status_code != httpx.codes.OK:
        return False

    return True


async def add_user_to_chatroom(username):
    conn = await get_db()
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                'INSERT INTO users (username) VALUES (%s)', (username,)
            )
            await conn.commit()

        except psycopg.errors.UniqueViolation:
            raise ValueError("Username exists")


async def delete_user(username):
    conn = await get_db()
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                "DELETE FROM users WHERE username = %s", (username,)
            )
            await conn.commit()

        except psycopg.errors.UniqueViolation:
            raise ValueError("Couldn't delete user")


@app.route('/login', methods=['POST'])
async def login_view():
    '''Adds a user to the database, and shows him in the table'''
    form_data = await request.form
    username = form_data.get('username')
    password = form_data.get('password')
    valid = await verify_user(username, password)
    if not valid:
        return Response("Invalid credentials", status=401)

    await add_user_to_chatroom(username)
    return "User logged in successfully"


async def delete_user_2PC(username, fail_on_prepare):
    '''Two-phase commit:
    1. Delete username from chat's users table
    2. Delete user record from the "users" service'''

    # Prepare phase
    transaction_id = str(uuid.uuid4())
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f'{gateway_addr}/users/delete/prepare',
            json={'transaction_id': transaction_id,
                  'username': username,
                  'fail_on_prepare': fail_on_prepare},
            timeout=PREPARE_PHASE_REQUEST_TIMEOUT)

    if response.status_code != httpx.codes.OK:
        return False
    # Pretend I sent a prepare request to this node as well

    # Commit phase
    print("Transaction: Prepare phase done")

    async with httpx.AsyncClient() as client:
        # Ensure no timeout
        response = await client.post(f'{gateway_addr}/users/delete/commit',
                                     json={'transaction_id': transaction_id},
                                     timeout=None)
    # We assume all responses are OK when requests succeeded

    # Pretend I sent a commit request to this node
    await delete_user(username)

    return True


@app.route('/delete', methods=['POST'])
async def delete_view():
    '''Delete user from the database'''
    form_data = await request.form
    username = form_data['username']
    fail_on_prepare = bool(form_data.get('fail_on_prepare'))
    ok = await delete_user_2PC(username, fail_on_prepare)
    if not ok:
        return Response("Couldn't delete user", status=500)
    return "User deleted successfully"


@app.get("/error")
@inc_counter(req_counter)
@req_time.time()
async def view_error():
    return Response("Simulating error", status=500)


@app.get("/sleep/<duration>")
@inc_counter(req_counter)
@req_time.time()
async def view_sleep(duration):
    '''Sleep for a given number of ms.
    Useful for testing timeouts.'''
    duration = int(duration)
    await asyncio.sleep(duration / 1000)
    return Response(f"Slept for {duration}ms.")


# Store connected clients by chatroom
connected_clients = {}


async def listen_for_messages():
    conn = await get_db()
    await conn.set_autocommit(True)
    async with conn.cursor() as cur:
        await cur.execute("LISTEN messages;")

        while True:
            # await conn.wait(notify=True)
            async for notify in conn.notifies():
                # Broadcast to clients in the relevant chatroom
                # Extract chatroom_id from the payload
                chatroom_id, message = notify.payload.split(',', 1)
                await broadcast_to_clients(chatroom_id, message)


async def broadcast_to_clients(chatroom_id, message):
    if chatroom_id in connected_clients:
        for client in connected_clients[chatroom_id]:
            await client.send(message)


async def insert_message(chatroom_id, user_id, content):
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            'INSERT INTO messages (chatroom_id, user_id, content) VALUES (%s, %s, %s)',
            (chatroom_id, user_id, content)
        )

        await cur.execute(
            f"NOTIFY messages, '{chatroom_id},{content}'"
        )

        await conn.commit()


@app.websocket('/chat/<chatroom_id>')
async def chat(chatroom_id):
    # Register the new client
    if chatroom_id not in connected_clients:
        connected_clients[chatroom_id] = set()

    # Add the client to the set
    client = websocket._get_current_object()
    connected_clients[chatroom_id].add(client)

    try:
        while True:
            # Handle incoming messages (if needed)
            data = await websocket.receive()
            # Optionally process incoming messages here
            # Example: Insert new messages into the database
            await insert_message(chatroom_id, "sender_id_placeholder", data)

    except Exception as e:
        print(f"Client disconnected: {e}")

    finally:
        connected_clients[chatroom_id].remove(client)


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
                if not response.success:
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


@app.after_serving
async def shutdown_RPC_task():
    app.register_task.cancel()


@app.before_serving
async def startup_messages_listen():
    loop = asyncio.get_event_loop()
    app.listen_task = loop.create_task(listen_for_messages())
    app.listen_task.add_done_callback(task_done_callback)


@app.before_serving
async def startup():
    # either init db from here,
    # or for persistency call this func from CLI
    await _init_db()
