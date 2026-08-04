# utils/ES_utils.py
from pprint import pprint
import json
import yaml
import os

from elasticsearch import Elasticsearch, helpers
from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError

# 預設連線到 localhost:9200
es = Elasticsearch("http://localhost:9200")

INDEX_NAME = "news_test"

INDEX_MAPPINGS = {
    "properties": {
        "uuid": {"type": "keyword"},
        "rawInfo": {
            "properties": {
                "content": {"type": "text"},
                "langCode": {"type": "keyword"}
            }
        },
        "communication": {
            "properties": {
                "subject": {"type": "text"}
            }
        },
        "itc": {
            "properties": {
                "rawTypeCode": {"type": "keyword"}
            }
        },
        "importDT": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
        "userNames": {"type": "keyword"},
        "selectedMessage": {"type": "boolean"},
        "ak6": {
            "properties": {
                "select": {
                    "properties": {
                        "selectorName": {"type": "keyword"}
                    }
                }
            }
        },
        "ai": {
            "properties": {
                "classLabels": {
                    "properties": {
                        "highValue": {"type": "boolean"}
                    }
                }
            }
        },
    }
}

def get_es_client(es_host: str = "http://localhost:9200") -> Elasticsearch:
    """
    建立並回傳 Elasticsearch 連線客戶端。
    """
    try:
        es = Elasticsearch(es_host)
        if not es.ping():
            raise ConnectionError("Elasticsearch 服務無回應，請確認是否啟動。")
        return es
    except Exception as e:
        raise RuntimeError(f"連線 Elasticsearch 失敗: {e}")


def es_create_index(es: Elasticsearch, index_name: str, mappings: dict = None):
    """
    建立 index（若不存在），可附帶 mappings。
    """
    try:
        if not es.indices.exists(index=index_name):
            body = {"mappings": mappings} if mappings else {}
            es.indices.create(index=index_name, body=body)
            print(f"✅ 已建立索引: {index_name}")
        else:
            print(f"ℹ️ 索引已存在: {index_name}")
    except RequestError as e:
        print(f"⚠️ 建立索引失敗: {e.info}")
    except Exception as e:
        print(f"⚠️ 發生錯誤: {e}")
        
def apply_es_mapping(es: Elasticsearch, index: str, yaml_path: str):
    """
    將指定 YAML 檔案的 mapping 套用到既有的 ES index。
    只會「新增」欄位，不會更改已存在的欄位型別。
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        mapping = yaml.safe_load(f)
    es.indices.put_mapping(index=index, body=mapping)
    print(f"✅ 已將 mapping 套用到 index: {index}")

def es_insert_test_doc(
    index_name: str, doc: dict, es_host: str = "http://localhost:9200"
) -> str:
    """
    插入單筆文件到 Elasticsearch。
    若成功，回傳文件 ID。
    """
    try:
        es = get_es_client(es_host)
        res = es.index(index=index_name, document=doc)
        print(f"✅ 已插入文件到 {index_name}, _id={res['_id']}")
        return res["_id"]
    except Exception as e:
        print(f"⚠️ 插入文件失敗: {e}")
        return ""

def ensure_index(index_name=INDEX_NAME, mappings=None, settings=None, es_client: Elasticsearch = None):
    """
    確保 index 存在，若不存在則建立。
    可選擇傳 mappings 與 settings。
    可選擇提供 es_client；若未提供則使用模組內的全域 es。
    """
    client = es_client or es

    if not client.indices.exists(index=index_name):
        body = {}
        if settings:
            body["settings"] = settings
        if mappings:
            body["mappings"] = mappings
        client.indices.create(index=index_name, body=body)
        print(f"✅ Created index: {index_name}")
    else:
        print(f"ℹ️ Index already exists: {index_name}")

def es_bulk_insert(
    index_name: str, docs: list, es_host: str = "http://localhost:9200"
) -> int:
    """
    批次插入多筆文件到 Elasticsearch。
    回傳成功插入的文件數量。
    """
    try:
        es = get_es_client(es_host)
        actions = [{"_index": index_name, "_source": doc} for doc in docs]
        success, _ = helpers.bulk(es, actions)
        print(f"✅ 批次插入完成，共 {success} 筆")
        return success
    except Exception as e:
        print(f"⚠️ 批次插入失敗: {e}")
        return 0
    
def es_upsert_doc(
    index_name: str, 
    doc: dict, 
    es_host: str = "http://localhost:9200"
) -> str:
    """
    高階函式：保證 index 存在，並插入單筆文件。
    若成功，回傳文件 _id。
    """
    try:
        es = get_es_client(es_host)

        # 定義簡單的 mapping，避免 Elasticsearch 動態亂推斷型態
        mappings = INDEX_MAPPINGS

        # 建立 index（如果不存在）
        if not es.indices.exists(index=index_name):
            es.indices.create(index=index_name, body={"mappings": mappings})
            print(f"✅ 已建立索引並套用 mapping: {index_name}")

        # 插入文件
        res = es.index(index=index_name, document=doc, 
                       id=doc["uuid"],   # 強制用 uuid 當 _id)
                       )
        print(f"✅ 已插入文件到 {index_name}, _id={res['_id']}")
        return res["_id"]

    except Exception as e:
        print(f"⚠️ 插入或建立索引失敗: {e}")
        return ""

def es_browse(index_name=INDEX_NAME, size=10, query=None):
    """
    瀏覽 index 裡的文件，類似 SQLite SELECT * LIMIT N。
    
    index_name: 要查詢的 index
    size: 取回筆數 (預設 10)
    query: 可選，Elasticsearch DSL 查詢 dict，例如：
           {"match": {"userNames": "IOERL"}}
    """
    ensure_index(index_name=index_name)

    body = {"query": {"match_all": {}}}
    if query:
        body = {"query": query}

    resp = es.search(index=index_name, body=body, size=size)

    hits = resp["hits"]["hits"]
    results = []
    for h in hits:
        results.append({
            "_id": h["_id"],
            "_score": h["_score"],
            "_source": h["_source"]
        })

    print(f"📄 Retrieved {len(results)} docs from index '{index_name}'")
    return results

def es_upsert_test_data():
    sj_ct = []
    uuid = "bae-22332331345"
    subject = "「不是都免稅！」賴總統宣布月薪5萬可免繳所得稅　財政部補充「要單身、租屋」"
    content = """
「不是都免稅！」賴總統宣布月薪5萬可免繳所得稅　財政部補充「要單身、租屋」
發布時間：2025/9/24 07:35

記者孫偉倫／台北報導

賴清德總統21日宣布明年將推動重大稅改措施，對外傳達從明年5月報稅開始，若年薪約62.6萬元以下（約月薪5萬元），將可完全免繳綜合所得稅消息，財政部對此補充表示，5萬月薪是以單身青年且租屋自住之情境試算，其享有免稅額9.7萬元、單身標準扣除額13.1萬元、薪資所得特別扣除額21.8萬元及房屋租金支出特別扣除額上限18萬元，合計在62.6萬元以下可免繳納綜所稅。

「不是這樣算」賴總統宣布月薪5萬可免繳所得稅　財政部補充「要單身、租屋」
新台幣。（示意圖／pexels）

財政部23日說明，近年來政府致力減輕民眾租稅負擔，調高基本生活費、免稅額及各項扣除額，包括106年度起每人基本生活所需之費用不予課稅、107年度實施所得稅制優化方案，調高標準扣除額及薪資所得、身心障礙及幼兒學前特別扣除額等4項扣除額、108年度增訂長期照顧特別扣除額、113年度起擴大幼兒學前特別扣除額及房屋租金支出改列特別扣除額並調高扣除額度50%。

廣告 更多內容請繼續往下閱讀

另配合消費者物價指數上漲，於106年度、111年度及113年度分別公告調高綜所稅免稅額、相關扣除額及課稅級距金額，並逐年調高各年度基本生活費。該部將於兼顧財政收入、租稅公平及稅政簡化等原則下，持續檢討。
"""
    sj_ct.append((uuid,subject,content))
    uuid = "selected uuid-bbe-22332331345"
    subject = "河智媛禹洙漢不甩風波「野生看球」 球迷暖哭：隔天韓國有班耶"
    content = """
河智媛禹洙漢不甩風波「野生看球」 球迷暖哭：隔天韓國有班耶
詹鎰睿
2025年9月29日 週一 下午9:58


0
禹洙漢、河智媛趕在回韓國前，跑來球場野生應援。(圖／翻攝IG）
禹洙漢、河智媛趕在回韓國前，跑來球場野生應援。(圖／翻攝IG）
樂天女孩人氣成員河智媛、禹洙漢今（29日）傳出未來恐很難再和樂天球團續約，引起球迷一陣討論。即便外界聲音不斷，兩人從未有離開台灣的念頭，河智媛更喊話「明年想繼續在樂天！」而在稍早的比賽，河智媛、禹洙漢悄悄現身場邊，超強行動力也感動無數球迷。

據了解，韓國職棒韓華鷹將在30日舉行例行賽最後一場賽事，對主場球隊來說非常重要，作為啦啦隊的河智媛、禹洙漢也確定出席。沒想到今晚他們還沒飛回韓國，反而留在台灣，決定看完今年樂天最後一場主場例行賽再走。
"""
    
    sj_ct.append((uuid,subject,content))
    uuid = "bce-22332331345"
    subject = "川普關稅鎖定產業 聚焦家具.半導體 農業卻成犧牲"
    content = """
川普關稅鎖定產業 聚焦家具.半導體 農業卻成犧牲
萬敏婉
2025年9月30日 週二 下午8:01


1
圖／達志影像路透社
圖／達志影像路透社
美國總統川普的關稅大棒繼續揮舞，這回不是針對國家，而是鎖定產業。除了已宣布的藥品、電影等產業外，家具以及櫥櫃沙發等裝修材料，已確定10月14日起加稅25%，未來還會提高。由於中國是美進口家具最主要來源，影響最大。此外，半導體、晶片、無人機等高科技產業，也將是川普加稅重點。儘管關稅目的是要讓企業把生產拉回美國，但農民卻成為關稅的最大犧牲品，因為北京當局祭出「拒買牌」，導致今年前七個月，美國對中國農產出口總額與去年比，等同腰斬。美國農民呼籲川普推進貿易談判，為大豆、玉米拓展市場。

廣告

美中之間的貿易關稅衝突再有新發展，這回鎖定的產業範圍，包括了家具，以及櫥櫃在內的家居裝修材料，甚至可能擴展到半導體。

美國總統川普周一(9月29日)透過社交媒體發文表示，將對所有非美國生產的家具，徵收高額關稅。文章中他直言，加稅目的就是為了讓當前在家具業務上，輸給中國等其他國家的北卡羅來納州，能夠再次偉大。

據了解，作為全球最大家具製造基地的中國，長期高居美國進口家具來源國榜首，儘管近來遭遇越南追趕，但直到去年仍有高達33%的占比，遠高過越南的23%，排名第三的則是墨西哥的20%。

其中，越南與墨西哥境內不少家具廠，都是中資企業為了避稅而開設。也就是說，去年高達255億美元的美國家具進口總額，可能有將近七成都進了中資口袋。而川普這回要對非美國製造家具提高關稅，影響最大的也會是中方。

在川普發文之後，美國白宮進一步宣告相關細節。包括從10月14日起，對進口的廚櫃和衛浴化妝台，以及沙發、軟墊椅等製品徵收25%關稅，這個稅率還將從明年1月1日起提高到30%至50%。至於普遍用在裝修的軟木材，則徵收10%的關稅。

經濟學人智庫中國經濟學家 蘇月：「無論你遷往何處，關稅都是一樣的。」

由於川普這回推出的新關稅，鎖定的是產品類型而不是單一國家，而且只對英國、日本、歐盟等已經達成貿易協議的國家，給予相對優惠的稅率。

學者坦言，這將讓過去透過遷廠來躲避關稅的手段失效。但多數企業仍相信，部分國家有機會與美國達成更好的貿易協定，或者戰火影響相對小，因此仍會有所動作。

經濟學人智庫中國經濟學家 蘇月：「所以我認為，我們的想法是實現供應鏈多元化，而不是將工廠永久遷移到其他地方。」

然而，川普有意藉由關稅來改變全球供應鏈的產業，還不只有家具或家居裝修產業，晶片半導體等高科技產業，才是更為關鍵。

TVB主播：「美國政府據報針對半導體行業部署新關稅安排。」

路透引述知情人士說法指出，川普政府為了進一步推動企業回美國設廠製造，正考慮根據對所有內含晶片的電子產品，根據晶片數量來收稅。也就是說，從電動牙刷到筆記型電腦等各式消費性產品，只要含有晶片，就要收稅。

《華爾街日報》更披露，川普政府還考慮強制半導體企業，在美國製造多少產品，才能夠進口多少產品，否則就得徵稅。但只要企業承諾在美國生產一定數量的晶片，那麼在建廠投產前，進口相應數量的晶片，都可以免稅。

中國大陸外交部發言人 郭嘉昆：「關稅戰貿易戰沒有贏家，搞保護主義沒有出路。」

北京當局對於川普政府針對產業所醞釀的新一輪關稅，以相同論調持續高分貝反彈；同時對美國大豆與玉米等農產品，持續祭出「拒買牌」做為反制，因此今年1-7月，美國對中國的農產品出口總額與去年同期相比，年減53%，等同腰斬。

美國肯德基州農民：「關稅對大豆農民的影響極具毀滅性。當前美國種植大豆總量的25%，或者說，你只要看到一片黃豆田，每四行大豆中的一行，都運往中國。但現在，中國一顆大豆都沒買。」

目前正進入收穫農忙期的美國農民坦言，中國的拒買確實為美國農民拉起了警報，儘管川普計劃把關稅收入移作美國農民的現金補貼，來緩解衝擊，但相關補貼政策還需要國會批准，最快2026年初才會發放。

印第安納州農民：「美國農民，尤其是我自己，不想要援助款。我們想工作。我們耕種土地，收割土地上的作物，我們最不想要的就是施捨。」

身處在川普與共和黨重要票倉的美國中西部農民，期盼川普在揮舞關稅大棒之外，更要推進貿易談判，為美國農民開拓更多市場與銷路。
"""
    sj_ct.append((uuid,subject,content))
    uuid = "bce-4795"
    subject = "俄烏戰爭@wiki"
    with open(os.path.join("sample_data",subject),'rt',encoding='utf-8') as fp:
        content = fp.read()
    sj_ct.append((uuid,subject,content))
    #for idx in range(0,len(sj_ct)):
    for idx in range(0,1):
        uuid,subject,content = sj_ct[idx]
        A = {
            "uuid": uuid,
            "rawInfo": {
                "content": content,
                "langCode": "C"
            },
            "communication": {"subject": subject},
            "itc": {"rawTypeCode": "05"},
            "importDT": "2022-12-07T09:13:01",
            "userNames": "IOERL",
            "selectedMessage": True,
            "ak6": {"select": {"selectorName": "John"}},
            "ai": {"classLabels": {"highValue": True}}
        }
        
        es_upsert_doc(INDEX_NAME, A)
        
if __name__ == '__main__':

    es_upsert_test_data()
    # 直接瀏覽前 10 筆 (類似 SELECT * LIMIT 10)
    all_docs = es_browse(size=10)
    
    # 查詢 userNames = IOERL 的文件
    q ={"match": {"userNames": "IOERL"}}
    q = {
      "nested": {
        "path": "multidim_event_json",
        "query": {
          "match": { "multidim_event_json.Person.name": "河智4媛" }
        },
        "inner_hits": {}
      }
    }
    q = {
      #"query": {
        "nested": {
          "path": "multidim_event_json",
          "query": {
            "term": {
            #"match": {
              # 如果 name 有 keyword/raw 子欄位，用它做精確比對
              "multidim_event_json.Person.name.keyword": "河智媛"
              # 或者你建立的是 .raw 子欄位，就用 name.raw
              # "multidim_event_json.Person.name.raw": "河智媛"
            }
          },
          "inner_hits": {}   # 想看命中哪個事件可保留
        }
      #}
    }

    filtered = es_browse(size=5, query=q)
    
    print("\n=== All Docs ===")
    #for d in all_docs:
    for d in filtered:
        # 方式一：用 json.dumps 排版
        print(json.dumps(d, indent=2, ensure_ascii=False))
        # 或者方式二：pprint
        # pprint(d, indent=2, width=100, compact=False)
