import os
import multiprocessing as mp
import numpy as np
import pandas as pd
from utilities import timeNow

class MPlogger():
    def logW(MES=None, logFile="mp_processing_log.txt"):
        f = open(logFile, "at", encoding='utf8')
        MES = "PID {}: {}".format(os.getpid(), MES)
        f.write("{},{}\n".format(timeNow(FMT="%Y-%m-%d %H:%M:%S"),MES))
        f.close()
        
def Launcher(Job, method="run"):
    #記錄任務log。
    MES = "Run Job {}".format(Job)
    multicoreJob.logW(MES=MES)
    return getattr(Job, method)()
    
class multicoreJob:
    '''
    平行化任務執行管理器，將Job.method任務集送入平行化運算隊列；
    執行完畢後回傳res清單。
    DTBJobs：任務物件清單，任務執行方法為 Job.run()。
    '''
    def __init__(self, DTBJobs=None, method="run", MulticoreMode=False, nProcess=1):
        self.DTBJobs = DTBJobs
        self.method = method
        self.MulticoreMode = MulticoreMode
        self.nProcess = min(nProcess,len(DTBJobs))
        
    def logW(MES=None, logFile="mp_processing_log.txt"):
        f = open(logFile, "at", encoding='utf8')
        MES = "PID {}: {}".format(os.getpid(), MES)
        f.write("{},{}\n".format(timeNow(FMT="%Y-%m-%d %H:%M:%S"),MES))
        f.close()
        
    '''
    def add_features(df):
        if "The Economist" in df['file'].split("\\"):
            SampleExtractBound = nUpperBoundForSingleEconomist
        else:
            SampleExtractBound = nUpperBoundForSingleFile
        df['text_cut'] = df['file'].apply(
            lambda x:readSamepleForFile(x, width=256, Mode="FullCut")[0:SampleExtractBound])
        return df
    ''' 

    def parallelize_dataframe(self, df, func):
        #func: input:df output:another df
        if self.nProcess > 1:
            df_split = np.array_split(df, self.nProcess)
            pool = mp.Pool(self.nProcess)
            df = pd.concat(pool.map(func, df_split))
            pool.close()
            pool.join()
        else:
            df = func(df)
        return df

    def run(self):
        DTBJobs = self.DTBJobs
        method = self.method
        print("="*50)
        print("執行multicorejob.run()函式，前3個任務為")
        for Job in DTBJobs[0:3]:
            print('-'*50)
            Job.show()
        res = []
        if len(DTBJobs) == 1:
            self.MulticoreMode = False
            print("There is only one job. Deactive Multiprocessing.")
        
        #將單一任務執行結果新增至res列表，俟所有任務完成，最後再換成DataFrame，
        #進行存檔或資料視覺化顯示。
        if self.MulticoreMode == False:
            print("="*50)
            print(f"""Multiprocessing is nonactive now and try pretest.
                  If everything is fine, try active Multiprocessing."""
                  .replace("\n",""))
            print("="*50)
            for Job in DTBJobs:
                #print("now processing", Job)
                #Job.show()
                res.append(Launcher(Job, method))
        else:
            print("="*50)
            print(f"""Start Multiprocessing, if the system is halted.
                  try inactive the Multiprocessing and make the PGM could 
                  run without Error or Exception. Otherwise the processing 
                  may call subprocess INFINITLY resulting in stucking 
                  in the multiprocess procedure!""".replace("\n",""))
            print("="*50)
            pool = mp.Pool(self.nProcess)
            DTBJobs = [(Job,method) for Job in DTBJobs]
            res = pool.starmap(Launcher, DTBJobs)
            pool.close()
            pool.join()
        return res
