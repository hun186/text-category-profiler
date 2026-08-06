from utils.core.utilities import reCombiner
from utils.concurrency.MP_utils import MPlogger
from utils.pipeline.DataConverter_utils_Parameters import GeneralBinInfoScoreSumLBD

#在Test_result_Vis_utils.py中的BinMissionVerifier.singleConstraintBool()中，
#檢驗切片分數是否符合SimpleTag的正規表示式時，會自動加入符合SimpleTag類別的子類別一起考量。
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


MPLOGGER = MPlogger(logFile="Exempt.log")
MES = "Start to load LocalExemptDict_DRN from VisParameters_DRN"
MPLOGGER.logW(MES)
try:
    from VisParameters_DRN import LocalExemptDict_DRN
    LocalExemptDict.update(LocalExemptDict_DRN)
    del(LocalExemptDict_DRN)
    MES = f"Successfully loaded LocalExemptDict_DRN, the LocalExemptDict is now {LocalExemptDict}"
    MPLOGGER.logW(MES)
except Exception as e:
    MES = f"When loading LocalExemptDict_DRN, the following error occurs:\n{e}"
    MPLOGGER.logW(MES)
    

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
MES = "Start to load GlobalExemptDict_DRN from VisParameters_DRN"
MPLOGGER.logW(MES)
try:
    from VisParameters_DRN import GlobalExemptDict_DRN
    GlobalExemptDict.update(GlobalExemptDict_DRN)
    del(GlobalExemptDict_DRN)
    MES = f"Successfully loaded GlobalExemptDict_DRN, the GlobalExemptDict is now {GlobalExemptDict}"
    MPLOGGER.logW(MES)
except Exception as e:
    MES = f"When loading GlobalExemptDict_DRN, the following error occurs:\n{e}"
    MPLOGGER.logW(MES)

'''
1.當整篇文章總分高於InfoScoreSumLBD時，進行高相似度切片豁免。
2.因分數較高之類別可能為特殊或重要類別，不宜豁免，
故僅當該切片類別分數在ClassScoreUBD以下時，才進行豁免。
3.當切片文本長度大於SegTxtLenUBD時，才進行豁免。
4.當切片於前面某片切片的相似度達到SimilarLBDToExempt以上時，才進行豁免。
'''
#SimilarPiecesExemptMethod = None
SimilarPiecesExemptMethod = "theFuzz"
#SimilarPiecesExemptMethod = "difflib"
SimilarPiecesExemptSetting = {
    "difflib":{
        #"InfoScoreSumLBD": 500,
        "InfoScoreSumLBD": 100,
        "ClassScoreUBD": 300,
        "SegTxtLenUBD": 100,
        "SimilarIntvToExemptList": [
            #[(字元種類量下限,字元種類量上限),(較長序列長度下限,較長序列長度上限),(相似度下限,相似度上限)]
            #[(charTypeLBD,charTypeUBD),(longerSeqLBD,longerSeqUBD),(similarityLBD,similarityUBD)]
            [(80,99999999),(0,99999999),(0.2,1)], #非英文
            [(0,79),(0,99999999),(0.4,1)], #英文
            ],
        },
    "theFuzz":{
        #"InfoScoreSumLBD": 500,
        "InfoScoreSumLBD": 100,
        "ClassScoreUBD": 300,
        "SegTxtLenUBD": 100,
        "SimilarIntvToExemptList": [
            [(80,99999999),(0,99999999),(0.3,1)], #非英文
            [(0,79),(0,400),(0.5,1)], #英文短序列 fro fuzz.ratio
            [(0,79),(401,99999999),(0.55,1)], #英文長序列 for fuzz.ratio
            ],
        },
    #TODO
    "jaro_similarity":{
        "InfoScoreSumLBD": GeneralBinInfoScoreSumLBD,
        "ClassScoreUBD": 300,
        "SegTxtLenUBD": 100,
        #"SimilarLBDToExempt": 0.74,
        "SimilarIntvToExemptList": [
            #[(字元種類量下限,字元種類量上限),(相似度下限,相似度上限)]
            #[(charTypeLBD,charTypeUBD),(similarityLBD,similarityUBD)]
            [(80,99999999),(0,99999999),(0.74,1)], #非英文
            [(0,79),(0,99999999),(0.74,1)], #英文
            ],
        },
    }

#令邏輯式形如(M_1 and M2 and ... and M_m) and 
#[ 
#(S_1 or S_2 or ... or S_k) or
#(T_11 and T_12 and .. and T_1j1) or
#(T_21 and T_22 and .. and T_2j2) or
#(T_31 and T_32 and .. and T_3j3) or
#(T_41 and T_42 and .. and T_4j3) or
#]
#M_i收集為Must_Pool，S_i收集為Or_Pool，T_i收集為And_Pool
#如果沒有任何constraint，Must_Pool預設輸出為True,
#如果沒有任何constraint，Or_Pool及And_Pool_i預設Pool輸出為False
#針對Must_Pool，必須所有constraint為True，Must_Pool輸出才為True，
#如果Must_Pool輸出為False，key的整個result輸出則為False，early return。
#針對Or_Pool，只要有一個constraint為True，Or_Pool輸出則為True。
#針對And_Pool_i，必須所有constraint為True，And_Pool_i輸出才為True。

#對單一的constraint而言，裡面有列到的各個小條件都要成立，這個constraint輸出才為True。
#如果constraint沒有任何小條件，則該constraint輸出為True。
#如果Or_Pool和And_Pool皆為空，即視為沒有經過任何篩選，當做垃圾。

BinMissionDict = {
    "Test":{
        #"active":True,
        "Or_Pool":{
            "Main":{
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
                }
            }
        },
    "General":{
        "active":True,
        "Icon":"👍",
        "Must_Pool":{
            "NoFalun":{
                #"InfoScoreSumInterval":[300,99999999],
                #"InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Falun Gong$)",
                    "MatchingBlockInterval":[0,10],
                    "RatioInterval":[0,0.25],
                    },
                }
            },
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[GeneralBinInfoScoreSumLBD,99999999],
                "InfoScoreMeanInterval":[30,99999999],
                }
            }
        },
    "20Da":{
        "active":True,
        "Icon":"♔",
        "Must_Pool":{
            "NoFalun":{
                #"InfoScoreSumInterval":[300,99999999],
                #"InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Falun Gong$)",
                    "MatchingBlockInterval":[0,10],
                    "RatioInterval":[0,0.25],
                    },
                }
            },
        "Or_Pool":{
            "Main":{
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
                }
            }
        },
    "APEC":{
        "active":True,
        "Icon":"✴",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^APEC$)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.2,1],
                    },
                }
            }
        },
    "Boao Forum":{
        "active":True,
        "Icon":"🐢",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Boao Forum$)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.1,1],
                    },
                }
            }
        },
    "CrossStraitTree":{
        "active":True,
        "Icon":"✌️",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Cross-Strait Relations$)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.2,1],
                    },
                }
            }
        },
    "OBOR":{
        "active":False,
        "Icon":"🐲",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^One Belt One Road$)",
                    "MatchingBlockInterval":[3,99999999],
                    "RatioInterval":[0.1,1],
                    },
                }
            }
        },
    "RUWar":{
        "active":True,
        "Icon":"⚔",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^RU-UA Confrontation$)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.3,1],
                    },
                "KW":{
                    "MatchingBlockWithKWInterval":[0,99999999],
                    "text":"(?=.*二十大|.*20大)(?=.*代表|.*中共|.*党).*"
                    },
                }
            }
        },
    "CN Cooperation":{
        "active":True,
        "Icon":"👯",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(.*CN.*Cooperation)|(.*CN.*Trade)",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.2,1],
                    },
                }
            }
        },
    "CN Military":{
        "active":True,
        "Icon":"🚀",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"CN Military",
                    "MatchingBlockInterval":[2,99999999],
                    "RatioInterval":[0.2,1],
                    },
                }
            }
        },
    "Navigational Warning-Military":{
        "active":True,
        "Icon":"✪",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[GeneralBinInfoScoreSumLBD,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Navigational Warning-Military$)",
                    "MatchingBlockInterval":[1,99999999],
                    "RatioInterval":[0.3,1],
                    },
                }
            }
        },
    "Navigational Warning-Non Traditional Security":{
        "active":True,
        "Icon":"✣",
        "Or_Pool":{
            "Main":{
                "InfoScoreSumInterval":[GeneralBinInfoScoreSumLBD,99999999],
                "InfoScoreMeanInterval":[40,99999999],
                "Labels":{
                    "SimpleTag":"(^Navigational Warning-Non Traditional Security$)",
                    "MatchingBlockInterval":[1,99999999],
                    "RatioInterval":[0.3,1],
                    },
                }
            }
        },
    #開啓自動擴充子類功能，以下FocT表示條件式:
    #((總分-660以上 且 社區事務含2到10片) 且
    #((總分300以上且均分30以上且Infor 2片以上且infor佔比20%以上) 或
    # (Society開頭類別恰好2片) 或
    # (均分介於-37至-20間且Sports 1片以上) 且 (社區事務10片以上) 或
    # (均分60分且新冠勵志故事2片且新冠政府作為1片)
    #)
    "FocT":{
        "active":True,
        "Icon":"♔",
        "Must_Pool":{
            "NotTooMuch":{
                "InfoScoreSumInterval":[-1019,99999999],
                #"InfoScoreMeanInterval":[-90,99999999],
                "Labels":{
                    #"SimpleTag":"(^Community Affairs$)",
                    "MatchingBlockInterval":[2,10],
                    },
                }
            },
        "Or_Pool":{
            "Infor":{
                "InfoScoreSumInterval":[300,99999999],
                "InfoScoreMeanInterval":[30,99999999],
                "Labels":{
                    "SimpleTag":"(^Informative$)",
                    "MatchingBlockInterval":[3,99999999],
                    "RatioInterval":[0.2,1],
                    },
                },
            "Society":{
                "Labels":{
                    "SimpleTag":"(^Society.*)",
                    "MatchingBlockInterval":[2,2],
                    },
                },
            "COVID Story":{
                "Labels":{
                    #"SimpleTag":"(?=.*COVID|.*APO)(?=.*Story|.*BDK).*",
                    "SimpleTag":reCombiner(
                        reList = [
                            reCombiner(
                                reList=[
                                    ".*COVID",
                                    ".*APO"],
                                ).proc(),
                            reCombiner(
                                reList=[
                                    ".*Story",
                                    ".*BDK"],
                                ).proc()],
                        method = "and"
                        ).proc(),
                    "MatchingBlockInterval":[4,4],
                    },
                },
            "Measles":{
                "Labels":{
                    #"SimpleTag":"(?=.*COVID|.*APO)(?=.*Story|.*BDK).*",
                    "SimpleTag":reCombiner(
                        reList = [
                            reCombiner(
                                reList=[
                                    ".*Vaccine",
                                    ".*APO"],
                                ).proc(),
                            reCombiner(
                                reList=[
                                    ".*Measles",
                                    ".*APO"],
                                ).proc(),
                            ],
                        method = "and"
                        ).proc(),
                    "MatchingBlockInterval":[2,2],
                    },
                },
            },
        "And_Pool":{
            "Sport":{
                "InfoScoreMeanInterval":[-37,-20],
                "Labels":{
                    "SimpleTag":"(^Sports$)",
                    "MatchingBlockInterval":[1,99999999],
                    },
                },
            "Community":{
                "Labels":{
                    "SimpleTag":"(^Community Affairs$)",
                    "MatchingBlockInterval":[10,99999999],
                    },
                }
            },
        "And_Pool2":{
            "InfoScoreMean":{
                "InfoScoreMeanInterval":[60,60],
                },
            "Inspirational":{
                "Labels":{
                    "SimpleTag":"(^COVID-19 IPC For Community-Inspirational Story$)",
                    "MatchingBlockInterval":[2,2],
                    },
                },
            "Government":{
                "Labels":{
                    "SimpleTag":"(^COVID-19 IPC For Community-Government.*)",
                    "MatchingBlockInterval":[1,1],
                    },
                }
            },
        "And_Pool3":{
            "Public":{
                "InfoScoreMeanInterval":[-169,-169],
                "Labels":{
                    "SimpleTag":"(^.*Public.*$)",
                    "MatchingBlockInterval":[1,99999999],
                    },
                },
            "Community":{
                "Labels":{
                    #"SimpleTag":"(^Community Affairs$)|(^Society.*)",
                    "SimpleTag":reCombiner(
                        reList = ["^Community Affairs$",
                                  "^Society.*"]
                        ).proc(),
                    "MatchingBlockInterval":[6,6],
                    },
                }
            },
        
        }
        
    }

'''
BADS = reCombiner(
                        reList = [
                            reCombiner(
                                reList=[
                                    ".*Measbbles",
                                    ".*APO"],
                                ).proc(),
                            reCombiner(
                                reList=[
                                    ".*Measles",
                                    ".*APO"],
                                ).proc(),
                            ],
                        method = "and"
                        ).proc()

print("BADS",BADS)
import re
strA = "Measles Vaccine"
print("BADS",re.match(BADS,strA))
raise Exception
'''


MES = f"Start to load BinMissionDict_DRN from VisParameters_DRN_Sample and VisParameters_DRN"
MPLOGGER.logW(MES)
try:
    from VisParameters_DRN_Sample import BinMissionDict_DRN
    BinMissionDict.update(BinMissionDict_DRN)
    del(BinMissionDict_DRN)
    from VisParameters_DRN import BinMissionDict_DRN
    BinMissionDict.update(BinMissionDict_DRN)
    del(BinMissionDict_DRN)
    MES = f"Successfully loaded BinMissionDict_DRN, the BinMissionDict is now {BinMissionDict}"
    MPLOGGER.logW(MES)
except Exception as e:
    MES = f"When loading BinMissionDict_DRN, the following error occurs:\n{e}"
    MPLOGGER.logW(MES)
    

