#!/usr/bin/env python

from flask import Flask
from websockets.asyncio.client import connect

app = Flask(__name__)


@app.route("/")
async def hello_world():

    async with connect("ws://websocket-server:8000/ws") as ws:
        await ws.send("hello uwu!")

    return "<p>Hello, World!</p>"
