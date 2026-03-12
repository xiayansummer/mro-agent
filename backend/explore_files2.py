import asyncio
from sqlalchemy import text
from app.db.mysql import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        # 各 file_type 的文件名样例
        for ft in ['301', '302', '303', '305']:
            r = await s.execute(text(
                f"SELECT origin_file_name, file_path FROM t_item_file_sample WHERE file_type = '{ft}' LIMIT 5"
            ))
            print(f"\n=== file_type={ft} 样例 ===")
            for row in r.fetchall():
                print(f"  {row[0]}")
                print(f"    {row[1]}")

        # 文件名前缀分布 (PT=产品, MH=技术, HT=合同, SS=?)
        r = await s.execute(text(
            "SELECT "
            "SUBSTRING_INDEX(origin_file_name, '_', 1) as prefix, "
            "COUNT(*) as cnt "
            "FROM t_item_file_sample "
            "GROUP BY prefix ORDER BY cnt DESC LIMIT 15"
        ))
        print("\n=== 文件名前缀分布 ===")
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}")

        # 看看技术资料类
        r = await s.execute(text(
            "SELECT t.item_code, t.origin_file_name, t.file_path, s.item_name "
            "FROM t_item_file_sample t "
            "JOIN t_item_sample s ON t.item_code = s.item_code "
            "WHERE t.origin_file_name LIKE '%技术%' OR t.origin_file_name LIKE '%说明%' OR t.origin_file_name LIKE '%规格%' "
            "LIMIT 10"
        ))
        print("\n=== 技术资料/说明书/规格文件 ===")
        for row in r.fetchall():
            print(f"  [{row[0]}] {row[3]}")
            print(f"    文件: {row[1]}")
            print(f"    URL: {row[2]}")

asyncio.run(main())
