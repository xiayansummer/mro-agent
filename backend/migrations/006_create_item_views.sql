-- 006_create_item_views.sql
-- 商品 / 文件查询视图:聚合 10 个分片 + 把 brandId/category{n}Id 翻译成名称。
-- 背景:旧代码查的 t_item_sample / t_item_file_sample 在生产 ERP 库不存在,
--      真实数据在 t_item_info(_0~_9) / t_item_file(_0~_9),品牌品类是 ID,
--      需 join t_brand / t_category / t_file。
--
-- ⚠️ 重要:中文关键词 LIKE 不能在 v_item_info 的【外层】做。MySQL 对
--    UNION ALL derived table 在外层做中文 LIKE 会被优化器吞掉(恒返回 0,
--    与字节/collation 无关,已实测)。所以:
--      - v_item_info 仅用于【id 过滤 + 聚合】(品类推荐 / brand 聚类),不做中文 LIKE
--      - 需要中文关键词匹配的 search_skus 把 LIKE 下推到各分片 WHERE 内
--        (见 app/services/sku_search.py 的 _items_union)
--    过滤一律用 *_id 列(可下推到分片走索引),name 列只用于展示。

CREATE OR REPLACE VIEW v_item_info AS
SELECT i.itemCode AS item_code, i.itemName AS item_name, b.brandName AS brand_name,
       i.specificAtion AS specification, i.mfgSku AS mfg_sku,
       c1.categoryName AS l1_category_name, c2.categoryName AS l2_category_name,
       c3.categoryName AS l3_category_name, c4.categoryName AS l4_category_name,
       i.itemDesc AS attribute_details,
       i.brandId AS brand_id,
       i.category1Id AS l1_category_id, i.category2Id AS l2_category_id,
       i.category3Id AS l3_category_id, i.category4Id AS l4_category_id
FROM (
    SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info   WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_1 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_2 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_3 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_4 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_5 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_6 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_7 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_8 WHERE deleted = 0
    UNION ALL SELECT itemCode, itemName, brandId, specificAtion, mfgSku, category1Id, category2Id, category3Id, category4Id, itemDesc FROM t_item_info_9 WHERE deleted = 0
) i
LEFT JOIN t_brand    b  ON b.sid  = i.brandId
LEFT JOIN t_category c1 ON c1.sid = i.category1Id
LEFT JOIN t_category c2 ON c2.sid = i.category2Id
LEFT JOIN t_category c3 ON c3.sid = i.category3Id
LEFT JOIN t_category c4 ON c4.sid = i.category4Id;

CREATE OR REPLACE VIEW v_item_file AS
SELECT f.itemCode AS item_code, tf.originFileName AS origin_file_name,
       tf.path AS file_path, tf.fileType AS file_type, f.published AS is_published
FROM (
    SELECT itemCode, fileId, published FROM t_item_file   WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_1 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_2 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_3 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_4 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_5 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_6 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_7 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_8 WHERE deleted = 0
    UNION ALL SELECT itemCode, fileId, published FROM t_item_file_9 WHERE deleted = 0
) f
JOIN (
    SELECT sid, originFileName, path, fileType FROM t_file   WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_1 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_2 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_3 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_4 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_5 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_6 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_7 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_8 WHERE deleted = 0
    UNION ALL SELECT sid, originFileName, path, fileType FROM t_file_9 WHERE deleted = 0
) tf ON tf.sid = f.fileId;
