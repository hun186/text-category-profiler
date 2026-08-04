# utils/ES_ingest_txt_to_es.py
# python ES_ingest_txt_to_es.py -d D:\shared\TopicClassification\TopicTextCrawler\Books\新聞網\聯合國新聞網\UnTagged\最新消息
# cd D:\shared\TopicClassification\PythonModule\utils && python ES_ingest_txt_to_es.py -d D:\shared\TopicClassification\poc-agent\data\軍事情報文本\mil_30k_300days -i mil_reports-01
import os
import sys
import time
import hashlib
import argparse
from datetime import datetime
from typing import Iterable, List, Dict, Generator, Tuple

from elasticsearch import Elasticsearch, helpers
from ES_utils import INDEX_MAPPINGS
from ES_utils import get_es_client
from ES_utils import ensure_index

def iter_txt_paths(root_dir: str, exts: Tuple[str, ...] = (".txt",)) -> Generator[str, None, None]:
    """遞迴產生所有副檔名符合的檔案絕對路徑（大小寫不敏感）。"""
    exts = tuple(e.lower() for e in exts)
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.abspath(os.path.join(dirpath, fn))

def read_text_best_effort(path: str) -> str:
    """容錯讀取文字檔：優先 utf-8-sig，失敗再嘗試常見本地編碼。"""
    candidates = ["utf-8-sig", "utf-8", "cp950", "big5", "latin-1"]
    last_err = None
    for enc in candidates:
        try:
            with open(path, "r", encoding=enc, errors="strict") as fp:
                return fp.read()
        except Exception as e:
            last_err = e
    # 最後退回「忽略錯字元」避免整檔失敗
    with open(path, "r", encoding="utf-8", errors="ignore") as fp:
        return fp.read()

def make_uuid_from_file(path: str) -> str:
    """以路徑 + 檔案大小 + mtime 製作穩定 uuid（避免重複插入）。"""
    try:
        st = os.stat(path)
        basis = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    except Exception:
        basis = os.path.abspath(path)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()

def make_uuid_from_content(path: str) -> str:
    """以檔案內容的 SHA1 當 uuid（跨路徑去重）。"""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

# ======【修改】build_doc_from_file：加入 dedup_by_content 參數 ======
def build_doc_from_file(path: str,
                        lang_code: str = "C",
                        user_name: str = "crawler",
                        raw_type_code: str = "05",
                        dedup_by_content: bool = False) -> Dict:
    """將檔案內容包成符合 mapping 的文件；dedup_by_content=True 時用內容雜湊當 _id。"""
    #print(f"running build_doc_from_file for path {path}")
    content = read_text_best_effort(path)
    subject = os.path.splitext(os.path.basename(path))[0]  # 檔名作為主題
    # —— 決定 _id 來源 —— #
    if dedup_by_content:
        doc_id = make_uuid_from_content(path)  # 跨路徑去重
    else:
        doc_id = make_uuid_from_file(path)     # 預設：同內容不同路徑視為不同

    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    # 可選：附帶可觀測欄位（非必要）
    try:
        st = os.stat(path)
        file_size = st.st_size
        file_mtime = int(st.st_mtime)
    except Exception:
        file_size = None
        file_mtime = None

    return doc_id, {
        "uuid": doc_id,
        "rawInfo": {"content": content, "langCode": lang_code},
        "communication": {"subject": subject},
        "itc": {"rawTypeCode": raw_type_code},
        "importDT": now_iso,
        "userNames": user_name,
        "selectedMessage": False,
        "ak6": {"select": {"selectorName": "Crawler"}},
        "ai": {"classLabels": {"highValue": False}},
        # 觀測資訊（可留可拿掉）
        "sourceFile": {
            "path": os.path.abspath(path),
            "size": file_size,
            "mtime": file_mtime,
            "dedupByContent": dedup_by_content,
        },
    }


# ======【修改】bulk_insert_txt_dir：把 dedup_by_content 串進來 ======
def bulk_insert_txt_dir(index_name: str,
                        root_dir: str,
                        es_host: str = "http://localhost:9200",
                        batch_size: int = 500,
                        lang_code: str = "C",
                        user_name: str = "crawler",
                        op_type: str = "index",  # "index" 覆寫同 id；"create" 僅新建
                        dedup_by_content: bool = False  # ← 新增參數（預設關閉）
                        ) -> int:
    """
    遞迴掃描 root_dir 下所有 .txt，以 bulk 寫入 ES。
    回傳成功插入/覆寫的文件數量。
    """
    es = get_es_client(es_host)
    ensure_index(index_name=index_name, mappings=INDEX_MAPPINGS, es_client=es)

    def gen_actions() -> Generator[Dict, None, None]:
        for p in iter_txt_paths(root_dir):
            doc_id, src = build_doc_from_file(
                p, lang_code=lang_code, user_name=user_name, dedup_by_content=dedup_by_content
            )
            yield {
                "_op_type": op_type,  # "index" or "create"
                "_index": index_name,
                "_id": doc_id,
                "_source": src,
            }

    total_success = 0
    for batch in chunked(gen_actions(), batch_size):
        try:
            success, _ = helpers.bulk(es, batch, raise_on_error=False)
            total_success += success
            print(f"✅ 批次完成，本批 {success} 筆，累計 {total_success} 筆")
        except Exception as e:
            print(f"⚠️ 批次寫入失敗：{e}")

    print(f"🎯 全部完成，成功寫入/覆寫：{total_success} 筆")
    return total_success

def build_doc_from_file_OLD(path: str,
                        lang_code: str = "C",
                        user_name: str = "crawler",
                        raw_type_code: str = "05") -> Dict:
    """將檔案內容包成符合你 mapping 的文件。"""
    content = read_text_best_effort(path)
    subject = os.path.splitext(os.path.basename(path))[0]  # 檔名作為主題
    doc_id = make_uuid_from_file(path)
    now_iso = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return doc_id, {
        "uuid": doc_id,
        "rawInfo": {"content": content, "langCode": lang_code},
        "communication": {"subject": subject},
        "itc": {"rawTypeCode": raw_type_code},
        "importDT": now_iso,
        "userNames": user_name,
        "selectedMessage": False,
        "ak6": {"select": {"selectorName": "Crawler"}},
        "ai": {"classLabels": {"highValue": False}},
    }

def chunked(iterable: Iterable, size: int) -> Generator[List, None, None]:
    """將 iterable 以固定批次切塊。"""
    buf = []
    for x in iterable:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
'''
def bulk_insert_txt_dir(index_name: str,
                        root_dir: str,
                        es_host: str = "http://localhost:9200",
                        batch_size: int = 500,
                        lang_code: str = "C",
                        user_name: str = "crawler",
                        op_type: str = "index"  # "index" 覆寫同 id；"create" 僅新建
                        ) -> int:
    """
    遞迴掃描 root_dir 下所有 .txt，以 bulk 寫入 ES。
    回傳成功插入/覆寫的文件數量。
    """
    es = get_es_client(es_host)
    ensure_index(index_name=index_name, mappings=INDEX_MAPPINGS, es_client=es)
    #ensure_index(index_name=index_name)

    # 產生所有文件的 actions（lazy）
    def gen_actions() -> Generator[Dict, None, None]:
        for p in iter_txt_paths(root_dir):
            doc_id, src = build_doc_from_file(p, lang_code=lang_code, user_name=user_name)
            yield {
                "_op_type": op_type,  # "index" or "create"
                "_index": index_name,
                "_id": doc_id,
                "_source": src,
            }

    total_success = 0
    for batch in chunked(gen_actions(), batch_size):
        try:
            # helpers.bulk 在 7.x/8.x 都可用，使用 _source 兼容
            success, _ = helpers.bulk(es, batch, raise_on_error=False)
            total_success += success
            print(f"✅ 批次完成，本批 {success} 筆，累計 {total_success} 筆")
        except Exception as e:
            print(f"⚠️ 批次寫入失敗：{e}")

    print(f"🎯 全部完成，成功寫入/覆寫：{total_success} 筆")
    return total_success
'''
# ======【修改】CLI 介面：加入 --dedup-by-content 開關 ======
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="遞迴掃描資料夾中的 .txt 並以 bulk 寫入 Elasticsearch"
    )
    parser.add_argument("-i", "--index", default="news_test", help="Elasticsearch 索引名稱")
    parser.add_argument("-d", "--dir", required=True, help="要遞迴掃描的根目錄")
    parser.add_argument("--host", default="http://localhost:9200", help="Elasticsearch 連線位址")
    parser.add_argument("--batch", type=int, default=500, help="bulk 批次大小（預設 500）")
    parser.add_argument("--lang", default="C", help="rawInfo.langCode（預設 C）")
    parser.add_argument("--user", default="crawler", help="userNames（預設 crawler）")
    parser.add_argument("--op", choices=["index", "create"], default="index",
                        help="index=覆寫同 id；create=僅新建")
    parser.add_argument("--dedup-by-content", action="store_true",
                        help="以內容雜湊作為 _id（跨路徑去重）。預設關閉。")

    args = parser.parse_args()

    bulk_insert_txt_dir(
        index_name=args.index,
        root_dir=args.dir,
        es_host=args.host,
        batch_size=args.batch,
        lang_code=args.lang,
        user_name=args.user,
        op_type=args.op,
        dedup_by_content=args.dedup_by_content,  # 串入
    )
    
'''
# —— 可選：提供命令列介面 —— #
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="遞迴掃描資料夾中的 .txt 並以 bulk 寫入 Elasticsearch"
    )
    parser.add_argument("-i", "--index", default = "news_test", help="Elasticsearch 索引名稱")
    parser.add_argument("-d", "--dir", required=True, help="要遞迴掃描的根目錄")
    parser.add_argument("--host", default="http://localhost:9200", help="Elasticsearch 連線位址")
    parser.add_argument("--batch", type=int, default=500, help="bulk 批次大小（預設 500）")
    parser.add_argument("--lang", default="C", help="rawInfo.langCode（預設 C）")
    parser.add_argument("--user", default="crawler", help="userNames（預設 crawler）")
    parser.add_argument("--op", choices=["index", "create"], default="index",
                        help="index=覆寫同 id；create=僅新建")
    args = parser.parse_args()

    bulk_insert_txt_dir(
        index_name=args.index,
        root_dir=args.dir,
        es_host=args.host,
        batch_size=args.batch,
        lang_code=args.lang,
        user_name=args.user,
        op_type=args.op,
    )
'''