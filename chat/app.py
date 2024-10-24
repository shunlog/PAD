import asyncio
from datetime import timedelta
import os

import grpc
from quart import Quart, render_template, websocket
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

broker = Broker()


@app.get("/")
async def index():
    return await render_template("index.html")


async def _receive() -> None:
    while True:
        message = await websocket.receive()
        await broker.publish(message)


@app.websocket("/ws")
async def ws() -> None:
    try:
        task = asyncio.ensure_future(_receive())
        async for message in broker.subscribe():
            await websocket.send(message)
    finally:
        task.cancel()
        await task


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
