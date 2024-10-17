#!/usr/bin/env python

import asyncio

import websockets
from websockets.asyncio.server import serve


async def handler(websocket):
    async for message in websocket:
        print(message)
        await websocket.send(message)


async def main():
    async with serve(handler, "", 8000):
        print("Listening")
        await asyncio.get_running_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
