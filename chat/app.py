import asyncio
from datetime import timedelta
import os
import traceback
import uuid

import httpx
import grpc
import click
from quart import (Quart, render_template, websocket, jsonify, Response, request,
                   url_for, send_from_directory)
from quart_rate_limiter import RateLimiter, RateLimit
import psycopg
from prometheus_client import generate_latest, Counter, Summary, CONTENT_TYPE_LATEST
import redis

import registry_pb2
import registry_pb2_grpc
from db import get_db
from prometheus_utils import inc_counter
from consistent_hashing import ConsistentHashRing

# seconds, after which the transaction is aborted
PREPARE_PHASE_REQUEST_TIMEOUT = 3.0

# number of last messages to keep in cache
NUM_LAST_MSG_CACHED = 3

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


ring = ConsistentHashRing(100)
ring["node1"] = redis.Redis(host=os.getenv('CACHE_HOSTNAME_1'), port=6379)
ring["node2"] = redis.Redis(host=os.getenv('CACHE_HOSTNAME_2'), port=6379)


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


# Add a new message
def cache_message(chat_id, content):
    r = ring[str(chat_id)]
    redis_host = r.connection_pool.get_connection('PING').host
    print(f"Cached on: {redis_host}")
    r.lpush(chat_id, content)  # Add the message to the list
    r.ltrim(chat_id, 0, NUM_LAST_MSG_CACHED-1)


async def insert_message(chatroom_id, user_id, content):
    cache_message(chatroom_id, content)

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


# Get the last 5 messages
def get_messages(chat_id):
    '''Retrieve last cached messages as a list'''
    r = ring[str(chat_id)]
    bl = r.lrange(chat_id, 0, -1)
    sl = [b.decode() for b in bl]
    return sl[::-1]


async def get_users_list():
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute('SELECT username FROM users')
        rows = await cur.fetchall()
    return [row[0] for row in rows]


@app.get("/chat/<chat_id>")
@inc_counter(req_counter)
@req_time.time()
async def index(chat_id):
    return await render_template("index.html", hostname=hostname, socket_port=port,
                                 messages=get_messages(chat_id),
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


async def register_user(username):
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


@app.route('/user', methods=['POST'])
async def user_register_view():
    '''Adds a user to the database, and shows him in the table'''
    form_data = await request.form
    username = form_data.get('username')
    await register_user(username)
    return "User registered successfully"


@app.route('/user/<username>', methods=['DELETE'])
async def delete_view(username):
    '''Delete user from the database'''
    try:
        await delete_user(username)
    except ValueError:
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


@app.websocket('/socket/chat/<chatroom_id>')
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

    try:
        await send_info()
    except RuntimeError as e:
        print("Couldn't connect to Service Registry.")
        print(e)


@app.route('/status')
@inc_counter(req_counter)
@req_time.time()
async def status_view():
    return jsonify({"status": "Alive"})


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
