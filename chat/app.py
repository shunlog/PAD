import asyncio
from datetime import timedelta
import os

import grpc
from quart import Quart, render_template, websocket, jsonify
from quart_rate_limiter import RateLimiter, RateLimit

import registry_pb2
import registry_pb2_grpc
from broker import Broker

app = Quart(__name__)
# Load environment variables starting with QUART_
# into the app config
app.config.from_prefixed_env()

rate_limiter = RateLimiter(app, default_limits=[
    RateLimit(3, timedelta(seconds=10))
])


@app.route('/status')
async def status_view():
    return jsonify({"status": "Alive"})


@app.get("/")
async def index():
    return await render_template("index.html")


# Store connected clients by chatroom
connected_clients = {}


async def listen_for_messages():
    async with psycopg.AsyncConnection.connect("dbname=yourdb user=youruser password=yourpass") as conn:
        async with conn.cursor() as cur:
            await cur.execute("LISTEN chat_messages;")
            print("Listening for new messages...")

            while True:
                await conn.wait(notify=True)
                async for notify in conn.notifies():
                    print("Received notification:", notify.payload)
                    # Broadcast to clients in the relevant chatroom
                    # Extract chatroom_id from the payload
                    chatroom_id = notify.payload.split()[-1]
                    await broadcast_to_clients(chatroom_id, notify.payload)


async def broadcast_to_clients(chatroom_id, message):
    if chatroom_id in connected_clients:
        for client in connected_clients[chatroom_id]:
            await client.send(message)


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
        # Remove the client from the set on disconnect
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
        task.result()  # Will raise any exceptions that happened in the task
    except Exception as e:
        print(f"Error in async task: {e}")


@app.before_serving
async def startup_RPC_task():
    hostname = os.getenv('HOSTNAME', '0.0.0.0')
    service_name = os.getenv('SERVICE_NAME')
    port = int(os.getenv('PORT', 5000))

    loop = asyncio.get_event_loop()
    app.register_task = loop.create_task(register_service(
        service_name, f"{hostname}:{port}"))

    app.register_task.add_done_callback(task_done_callback)
    print("Registered RPC task")


@app.after_serving
async def shutdown_RPC_task():
    app.register_task.cancel()
    print("Shut down RPC task")
