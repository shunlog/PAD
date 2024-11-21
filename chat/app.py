import asyncio
from datetime import timedelta
import os
import traceback

import grpc
from quart import Quart, render_template, websocket, jsonify, Response
from quart_rate_limiter import RateLimiter, RateLimit
import psycopg
from prometheus_client import generate_latest, Counter, Summary, CONTENT_TYPE_LATEST

import registry_pb2
import registry_pb2_grpc
from db import get_db
from prometheus_utils import inc_counter


# Service discovery
hostname = os.getenv('HOSTNAME', '0.0.0.0')
service_name = os.getenv('SERVICE_NAME')
port = int(os.getenv('PORT', 5000))


app = Quart(__name__)
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


# Prometheus endpoint
@app.route('/metrics')
async def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/status')
@inc_counter(req_counter)
@req_time.time()
async def status_view():
    return jsonify({"status": "Alive"})


@app.get("/")
@inc_counter(req_counter)
@req_time.time()
async def index():
    return await render_template("index.html", hostname=hostname, port=port)


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
        print("Listening for new messages...")

        while True:
            # await conn.wait(notify=True)
            async for notify in conn.notifies():
                print("Received notification:", notify.payload)
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

        print("Inserted message")
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
async def startup_messages_listen():
    loop = asyncio.get_event_loop()
    app.listen_task = loop.create_task(listen_for_messages())
    app.listen_task.add_done_callback(task_done_callback)


@app.before_serving
async def startup():
    # either init db from here,
    # or for persistency call this func from CLI
    await _init_db()
