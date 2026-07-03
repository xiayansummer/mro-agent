"""表格文件(.xlsx/.xls/.csv)统一读取为二维字符串数组。

原先 routers/inquiry.py 与 services/erp_importer.py 各写了一套 openpyxl/xlrd/csv
读取分支(上层列名映射各自不同,但底层"字节→原始行"重复)。收敛到这里一处;
顺带让 erp_importer 也获得 .xls(xlrd)支持。
"""
import csv
import io

import openpyxl
import xlrd


def read_sheet_rows(file_bytes: bytes, filename: str) -> list[list[str]]:
    """把上传的表格文件读成二维字符串数组(每格转字符串并 strip)。

    不支持的后缀抛 ValueError,由调用方转成 400。内容损坏时底层库抛异常,同样上抛。
    """
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        return [
            [str(cell).strip() if cell is not None else "" for cell in row]
            for row in ws.iter_rows(values_only=True)
        ]
    if name.endswith(".xls"):
        wb = xlrd.open_workbook(file_contents=file_bytes)
        ws = wb.sheet_by_index(0)
        return [
            [str(ws.cell_value(r, c)).strip() for c in range(ws.ncols)]
            for r in range(ws.nrows)
        ]
    if name.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        return [list(row) for row in csv.reader(io.StringIO(text))]
    raise ValueError(f"不支持的文件格式: {filename}")
