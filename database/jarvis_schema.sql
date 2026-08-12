-- Complete database schema

CREATE TABLE memory (
    id INT PRIMARY KEY,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE patterns (
    id INT PRIMARY KEY,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE predictions (
    id INT PRIMARY KEY,
    pattern_id INT,
    prediction TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pattern_id) REFERENCES patterns(id)
);

CREATE TABLE plans (
    id INT PRIMARY KEY,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE device_actions (
    id INT PRIMARY KEY,
    action VARCHAR(255),
    device_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);