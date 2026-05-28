-- MRO Agent — external platform comparison tables
-- Apply with: mysql -h <host> -P <port> -u <user> -p <database> < 004_create_comparison_tables.sql

CREATE TABLE IF NOT EXISTS comparison_drafts (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    chat_session_id VARCHAR(64),
    chat_message_id INT,
    raw_query TEXT NOT NULL,
    structure_json JSON NOT NULL,
    selected_platforms JSON NOT NULL,
    search_terms_json JSON NOT NULL,
    platform_status_json JSON,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_comparison_drafts_user_updated (user_id, updated_at DESC),
    INDEX idx_comparison_drafts_status (status),
    INDEX idx_comparison_drafts_chat_session (chat_session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS comparison_tasks (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    draft_id VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME NULL,
    INDEX idx_comparison_tasks_draft (draft_id),
    INDEX idx_comparison_tasks_user_created (user_id, created_at DESC),
    INDEX idx_comparison_tasks_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS comparison_subtasks (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    platform VARCHAR(16) NOT NULL,
    status VARCHAR(32) NOT NULL,
    search_terms_json JSON NOT NULL,
    items_json JSON,
    error_json JSON,
    leased_until DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_comparison_subtasks_task (task_id),
    INDEX idx_comparison_subtasks_status (status),
    INDEX idx_comparison_subtasks_platform_status (platform, status),
    INDEX idx_comparison_subtasks_lease (leased_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS extension_sessions (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    ext_token_hash VARCHAR(128) NOT NULL,
    device_name VARCHAR(120),
    browser VARCHAR(32) NOT NULL DEFAULT 'chrome',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    status_json JSON,
    last_seen_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_extension_sessions_user_active (user_id, active),
    INDEX idx_extension_sessions_last_seen (last_seen_at),
    UNIQUE KEY uk_extension_token_hash (ext_token_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS extension_pairing_codes (
    code_hash VARCHAR(128) NOT NULL PRIMARY KEY,
    user_id INT NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_extension_pairing_user_created (user_id, created_at DESC),
    INDEX idx_extension_pairing_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
