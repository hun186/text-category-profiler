LocalExemptDict = {
    "Test":{"condition":{
        "SimpleTag":"^South Sea$",
        "text":".*",
        "nTriggerUPD":0 #0表示不觸發
        #"text":"(?=.*第 5 卷|.*abc)(?=.*12rg4|.*肖 锋|.*3f3).*"
        },
        "OutputTag":"Exempt-Test",
        "OutputTagScore":0
        },
    "20Da":{"condition":{
        "SimpleTag":("(^Falun Gong$)|(^CPC Affairs$)|"
            "(^CPC Party Development$)|(^.*Politics.*$)|(^.*United Front.*$)"),
        #文本含有 (二十大或20大) 且含有　(代表、中共、党)
        "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"},
        "OutputTag":"CPC Meeting",
        #"OutputTagScore":200
        },
    
    # "Valueless Report":{"condition":{
    #     "SimpleTag":(".*"),
    #     #文本含有 (二十大或20大) 且含有　(代表、中共、党)
    #     "text":"((?=.*证券)(?=.{0,20}\*行业週报\*).*)|(.*Mini M$).*|((?=.*TODAY ONLY)(?=.*\* LIMIT).*)"},
    #     "OutputTag":"Keyword Neg Filter-Valueless Report",
    #     "OutputTagScore":-1000000,
    #     },
    
#    "Scrap":{"condition":{
#        "SimpleTag":"^Scrap$",
#        "text":".*",
#        "nTriggerUPD":1},
#        "OutputTag":"Exempt-Scrap",
#        "OutputTagScore":0
#        },
    
    }
try:
    from VisParameters_DRN import LocalExemptDict_DRN
    LocalExemptDict.update(LocalExemptDict_DRN)
    del(LocalExemptDict_DRN)
except:
    pass
GlobalExemptDict = {
    #"20Da":{"condition":{"SimpleTag":}},
    "Test":{"condition":{
        "SimpleTag":"^South Sea$",
        "RatioInterval":[3,1], #閉區間
        "nTriggerUPD":3
        },
        "OutputTag":"Exempt-Test",
        "OutputTagScore":0
        },

    "Falun Gong Global":{"condition":{
        "SimpleTag":"^Falun Gong$",
        "RatioInterval":[0.000000001,0.3], #閉區間
        "nTriggerUPD":8
        },
        "OutputTag":"Exempt-Falun Gong",
        "OutputTagScore":0
        },

    "Abnormally Repeated Email Header Global":{"condition":{
        "SimpleTag":"^Spam-Abnormally Repeated Email Header$",
        "RatioInterval":[0.000000001,0.7], #閉區間
        "nTriggerUPD":3
        },
        "OutputTag":"Exempt-Spam-Abnormally Repeated Email Header",
        "OutputTagScore":0
        },
    
    }
try:
    from VisParameters_DRN import GlobalExemptDict_DRN
    GlobalExemptDict.update(GlobalExemptDict_DRN)
    del(GlobalExemptDict_DRN)
except:
    pass
BinMissionDict = {
    "Test":{
        #"active":True,
        "InfoScoreSumInterval":[500,99999999],
        "InfoScoreMeanInterval":[-99999999,99999999],
        "Labels":{
            "SimpleTag":"(^JP Affairs$)",
            "MatchingBlockInterval":[2,99999999],
            "RatioInterval":[0.5,1],
            },
        "KW":{
            "MatchingBlockWithKWInterval":[0,99999999],
            "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
            },
        },
    "20Da":{
        "active":True,
        "Icon":"♔",
        "InfoScoreSumInterval":[300,99999999],
        "InfoScoreMeanInterval":[40,99999999],
        "Labels":{
            "SimpleTag":"(^CPC Affairs$)|(^CPC Party Development$)|(^CPC Meeting$)",
            "MatchingBlockInterval":[2,99999999],
            "RatioInterval":[0.2,1],
            },
        "KW":{
            "MatchingBlockWithKWInterval":[0,99999999],
            "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
            },
        },
    "APEC":{
        "active":True,
        "Icon":"✴",
        "InfoScoreSumInterval":[300,99999999],
        "InfoScoreMeanInterval":[40,99999999],
        "Labels":{
            "SimpleTag":"(^APEC$)",
            "MatchingBlockInterval":[3,99999999],
            "RatioInterval":[0.1,1],
            },
        },
    "Boao Forum":{
        "active":True,
        "Icon":"🐢",
        "InfoScoreSumInterval":[300,99999999],
        "InfoScoreMeanInterval":[40,99999999],
        "Labels":{
            "SimpleTag":"(^Boao Forum$)",
            "MatchingBlockInterval":[2,99999999],
            "RatioInterval":[0.1,1],
            },
        },
    "OBOR":{
        "active":True,
        "Icon":"🐲",
        "InfoScoreSumInterval":[300,99999999],
        "InfoScoreMeanInterval":[40,99999999],
        "Labels":{
            "SimpleTag":"(^One Belt One Road$)",
            "MatchingBlockInterval":[3,99999999],
            "RatioInterval":[0.1,1],
            },
        },
    "RUWar":{
        "active":True,
        #"Icon":"♔",
        "InfoScoreSumInterval":[300,99999999],
        "InfoScoreMeanInterval":[40,99999999],
        "Labels":{
            "SimpleTag":"(^RU-UA Confrontation$)",
            "MatchingBlockInterval":[2,99999999],
            "RatioInterval":[0.2,1],
            },
        "KW":{
            "MatchingBlockWithKWInterval":[0,99999999],
            "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
            },
        },
    }
try:
    from VisParameters_DRN_Sample import BinMissionDict_DRN
    BinMissionDict.update(BinMissionDict_DRN)
    del(BinMissionDict_DRN)
    from VisParameters_DRN import BinMissionDict_DRN
    BinMissionDict.update(BinMissionDict_DRN)
    del(BinMissionDict_DRN)
except:
    pass