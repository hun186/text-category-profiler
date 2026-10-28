import os

esJobTemplate = {
    "es_tokens" : {
        #"host" : "http://localhost:9200",
        "host" : "https://localhost:9200",
        "user" : "elastic",
        "password" : os.environ.get("TCP_ELASTIC_PASSWORD")
    },
	"indexnameTemplate" : "movies_%m",
	#"startDay" : "2022-12-01T00:00:00Z",
	#"endDay" : "2022-12-10T20:00:00Z",
    #"langCode" : "C",
    "langCodeList" : ["C","E","J"],
    "Vis_ESFileNameMode": "subject_id", #"","subject_id",
    #"selectedMessage":True
}