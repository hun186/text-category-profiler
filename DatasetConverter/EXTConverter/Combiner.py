import os
import glob
import datetime

if os.getcwd().split(os.path.sep)[-1] in [
        #"DatasetConverter","BertScript",
        "EXTConverter"]:
    os.chdir("../../")
    print(f"Change working directory to {os.getcwd()}")
from PackageImport import PackageImporter
PackageImporter.proc()

import math
import os
import tqdm
from utils.core.utilities import OSWALK
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
        
    def Transformer(self):
        df = dfFromSQLite3(self.SourceCZJSampleFN).reset_index(drop=True)
        df.drop(columns=[col for col in ["index", "ID"] if col in df.columns], inplace=True)
    
        corpus_list = []
    
        for src, src_df in df.groupby("file", sort=False):
            # 使用 mode() 取得最常出現的 InLabel
            inlabel = src_df["InLabel"].mode().iat[0] if not src_df["InLabel"].mode().empty else None
        
            # 組合 PartNO 文字內容
            text_list = list(zip(src_df["PartNO"], src_df["text"]))
            text_list.sort(key=lambda x: x[0])
            article_text = ''.join(text for _, text in text_list)
        
            sample = {
                "title": src,
                "InLabel": inlabel,
                "text": article_text,
                "FilePath": None,
                "url": None,
                "UpdatedTime": None,
            }
            corpus_list.append(sample)
    
        df_save = DictRowsListToDF(corpus_list)
        output_main = self.OutputCZJCorpusFN.rpartition(".")[0]
        dfOutputer(df_save, output_main, OutputFormat=["sql"], SQL_table="Corpus").run()

    def build_from_txt_folder(self, txt_folder_path):
        #txt_files = glob.glob(os.path.join(txt_folder_path, "**", "*.txt"), recursive=True)
        txt_files = OSWALK(txt_folder_path)
        print("txt_files",txt_files)
        corpus_list = []

        for txt_file in txt_files:
            title = os.path.splitext(os.path.basename(txt_file))[0]
            with open(txt_file, "r", encoding="utf-8") as f:
                text = f.read()

            # 嘗試從路徑中擷取 InLabel
            inlabel = None
            if "#T#[" in txt_file:
                try:
                    inlabel = txt_file.split("#T#[", 1)[1].split("]", 1)[0]
                except IndexError:
                    inlabel = None

            # 取得最後更新時間
            updated_time = datetime.datetime.fromtimestamp(os.path.getmtime(txt_file)).isoformat()

            sample = {
                "title": title,
                "InLabel": inlabel,
                "text": text,
                "FilePath": txt_file,
                "url": None,
                "UpdatedTime": updated_time
            }
            corpus_list.append(sample)

        df_save = DictRowsListToDF(corpus_list)
        output_main = self.OutputCZJCorpusFN.rpartition(".")[0]
        dfOutputer(df_save, output_main, OutputFormat=["sql"], SQL_table="Corpus").run()
        
def transform_segmented_sql3_to_czj():
    EXTCVPath = r"D:\shared\TopicClassification\DatasetConverter\EXTConverter"
    SourceCZJSampleFN = os.path.join(EXTCVPath, "Input", "dataset_total_with_filename_FixedTest.sql3")
    OutputCZJCorpusFN = os.path.join(EXTCVPath, "Output", "CZJ_CorpusFile.sql3")

    print(os.path.isfile(SourceCZJSampleFN))
    print(OutputCZJCorpusFN, os.path.isfile(OutputCZJCorpusFN))

    CZJCorpusFileBuilder(
        SourceCZJSampleFN=SourceCZJSampleFN,
        OutputCZJCorpusFN=OutputCZJCorpusFN,
    ).Transformer()

def test_build_from_txt():
    txt_folder = r"D:\shared\TopicClassification\TopicTextCrawler\Books\特定主題\電郵文本\#T#[Ransomware Notes]"
    OutputCZJCorpusFN = r"D:\shared\TopicClassification\DatasetConverter\EXTConverter\CZJ_CorpusFile_from_Ransomware_Notes_txt.sql3"
    builder = CZJCorpusFileBuilder(OutputCZJCorpusFN=OutputCZJCorpusFN)
    #print("builder",builder)
    builder.build_from_txt_folder(txt_folder)

if __name__ == '__main__':
    #transform_segmented_sql3_to_czj()
    test_build_from_txt()  # 若需執行 txt → corpus，取消這行註解
