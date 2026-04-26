-- MRO Agent — user table for phone-based login
-- Apply with: mysql -h 39.107.14.53 -P 3307 -u USER -p d_mymro_sample < 001_create_users.sql

CREATE TABLE IF NOT EXISTS t_user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    nickname VARCHAR(50),
    auth_token VARCHAR(64) NOT NULL,
    session_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_phone (phone),
    UNIQUE KEY uk_token (auth_token)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- For tables that already exist (idempotent ALTER):
-- ALTER TABLE t_user ADD COLUMN session_count INT NOT NULL DEFAULT 0 AFTER auth_token;
