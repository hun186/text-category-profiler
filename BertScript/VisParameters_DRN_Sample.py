LocalExemptDict_DRN = {
    "Valueless Report":{"condition":{
        "SimpleTag":(".*"),
        #文本含有 (二十大或20大) 且含有　(代表、中共、党)
        "text": r"((?=.*证券)(?=.{0,20}\*行业週报\*).*)"
        #"text":".*",
        },
        "OutputTag":"Keyword Neg Filter-Valueless Report",
        "OutputTagScore":-30000,
        },
#    "Scrap":{"condition":{
#        "SimpleTag":"^Scrap$",
#        "text":".*",
#        "nTriggerUPD":1},
#        "OutputTag":"Exempt-Scrap",
#        "OutputTagScore":0
#        },    
    }
    
GlobalExemptDict_DRN = { 
    }
BinMissionDict_DRN = { 
    }

'''
BinMissionDict_DRN = {
    "FocTInSample":{
        "active":True,
        "Icon":"♔",
        #Or_Pool, And_Pool are dictionary
        "Or_Pool":{
            "Infor":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[30,99999999],
                "Labels":{
                    "SimpleTag":"(^Informatiive$)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.2,1],
                    },
                "KW":{
                    "MatchingBlockWithKWInterval":[0,99999999],
                    "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
                    },
                }
            },
        "And_Pool":{
            "Sport":{
                #"InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[-7,99999999],
                "Labels":{
                    "SimpleTag":"(^Sports$)",
                    "MatchingBlockInterval":[1,99999999],
                    #"RatioInterval":[0.2,1],
                    },
                "KW":{
                    "MatchingBlockWithKWInterval":[0,99999999],
                    "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
                    },
                },
            "Community":{
                #"InfoScoreSumInterval":[300,99999999],
                #"InfoScoreMeanInterval":[-100,99999999],
                "Labels":{
                    "SimpleTag":"(^Community Affairs$)",
                    #"SimpleTag":"(^Informatiive$)",
                    "MatchingBlockInterval":[10,99999999],
                    #"RatioInterval":[0.2,1],
                    },
                "KW":{
                    "MatchingBlockWithKWInterval":[0,99999999],
                    "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
                    },
                }
            
            }
        }
    }
'''