import os
if os.getcwd().split(os.path.sep)[-1] in [
        #"DatasetConverter","BertScript",
        "EXTConverter"]:
    os.chdir("../../")
    print(f"Change working directory to {os.getcwd()}")
print(f"cwd:{os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import math
import os
import tqdm
from utils.core.utilities import getPathFromFN
from utils.core.utilities import getMFNFromFN
from utils.data.df_utils import DictRowsListToDF
from utils.data.df_utils import dfFromSQLite3
from utils.data.df_utils import dfOutputer
from utils.data.DB_utils import createTable
from utils.data.DB_utils import createIndex

class EmbassyPagesCombiner:
    def __init__(self, 
                 ROOTPATH = r"D:\shared\TopicClassification\TopicTextCrawler\C_EmbassyPages-Located Country",
                 nSubtaskUBD = math.inf,
                ):
        self.ROOTPATH = ROOTPATH
        self.nSubtaskUBD = nSubtaskUBD
    def CheckMission(self,file,sample,Mission):
            if Mission not in [
                '','Consulate General','Embassy Office',
                'Embassy Branch Office','Permanent Mission',
                'Administrative Office','Embassy','Interest Section',
                'Representative Office','Delegation','Apostolic Nunciature',
                'Vice Consulate','Government Office',
                'Deputy High Commission','Consul','Trade Office',
                'Consular Agency','High Commission','Governor’S Office',
                'Permanent Representation','Consulate',
                'Permanent Observer Mission','Mission',
                'Apostolic Delegation'
                ]:
                print("="*50)
                print(file)
                print(sample)
    def proc(self,):
        Fields = [x.lstrip("=") for x in os.listdir(
            self.ROOTPATH) if x.startswith("=")]
        print("Fields",Fields)
        rows_list = []
        RecCountryList = os.listdir(os.path.join(self.ROOTPATH,"=Address"))
        #AddPath = os.path.join(ROOTPATH,"=Address")
        #AddPath = os.path.join(ROOTPATH,"=Address")
        cnt = 0
        if self.nSubtaskUBD == math.inf:
            self.nSubtaskUBD = len(RecCountryList)
        for ReceivingCountry in tqdm.tqdm(RecCountryList[:self.nSubtaskUBD]):
            for file in os.listdir(os.path.join(self.ROOTPATH,"=Address",ReceivingCountry)):
                #print("file",file)
                #if cnt % 1000 == 0:
                    #print(f"Handled {cnt} samples")
                SendingCountry,_,CityMission = getMFNFromFN(file).partition(", ")
                CMS = CityMission.split(" - ")
                LocatedCity = CMS[0]
                if len(CMS) >=2:
                    Mission = CMS[1]
                else:
                    Mission = ""
                sample = {
                    "Receiving Country":ReceivingCountry,
                    "Sending Country":SendingCountry,
                    "Located City":LocatedCity,
                    "Mission":Mission,
                    }
                for field in Fields:
                    FN = os.path.join(self.ROOTPATH,f"={field}",ReceivingCountry,file)
                    if os.path.isfile(FN):
                        value = open(FN,'rt',encoding='utf-8').read()
                        sample[field] = value
                    if field == "Email":
                        sample["Domain Name List"] = []
                        #DNcnt = 1
                        EmailLines = sample["Email"].split("\n")
                        while(len(EmailLines)>0):
                            EMLine = EmailLines.pop()
                            #sample[f"Domain Name {DNcnt}"] = EMLine.split("@")[1] if len(EMLine) > 0 else ""
                            if "@" in EMLine:
                                sample["Domain Name List"].append(EMLine.split("@")[1])
                            #DNcnt += 1
                        sample["Domain Name List"]='\n'.join(sample["Domain Name List"])
                        #sample["Domain Name"] = sample["Email"].split("@")[1] if len(sample["Email"]) > 0 else ""
                self.CheckMission(file,sample,Mission)
                rows_list.append(sample)
                #cnt += 1
        df = DictRowsListToDF(rows_list)
        print("df.columns",df.columns)
        OUTPUTMAIN = os.path.join("DatasetConverter","EXTConverter","Output","EmbassyPages","EmbassyPages")
        dfOutputer(df, OUTPUTMAIN).run()

#%%#################初始化資料庫檔案#################
def CreateCZJCorpusSQL(
        sql3File = "CZJCorpusSQL.sql3",
        table = "Corpus",
        ):
    print("For CreateCZJCorpusSQL,sql3File",sql3File)
    ColDict={
        "title":{
            "datatype":"TEXT",
            #"property":"NOT NULL PRIMARY KEY",
            },
        }
    for project in ["InLabel","text","FilePath","url","UpdatedTime"]:
        ColDict[project] = {
            "datatype":"TEXT",
            }
    print("For CreateCZJCorpusSQL,ColDict",ColDict)
    
    createTable(
        sql3File,table,
        ColDict=ColDict,
        )
    createIndex(
        SQLname = sql3File,
        table = table,
        IndexCol = "title",
        uniqueIndex=False)
    
class CZJCorpusFileBuilder:
    def __init__(self, 
                 SourceCZJSampleFN = "",
                 OutputCZJCorpusFN = "",
                ):
        self.SourceCZJSampleFN = SourceCZJSampleFN
        self.OutputCZJCorpusFN = OutputCZJCorpusFN
    def Transformer(self,):
        df = dfFromSQLite3(self.SourceCZJSampleFN).reset_index(drop=True)
        #移除index Column，CZJ標準index Col Name是"index"，
        #WeiTech的index Column非標準，設定為"ID"
        for indexCol in ["index","ID"]:
            if indexCol in df.columns:
                df = df.drop(columns=[indexCol])
                break
        #print("df in Transformer",df)
        SrcList = set(df["file"])
        CorpList = []
        for Src in SrcList:
            #print("="*50)
            #print("Src",Src)
            #使用出現最多的類別做為整篇的類別
            lst = list(df["InLabel"])
            InLabel = max(lst,key=lst.count)
            #取出切片編號、文字內容
            SrcRows = df[df["file"]==Src][["PartNO","text"]].iterrows()
            textList = [(dfrow[0],dfrow[1]) for idx,dfrow in SrcRows]
            #按切片編號順序排序
            textList = sorted(textList,key=lambda x:x[0])
            #組合切片文字為單篇文本
            articleText = ''.join([text for PN,text in textList])
            #print("articleText",articleText)
            sample = {
                "title":Src,
                "InLabel":InLabel,
                "text":articleText,
                "FilePath":None,
                "url":None,
                "UpdatedTime":None,
                }
            CorpList.append(sample)
        #print("CorpList",CorpList)
        #print("~"*50)
        #print("self.OutputCZJCorpusFN",self.OutputCZJCorpusFN)
        #後面的dfOutputer會直接取代table，故CreateCZJCorpusSQL無實際作用，暫時mark。
        #CreateCZJCorpusSQL(sql3File=self.OutputCZJCorpusFN)
        df_Save = DictRowsListToDF(CorpList)
        OUTPUTMAIN = self.OutputCZJCorpusFN.rpartition(".")[0]
        dfOutputer(df_Save, OUTPUTMAIN, OutputFormat=["sql"], SQL_table="Corpus").run()

if __name__=='__main__':
    EXTCVPath = r"D:\shared\TopicClassification\DatasetConverter\EXTConverter"
    SourceCZJSampleFN=os.path.join(EXTCVPath,"input","dataset_total_with_filename_FixedTest.sql3")
    OutputCZJCorpusFN=os.path.join(EXTCVPath,"Output","CZJ_CorpusFile.sql3")
    print(os.path.isfile(SourceCZJSampleFN))
    print(OutputCZJCorpusFN,os.path.isfile(OutputCZJCorpusFN))
    CZJCorpusFileBuilder(
        SourceCZJSampleFN=SourceCZJSampleFN,
        OutputCZJCorpusFN=OutputCZJCorpusFN,
        ).Transformer()
        