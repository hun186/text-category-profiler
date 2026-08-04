import json


def createIndex(es):
    mappings = {
            "properties": {
                "title": {"type": "text", "analyzer": "english"},
                "ethnicity": {"type": "text", "analyzer": "standard"},
                "director": {"type": "text", "analyzer": "standard"},
                "cast": {"type": "text", "analyzer": "standard"},
                "genre": {"type": "text", "analyzer": "standard"},
                "plot": {"type": "text", "analyzer": "english"},
                "year": {"type": "integer"},
                "wiki_page": {"type": "keyword"}
        }
    }
    
    es.indices.create(index="movies", mappings=mappings)

def getESData(es_tokens,indexname,startday,endday,langCode):
    resdataList = []
    jqbody = {
        "query": {
            "bool": {
                "must": [
                    { "bool": {
                        "must": [
                            {
                                "match":{
                                    "itc.rawTypeCode": "05"
                                    }
                                },
                            {
                                "match": {
                                    "rawInfo.langCode": langCode
                                    }
                                }
                            ]
                        }
                    }
                ],
                "filter": [
                    {"range": {
                        "itcDT":{
                            "gte":startday,
                            "lte":endday,
                        }
                    }
                }
            ]
        }
    }
    }
    '''
    jqbody['query']['bool']['should'] = []
    jqbody['query']['bool']['should'].extend(
        [
            {
                'bool':{
                    'must':[{
                        "exists": {
                            "field": "select"
                            }
                        }]
                    }
                },
            {
                'bool':{
                    'must':[{                    
                        'term':
                            {
                                "selectedMessage": True
                            }
                        }]
                    }
                }
        ])
    '''
    jqbody['query']['bool']['filter'].append(
        {'terms':{
            "selectedMessage":[True]}
         })
    es = Elasticsearch(
        es_tokens['host'],
        http_auth=(es_tokens['user'], es_tokens['password']),
        verify_certs=False
        )
    res =es.search(index=indexname,body=jqbody,scroll="2m")
    #for x in res['hits']['hits']:
        #print("item in res",x)    
    sid=res['_scroll_id']
    scroll_size =len(res['hits']['hits'])
    #logging.error(res['hits']['total'])
    #logging.error(scroll_size)

    while scroll_size > 0:
        #resdataList.extend(res['hits']['hits'])
        #print('-'*50)
        #print(res['hits']['hits'])
        resdataList.extend([
            (x['_id'],x['_source']['rawInfo'].get('content')) 
                            for x in res['hits']['hits']])
        #for x in res:
            #print("item in res",x)
        res = es.scroll(scroll_id=sid,scroll="2m")
        
        sid=res['_scroll_id']
        scroll_size=len(res['hits']['hits'])
    return resdataList
                            

#A = {"_source":{
A = {
	"uuid":"bfe-22332331345",
	"rawInfo":{
		"content":"1207,highValue好棒棒循環難題，很多氫設備要大量使用才有成本效益，但是不先裝設這些天價設備，則根本無法吸引人使用，更不會有相關產業，如何過渡到氫時代是氫經濟的研究課題。",
		"langCode":"C"},
	"communication":{
		"subject":"SEL Name",
	},
	"itc":{
		"rawTypeCode":"05"
		},
	#"itcDT":"2022-12-03T16:00:01.292Z",
    #"itcDT":"2022-12-03T16:00:01",
    "importDT":"2022-12-07T09:13:01",
    "userNames":"IOERL",
    "selectedMessage": False,
    "ak6":{
        "select":{
            "selectorName":"John"}
        },
    "ai":{
        "classLabels":{
            "highValue":True
            }
        }
    #"itcDT":"2022-12-18"
 #},
}
#print(A)
with open('data2.json', 'w') as f:
    json.dump(A, f)


from elasticsearch import Elasticsearch, helpers
import configparser

#config = configparser.ConfigParser()
#config.read('example2.ini')


es_tokens = {
    "host" : "https://localhost:9200",
    #"host" : "http://localhost:9200",
    "user" : "elastic",
    "password" :"=lJg5OAxH_Oivzo1ZB-1",
    #"password" :"Rhhl35kvMf6Xm0U*PTAH"
}

'''
es = Elasticsearch(
    cloud_id=config['ELASTIC']['cloud_id'],
    http_auth=(config['ELASTIC']['user'], config['ELASTIC']['password'])
)
'''


es = Elasticsearch(
    es_tokens['host'],
    http_auth=(es_tokens['user'], es_tokens['password']),
    verify_certs=False
)
try:
    createIndex(es)
except:
    pass

es.index(index="movies", id=11777, document=A)
#startday = "2022-12-01"
startday = "2022-12-01T00:00:00Z"
#endday = "2022-12-30"
endday = "2022-12-10T20:00:00Z"
langCode = 'C'
indexname = "movies"
resdataList = getESData(es_tokens,indexname,startday,endday,langCode)

print('-'*50)
print("alldata:")
for x in es.search()['hits']['hits']:
    print(x)
print('='*50)
print('='*50)
print(f'pick data between {startday} and {endday}:')
print("resdataList", resdataList)
print('*'*50)
for x in resdataList:
    print(x)