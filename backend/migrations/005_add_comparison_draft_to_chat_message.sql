-- MRO Agent — persist comparison draft cards in chat history
-- Apply with: mysql -h <host> -P <port> -u <user> -p <database> < 005_add_comparison_draft_to_chat_message.sql

ALTER TABLE t_chat_message
ADD COLUMN comparison_draft JSON NULL
AFTER slot_clarification;
