DROP TABLE IF EXISTS users, sessions, WAL;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash BYTEA NOT NULL,
    salt BYTEA NOT NULL
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);


CREATE TABLE WAL (
    transaction_id VARCHAR(100) PRIMARY KEY,
    query VARCHAR(200)
);
