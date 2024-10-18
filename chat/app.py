import asyncio
from quart import Quart, render_template, websocket
from quart_rate_limiter import RateLimiter, RateLimit
from datetime import timedelta

from broker import Broker

app = Quart(__name__)
# Load environment variables starting with QUART_
# into the app config
app.config.from_prefixed_env()
print(app.config["RESPONSE_TIMEOUT"])
rate_limiter = RateLimiter(app, default_limits=[
    RateLimit(1, timedelta(seconds=1)),
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
    while True:
        print("Register service running")
        await asyncio.sleep(1)

    # async with grpc.aio.insecure_channel('localhost:50051') as channel:
    #     registry_stub = registry_pb2_grpc.ServiceRegistryStub(channel)

    #     service_info = registry_pb2.ServiceInfo(
    #         service_name=service_name,
    #         address=address
    #     )

    #     try:
    #         response = await registry_stub.RegisterService(service_info)
    #         if response.success:
    #             print(f"Service {service_name} registered successfully!")
    #         else:
    #             print(f"Service {service_name} registration failed.")
    #     except grpc.RpcError as e:
    #         print(f"RPC error: {e}")


@app.before_serving
async def startup():
    loop = asyncio.get_event_loop()

    app.register_task = loop.create_task(register_service(
        "example-python-service", "localhost:50052"))


@app.after_serving
async def shutdown():
    app.register_task.cancel()
