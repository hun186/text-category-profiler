import random
import os
from PackageImport import PackageImporter
PackageImporter.proc()
from text_category_profiler.core.utilities import MKDIR

#依照樣本數量取樣。
def PickSamples(THUCdir, ntrain, ndev, ntest):
    trainSampleList = []
    devSampleList = []
    testSampleList = []
    #計算各類型資料集樣本佔全部資料集樣本數比例
    sampleSum = ntrain + ndev + ntest
    ntrainRatio = ntrain/sampleSum
    ndevRation = ndev/sampleSum
    for label in os.listdir(THUCdir):
        #抓取標籤目錄
        labelDir = os.path.join(THUCdir, label)
        #抓取該標籤目錄之檔案列表
        files = os.listdir(labelDir)
        #如果特定標籤抽樣母體數量過少，則該標籤減少取樣
        labelSampleSum = min(sampleSum, len(files)) 
        sampleList = random.sample(files, k=labelSampleSum)
        trainEnd = int(labelSampleSum*ntrainRatio)
        devEnd = int(labelSampleSum*(ntrainRatio+ndevRation))
        #針對各資料集，取出各標籤所使用樣本文檔
        trainSampleList.extend([(label,file) for file in sampleList[:trainEnd]])
        devSampleList.extend([(label,file) for file in sampleList[trainEnd:devEnd]])
        testSampleList.extend([(label,file) for file in sampleList[devEnd:]])
    #打亂樣本集順序
    random.shuffle(trainSampleList)
    random.shuffle(devSampleList)
    random.shuffle(testSampleList)
    return trainSampleList, devSampleList, testSampleList
#資料集創建程式
def WriteTo_tsv(THUCdir, trainSampleList, devSampleList, testSampleList):
    for setName, Samples in [("train",trainSampleList),
                            ("dev",devSampleList), ("test",testSampleList)]:
        FN = os.path.join(OutputDir,setName+".tsv")
        fw = open(FN,'a', encoding='utf8')
        print("Producing {} Set.".format(setName))
        for label,file in Samples:
            #設定標籤目錄
            labelDir = os.path.join(THUCdir, label)
            #讀取語料
            fr = open(os.path.join(labelDir,'{}'.format(file)), 'r', encoding='utf8')
            txt = fr.read()
            txt = txt.replace('\n', '')
            txt = txt.replace('\u3000', '')
            txt = txt.replace(' ', '')
            #每則文章最多取max_length個字
            txt = txt[:max_length]
            txt = label + '\t' + txt + '\n'
            fw.write(txt)
            fr.close()
        fw.close()

#THUCNews語料庫路徑
THUCdir = "data_set_THUC"
OutputDir = "THUC_txt"
MKDIR("THUC_txt")
#每則文章最多取max_length個字
max_length = 128
#定義訓練集、開發集與測試級每個類別要取的樣本數量
#ntrain = 8000
#ndev = 2000
#ntest = 1000
ntrain = 100
ndev = 0
ntest = 0

#隨機選取文檔，分配至訓練集、開發集與測試集
trainSampleList, devSampleList, testSampleList = PickSamples(THUCdir, ntrain, ndev, ntest)
print("trainSampleList", trainSampleList[0:10])
#raise Exception
#創建tsv格式之訓練集、開發集與測試級
WriteTo_tsv(THUCdir, trainSampleList, devSampleList, testSampleList)
