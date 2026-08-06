import os
import time
import multiprocessing as mp
import re
import hashlib
import shutil
import datetime
import pathlib
import platform
from text_category_profiler.concurrency.MP_utils import MPlogger

class VariableChangeDetector:
    """ A simple class, set to watch its variable. """
    def __init__(self, name, value):
        self.name = name
        self.variable = value   
    def proc(self, new_value):
        if new_value != self.variable:
            self.variable = new_value
            return True
        else:
            return False

class fileNameNormalizer:
    def proc(fileName):
        '''
        if os.path.sep == "\\":
        #if "windows" in platform.system().lower():
            return fileName.replace("/","\\")
        else:
            return fileName.replace("\\","/")
        '''
        return fileName.replace("\\","/")

def PathSEP(filePath):
    if "/" in filePath:
        SEP = "/"
    elif "\\" in filePath:
        SEP = "\\"
    else:
        SEP = os.path.sep
    return SEP

class pathSpliter:
    def proc(filePath):
        filePath = fileNameNormalizer.proc(filePath)
        return filePath.split(PathSEP(filePath))


class fileNameReplacer:
    def proc(ROOTPATHList,ReplaceDict = {},
             ReplaceDirNameOnly=False,RemoveEmptyFolder = False):
        counter = 0
        for ROOTPATH in ROOTPATHList:
            for file in OSWALK(ROOTPATH):
                #print("dealing {}".format(file))
                src = fileNameNormalizer.proc(file)
                des = src
                for key in ReplaceDict.keys():
                    desSubDir = des.rpartition("/")[0]
                    if ReplaceDirNameOnly == False:
                        des = des.replace(key, ReplaceDict[key])
                    elif ReplaceDirNameOnly == True:
                        desSubDir = desSubDir.replace(key, ReplaceDict[key])
                        des = os.path.join(desSubDir,getFNFromFullPath(des))
                des = fileNameNormalizer.proc(des)
                
                if src != des:
                    srcSubDir = src.rpartition("/")[0]#'/'.join(pathSpliter.proc(src)[:-1])
                    desSubDir = des.rpartition("/")[0]#'/'.join(pathSpliter.proc(des)[:-1])
                    MKDIR(desSubDir)
                    shutil.move(src, des)
                    MES = "Move {} to {}".format(src,des)
                    MPlogger.logW(MES,logFile="ReNameLog.txt")
                    if RemoveEmptyFolder == True and len(os.listdir(srcSubDir)) == 0:
                        shutil.rmtree(srcSubDir)
                    counter += 1
        MES = "="*50+"\nThere are totally {} files renamed.".format(counter)
        MPlogger.logW(MES,logFile="ReNameLog.txt")

'''
def pathSeqFromFN(file):
    file = fileNameNormalizer.proc(file)
    return file.split("/")
'''


def OSWALK(ROOTPATH, Extension = []):
    if type(Extension) == str:
        Extension = [Extension]
    result = []
    for dirPath, dirNames, fileNames in os.walk(ROOTPATH):
        for f in fileNames:
            if Extension == [] or any(f.endswith(x) for x in Extension):
                result.append(os.path.join(dirPath, f))
    result = [fileNameNormalizer.proc(x) for x in result]
    return result

class Prefixer:
    def __init__(self, inputObj="", prefix="",):
        self.inputObj = inputObj
        self.prefix = prefix
    def proc(self, inputObj):
        return self.prefix + inputObj
    def run(self):
        return self.inputObj+self.prefix

class Replacer:
    def __init__(self, Map={}):
        self.Map = Map
    def proc(self, inputObj):
        result = inputObj
        for key in self.Map.keys():
            result = result.replace(key, self.Map[key])
        return result

class TextNormalizer:
    def __init__(self, Map={}):
        if Map == {}:
            for removeChar in ['\0','\u3000','\t', '\ufeff']:
                Map[removeChar] = ""
            Map.update({'"':'“',"'":"’"})
        self.Map = Map
    def proc(self, inputObj):
        result = inputObj
        return Replacer(Map = self.Map).proc(inputObj)
    
class LineBreaker:
    def __init__(self, BreakPattern=[]):
        self.BreakPattern = BreakPattern
    def proc(self, inputObj):
        result = inputObj #string
        for pat in self.BreakPattern:
            result = result.replace(
                pat, pat+"\n").replace("\n\n","\n").replace("\n ","\n")
        return result
        
class OptionLineBreaker:
    def __init__(self, OptionPattern=[]):
        self.OptionPattern = OptionPattern
    def proc(self, inputObj):
        result = inputObj #string
        for pat in self.OptionPattern:
            if inputObj.startswith(pat) and inputObj.strip() != pat:
                result = inputObj.replace(
                    pat+" ", pat).replace(pat, pat+"\n")
                break
        return result
        
class VersionPicker:
    def __init__(self, Option="Verno"):
        self.Option = Option
    def proc(self, inputObj):#inputObj:List of string
        result = inputObj
        VerDict = {}
        if Option == "Verno":
            for x in inputObj:
                VerCand = re.findall("\d+",x)
                if VerCand == []:
                    VerCand = [0]
                    
                
                NewestItem = sorted(A.items(),key = lambda x:x[1])[-1]
                NewestEle = NewestItem[0]
                return NewestEle

class textReader:
    def __init__(self, file, 
                 encoding = "utf-8",
                 nBytes=None
                 ):
        self.file = file
        self.encoding = encoding
        self.nBytes = nBytes
    def run(self,):
        #讀取文本。
        nullReturn = ""
        try:
            text = open(
                self.file, mode="rt", encoding=self.encoding).read(self.nBytes).replace("\0","")
        except UnicodeDecodeError:
            try:
                MES = "Fail to use utf-8 to read file {}.\n".format(
                    self.file)
                MPlogger.logW(MES)
                text = open(
                    self.file, mode="rt").read(self.nBytes).replace("\0","")
            except:
                pass
                MES = "Fail to use cp950 to read file {}.\n".format(
                    self.file)
                MPlogger.logW(MES)
                return nullReturn
        return text
        
class TxtFileHashDictBuilder:
    def __init__(self, fileList, hashalg = "md5", nBytes = None):
        self.fileList = fileList
        self.nBytes = nBytes
        self.hashalg = hashalg
    def show(self,):
        print("="*50)
        print("fileList[0:3]:", self.fileList[0:3])
    def run(self):
        hashDict = {}
        ndup = 0
        for file in self.fileList:
            ctx = textReader(file).run()
            #ctx = open(file,'rt',encoding='utf-8').read(1000000)
            #print(ctx)
            hashval = hash(ctx, self.hashalg)
            if hashval in hashDict.keys():
                ndup += 1
            #hashDict[hashval] = file
            hashDict[file] = hashval
        return hashDict

class ListDivider:
    def proc(List, ratioList = [0.5,0.5]):
        if sum(ratioList) != 1:
            SUMR = sum(ratioList)
            ratioList = [x/SUMR for x in ratioList]
        result = []
        LenL = len(List)
        #cutIdxList
        CIL = [int(sum(ratioList[:i+1])*LenL)
               for i,ratio in enumerate(ratioList)]
        CIL.insert(0,0)
        print("CIL",CIL)
        if CIL[-1] != LenL:
            CIL[-1] == LenL
        for i in range(len(CIL)-1):
            print(CIL[i],CIL[i+1])
            result.append(List[CIL[i]:CIL[i+1]])
        return result
    
def CapWords(s, ignorePreposition = True):
    #print("CapWords", s)
    if all([ignorePreposition,
            s in ["and","of","to","on","above","below","under",
                  "at","a","an","the"],
            ]):
        return s
    else:
        lst = [word[0].upper() + word[1:] for word in s.split()]
        return " ".join(lst)
        




def timeNow(FMT = "%Y%m%d%H%M%S"):
    return time.strftime(FMT, time.localtime())

def getFileModTime(file):
    fname = pathlib.Path(file)
    try:
        result = datetime.datetime.fromtimestamp(int(fname.stat().st_mtime))
    except:
        result = None
    return result

def ShowElapsedTime(start_time):
    elapsed_time = time.time() - start_time
    print("It has been passed for {:.4f} seconds".format(elapsed_time))
    
def ShowStepCostTime(start_time, JobName = ""):
    elapsed_time = time.time() - start_time
    print("It cost {:.4f} seconds for this job {}".format(elapsed_time, JobName)) 

def UniqueList(InputList):
    result = []
    for x in InputList:
        if x not in result:
            result.append(x)
        else:
            continue
    return result
def ListDiff(List1,List2):#Output:List1-List2
    s = set(List2)
    print("List1, List2",List1, List2)
    return [x for x in List1 if x not in s]

def ListCap(List1,List2):#Output:List1-List2
    return list(set(List1) & set(List2))

def SplitList(data, nChunks = 2):
    result = []
    nElemInSubList = int(len(data)/nChunks)
    cong = len(data) % nChunks
    #if len(data) % nChunks != 0:
        #nElemInSubList += 1
    for i in range(nChunks):
        if i <= cong-1:
            chunk = data[0:nElemInSubList+1]
            data = data[nElemInSubList+1:]
        else:
            chunk = data[0:nElemInSubList]
            data = data[nElemInSubList:]
        result.append(chunk)
    return result
    return [
        data[x:x+nElemInSubList] 
        for x in range(0, len(data), nElemInSubList)]

def CheckStringWithPatterns(string, PatternList):
    for pat in PatternList:
        if pat in string:
            return True, pat
    return False, None

def CheckStringWithRePatterns(string, RePatternDict):
    '''
    RePatternDict = {
        "setn.com":["^((?!News.aspx).)*$"],
        "mirrormedia.mg":[".*/category/.*",
                         ".*/section/.*"],
                    ]
    '''
    for key in RePatternDict.keys():
        if key in string:
            for regex in RePatternDict[key]:                
                if re.match(regex,string) != None:
                    return True, regex
    return False, None

def getMFNFromFN(FN):
    '''
    e.g: known_pictures\Hong Kong\artist\Aaron Kwok[3].jpg => Aaron Kwok[3]
    '''
    return FN.split(PathSEP(FN))[-1].rpartition(".")[0]


def getFNFromFullPath(FN):
    '''
    e.g: known_pictures\Hong Kong\artist\Aaron Kwok[3].jpg => Aaron Kwok[3].jpg
    '''
    return FN.split(PathSEP(FN))[-1]


def getFileDirFromFN(FN):
    '''
    e.g: known_pictures\Hong Kong\artist\Aaron Kwok[3].jpg => Aaron Kwok[3].jpg
    '''
    FN = fileNameNormalizer.proc(fileName = FN)
    FileDir = FN.rpartition("/")[0]
    if FileDir == "":
        FileDir = "./"
    return FileDir

def LinkFiller(Link, CtrlPath, SpecLinkFiller=None):
    if SpecLinkFiller != None:
        if Link.startswith("http"):
            return Link
        #{"re":"http://www.ccpit.org/.*/","method":"concatenate"},
        expr = SpecLinkFiller["re"]
        method = SpecLinkFiller["method"]
        print("expr, CtrlPath", expr, CtrlPath)
        prefix = re.findall(expr,CtrlPath)[0]
        #print("prefix", prefix)
        if method == "concatenate":
            print("after concatenate, the link is", prefix+Link)
            return prefix+Link
    else:
        CtrlDir = "/".join(CtrlPath.split("/")[:-1])
        HomeLink = "/".join(CtrlPath.split("/")[0:3])
        if Link.startswith("//"):
            Link = "https:"+Link
        elif Link.startswith("/"):
            Link = HomeLink+Link
        elif Link.startswith("#"):
            Link = CtrlPath.split("#")[0]+"#"+Link.split("#")[1]
        elif Link.startswith("."): #../* or ./*
            print("CtrlPath", CtrlPath)
            '''
            SubPath = Link.split("/")
            RemoveCtrlPathLevel = (
                SubPath[0]==".")*1+(SubPath[0]=="..")*2+sum(
                [(x=="..")*1 for x in SubPath[1:]])
            print("RemoveCtrlPathLevel", RemoveCtrlPathLevel)
            print("Link", Link)
            Link = "/".join(CtrlPath.split("/")[:min(-RemoveCtrlPathLevel+1,-1)]+[
                x for x in SubPath if x not in [".",".."]])
            print("Link af", Link)
            '''
            print("CtrlDir", CtrlDir)
            Link = CtrlDir + "/"+Link
            #Link = CtrlDir+'.'.join(Link.split(".")[1:])
        #elif (not Link.startswith("http")) and ("aspx" in Link):
        elif (not Link.startswith("http")) and (not Link.startswith("/")):
            Link = HomeLink+"/"+Link
    return Link

def LinkFillerOld(Link, CtrlPath):
    CtrlDir = "/".join(CtrlPath.split("/")[:-1])
    HomeLink = "/".join(CtrlPath.split("/")[0:3])
    if Link.startswith("."):
        Link = CtrlDir+'.'.join(Link.split(".")[1:])
    elif Link.startswith("/"):
        Link = HomeLink+Link
    elif Link.startswith("#"):
        Link = CtrlPath.split("#")[0]+"#"+Link.split("#")[1]
    #elif (not Link.startswith("http")) and ("aspx" in Link):
    elif (not Link.startswith("http")) and (not Link.startswith("/")):
        Link = HomeLink+"/"+Link
    return Link

def BackUp(FileName):
    if "." in FileName:
        ext = FileName.split(".")[-1]
        dst = FileName.replace(ext,"_{}.{}".format(timeNow(),ext))
    else:
        dst = FileName + ext,timeNow()
    MES = "Backuping file {} as {}".format(FileName, dst)
    MPlogger.logW(MES)
    shutil.copyfile(FileName, dst)
                    
def MKDIR(DirName):
    os.makedirs(DirName, exist_ok=True)
    
def RemoveIlleagalCharForFileName(title, Mode = "FileName"):
    result = title
    if Mode == "FileName":
        IlleagalSet = ['/','\\',':','?','\"','<','>','|','\n','\xa0','\t','*']
        IlleagalMapDict = {}
        for x in IlleagalSet:
            IlleagalMapDict[x] = "_"
    if Mode == "Latex":
        IlleagalMapDict = {}
        IlleagalMapDict["_"] = " "
        IlleagalMapDict["&"] = "\&"
        IlleagalMapDict["%"] = "\%"
        IlleagalMapDict["#"] = "＃"
    for x in IlleagalMapDict.keys():
        result = result.replace(x,IlleagalMapDict[x])
    return result

def RemoveIlleagalCharForFileNameForLatex(text):
    result = text
    IlleagalSet = ['/','\\',':','?','\"','<','>','|','\n','\xa0','\t','*']
    for x in IlleagalSet:
        result = result.replace(x,"_")
    return result

class strQ2BConverter:
    """ 全型字母、數字、括弧、空白轉半型 """
    def __init__(self):
        src = "１２３４５６７８９０ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）［］　"
        des = "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz()[] "
        self.convertDict = dict(zip(src,des))
    def proc(self, text):
        result = text
        for x in self.convertDict.keys():
            result = result.replace(x, self.convertDict[x])
        return result
        
        
def hash(data, method="sha512"):
    m = getattr(hashlib, method)()
    if data == None:
        return None
    try:
        m.update(data)
    except:
        data = data.encode('utf-8')
        m.update(data)
    return m.hexdigest()

def wrap(s, w):
    return [s[i:i + w] for i in range(0, len(s), w)]

def OffsetWrap(s, StartOffset, ChunkUnit):
    return [s[i:i + ChunkUnit] for i in range(0, len(s), StartOffset)]

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    '''
    return [ atoi(c) for c in re.split(r'(\d+)', text) ]

def removekey(d, key):
    r = dict(d)
    del r[key]
    return r