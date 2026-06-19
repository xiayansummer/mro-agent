-- MRO Agent — 给聊天消息加"精炼结果"列,与 comparison_draft 平行,供回看历史时还原精炼结果卡片
-- Apply: mysql -h <host> -P <port> -u root -p <db> < 007_add_refined_offers_to_chat_message.sql
ALTER TABLE t_chat_message ADD COLUMN refined_offers JSON NULL;
