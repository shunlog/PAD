import uuid
import datetime

import psycopg

from db import get_db
from hashing import check_password, hash_password


async def register(username, password) -> None:
    '''Try to register. Raise ValueError if username exists.'''
    salt, password_hash = hash_password(password)

    conn = await get_db()
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                'INSERT INTO users (username, password_hash, salt) VALUES (%s, %s, %s)',
                (username, password_hash, salt)
            )
            await conn.commit()

        except psycopg.errors.UniqueViolation:
            raise ValueError("Username exists")


async def create_session(username, password) -> str:
    '''If credentials are correct, create a session token, store it and return it.'''
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            'SELECT id, password_hash, salt FROM users WHERE username=%s', (
                username,)
        )
        user = await cur.fetchone()

        if not user:
            raise ValueError("Invalid username")

        id, password_hash, salt = user
        if not check_password(salt, password_hash, password):
            raise ValueError("Incorret password")

        # Generate a bearer token
        token = str(uuid.uuid4())
        expiration = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        await cur.execute(
            'INSERT INTO sessions (user_id, token, expires_at) VALUES (%s, %s, %s)',
            (user[0], token, expiration)
        )
        await conn.commit()
        return token


async def logout(token: str):
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute('DELETE FROM sessions WHERE token=%s', (token,))
        await conn.commit()


async def verify_token(token: str) -> bool:
    conn = await get_db()
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT EXISTS(SELECT 1 FROM sessions WHERE token = %s)", (token,))
        exists = (await cur.fetchone())[0]
        return exists
