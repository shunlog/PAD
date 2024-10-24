import os

import psycopg


def read_password_file(filepath):
    with open(filepath, 'r') as file:
        return file.read().strip()


user = os.getenv("POSTGRES_USER")
db = os.getenv("POSTGRES_DB")
pwd = read_password_file(os.getenv("POSTGRES_PASSWORD_FILE"))
server = os.getenv("POSTGRES_SERVER")
db_url = f"postgresql://{user}:{pwd}@{server}/{db}"


async def get_db():
    return await psycopg.AsyncConnection.connect(db_url)
