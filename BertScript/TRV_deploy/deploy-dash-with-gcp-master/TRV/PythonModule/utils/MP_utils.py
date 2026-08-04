import os
import multiprocessing as mp
import numpy as np
import pandas as pd
import time
import random
#from utilities import timeNow
import psutil

def timeNow(FMT = "%Y%m%d%H%M%S"):
    return time.strftime(FMT, time.localtime())

class MPlogger():
    def logW(MES=None, logFile="mp_processing_log.txt", printOnScreen=True):
        return
        logFile = os.path.join('/tmp',logFile)
        f = open(logFile, "at", encoding='utf8')
        MES = "PID {}: {}".format(os.getpid(), MES)
        if printOnScreen == True:
            print(MES)
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
    def __init__(self, DTBJobs=[], method="run",
                 #MulticoreMode=False,
                 nProcess=1):
        random.shuffle(DTBJobs)
        #print("In MU DTBJobs", DTBJobs[0:3])
        self.DTBJobs = DTBJobs
        self.method = method
        if nProcess > 1:
            self.MulticoreMode = True
        else:
            self.MulticoreMode = False
        #self.MulticoreMode = MulticoreMode
        if DTBJobs != []:
            self.nProcess = min(nProcess,len(DTBJobs))
        else:
            self.nProcess = nProcess
        
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
        print("呼叫DataFrame平行化函數套用功能，進程數為 {}".format(
            self.nProcess))
        if self.nProcess > 1:
            df_split = np.array_split(df, self.nProcess)
            pool = mp.Pool(self.nProcess)
            df = pd.concat(pool.map(func, df_split))
            pool.close()
            pool.join()
        else:
            df = func(df)
        return df

    def ComputeNProcess(self,):
        nCPU = mp.cpu_count()
        if nCPU > 30:
            nProcess = int(nCPU*1.3)
        else:
            nProcess = nCPU
        MES = f"The basic number of Process is defined to {nProcess}."
        MPlogger.logW(MES=MES)
        MES = "進程數設定為{}，請依硬體CPU資源數量，妥善設定進程數量，以免程式崩潰！\
            如果沒有把握，請將進程數設為1，以策安全。".format(nProcess)
        MPlogger.logW(MES=MES)
        return nProcess
    
    def ComputeSPCNProcess(self,):
        AvaMem = psutil.virtual_memory().available
        nProcessSPC = int(AvaMem/(3*1024*1024*1024))
        MES = f"The SPC number of Process is defined to {nProcessSPC}."
        MPlogger.logW(MES=MES)
        MES = "經考量剩餘記憶體，進程數設定為{}，請依硬體CPU資源數量，妥善設定進程數量，以免程式崩潰！\
            如果沒有把握，請將進程數設為1，以策安全。".format(nProcessSPC)
        MPlogger.logW(MES=MES)
        return nProcessSPC
            
    def run(self):
        DTBJobs = self.DTBJobs
        method = self.method
        print("="*50)
        print(f"執行multicorejob.run()函式，共有{len(DTBJobs)}個任務，前3個任務為")
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
