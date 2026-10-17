import os

esJob = {
    "es_tokens" : {
        #"host" : "http://localhost:9200",
        "host" : "https://localhost:9200",
        "user" : "elastic",
        "password" : os.environ.get("TCP_ELASTIC_PASSWORD")
    },
	"indexname" : "movies",
	"startDay" : "2022-12-01T00:00:00Z",
	"endDay" : "2022-12-10T20:00:00Z",
    "langCode" : "C",
    "Vis_ESFileNameMode": "subject_id" #"","subject_id"
}