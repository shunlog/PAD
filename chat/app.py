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
