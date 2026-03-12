import asyncio
from sqlalchemy import text
from app.db.mysql import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        # file_type 分布
        r = await s.execute(text("SELECT file_type, COUNT(*) FROM t_item_file_sample GROUP BY file_type"))
        print("=== file_type 分布 ===")
        for row in r.fetchall():
            print(row)

        # 文件名关键词分布
        r = await s.execute(text(
            "SELECT "
            "SUM(origin_file_name LIKE '%证书%') as cert, "
            "SUM(origin_file_name LIKE '%说明%') as manual_doc, "
            "SUM(origin_file_name LIKE '%规格%') as spec, "
            "SUM(origin_file_name LIKE '%参数%') as param_doc, "
            "SUM(origin_file_name LIKE '%检测%' OR origin_file_name LIKE '%检验%' OR origin_file_name LIKE '%报告%') as report, "
            "SUM(origin_file_name LIKE '%SDS%' OR origin_file_name LIKE '%MSDS%') as sds, "
            "SUM(origin_file_name LIKE '%.pdf') as pdf_count, "
            "SUM(origin_file_name LIKE '%.jpg' OR origin_file_name LIKE '%.png') as img_count "
            "FROM t_item_file_sample"
        ))
        row = r.fetchone()
        print(f"\n=== 文件名关键词分布 ===")
        print(f"证书: {row[0]}, 说明: {row[1]}, 规格: {row[2]}, 参数: {row[3]}, 检测/报告: {row[4]}, SDS: {row[5]}")
        print(f"PDF: {row[6]}, 图片: {row[7]}")

        # 一个item_code对应多少文件
        r = await s.execute(text("SELECT item_code, COUNT(*) c FROM t_item_file_sample GROUP BY item_code ORDER BY c DESC LIMIT 10"))
        print("\n=== item_code 文件数 TOP10 ===")
        for row in r.fetchall():
            print(row)

        # 有文件的SKU占比
        r = await s.execute(text("SELECT COUNT(DISTINCT item_code) FROM t_item_file_sample"))
        print(f"\n=== 有文件的SKU数: {r.scalar()} / 2000007 ===")

        # file_comment 有内容的
        r = await s.execute(text("SELECT COUNT(*) FROM t_item_file_sample WHERE file_comment IS NOT NULL AND file_comment != ''"))
        print(f"\n=== 有 file_comment 的记录数: {r.scalar()} ===")

        r = await s.execute(text("SELECT file_comment FROM t_item_file_sample WHERE file_comment IS NOT NULL AND file_comment != '' LIMIT 10"))
        print("=== file_comment 样例 ===")
        for row in r.fetchall():
            print(row)

        # 看看非证书类的文件
        r = await s.execute(text("SELECT origin_file_name, file_path FROM t_item_file_sample WHERE origin_file_name NOT LIKE '%证书%' LIMIT 20"))
        print("\n=== 非证书类文件样例 ===")
        for row in r.fetchall():
            print(row)

asyncio.run(main())
