import os
import time
import multiprocessing as mp
import re
import hashlib

def CapWords(s):
    lst = [word[0].upper() + word[1:] for word in s.split()]
    return " ".join(lst)

def OSWALK(ROOTPATH, Extension = None):
    result = []
    for dirPath, dirNames, fileNames in os.walk(ROOTPATH):
        for f in fileNames:
            if Extension == None or f.endswith(Extension):
                result.append(os.path.join(dirPath, f))
    return result

def timeNow(FMT = "%Y%m%d%H%M%S"):
    return time.strftime(FMT, time.localtime())

def ShowElapsedTime(start_time):
    elapsed_time = time.time() - start_time
    print("It has been passed for {:.4f} seconds".format(elapsed_time)) 

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
    return [x for x in List1 if x not in s]
def ListCap(List1,List2):#Output:List1-List2
    return list(set(List1) & set(List2))

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
    e.g: known_pictures\Hong Kong\artist\Aaron Kwok[3].jpg => Aaron Kwok[3].jpg
    '''
    return FN.split("\\")[-1]

def LinkFiller(Link, CtrlPath):
    CtrlDir = "/".join(CtrlPath.split("/")[:-1])
    HomeLink = "/".join(CtrlPath.split("/")[0:3])
    if Link.startswith("/"):
        Link = HomeLink+Link
    elif Link.startswith("#"):
        Link = CtrlPath.split("#")[0]+"#"+Link.split("#")[1]
    elif Link.startswith("."): #../* or ./*
        print("CtrlPath", CtrlPath)
        SubPath = Link.split("/")
        RemoveCtrlPathLevel = (
            SubPath[0]==".")*1+(SubPath[0]=="..")*2+sum(
            [(x=="..")*1 for x in SubPath[1:]])
        print("RemoveCtrlPathLevel", RemoveCtrlPathLevel)
        print("Link", Link)
        Link = "/".join(CtrlPath.split("/")[:min(-RemoveCtrlPathLevel+1,-1)]+[
            x for x in SubPath if x not in [".",".."]])
        print("Link af", Link)
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

def MKDIR(DirName):
    os.makedirs(DirName, exist_ok=True)
    
def RemoveIlleagalCharForFileName(title):
    result = title
    IlleagalSet = ['/','\\',':','?','\"','<','>','|','\n','\xa0','\t','*']
    for x in IlleagalSet:
        result = result.replace(x,"_")
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