DROP TABLE IF EXISTS users, messages;


CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL
);


CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    chatroom_id VARCHAR(255) NOT NULL,  
    user_id VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
