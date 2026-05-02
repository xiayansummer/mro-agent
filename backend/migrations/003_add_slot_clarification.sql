-- MRO Agent — add slot_clarification JSON column to chat_message
-- Apply with: mysql -h 39.107.14.53 -P 3307 -u root -p d_mymro_sample < 003_add_slot_clarification.sql

ALTER TABLE t_chat_message
ADD COLUMN slot_clarification JSON NULL
AFTER competitor_results;
