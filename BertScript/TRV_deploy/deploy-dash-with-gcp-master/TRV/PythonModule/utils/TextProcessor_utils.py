import re
from utils.utilities import AppendedMFN

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

def removeLinesWithPattern(inputFileName, outputFileName=None,RePatternDict = None):
    if RePatternDict == None:
        print("WARNING! There is NO Pattern Input! Abort!")
        return
    
    if outputFileName == None:
        
        outputFileName = AppendedMFN(inputFileName,appendStr="_removeLine")
    print("outputFileName is",outputFileName)
    input = open(inputFileName, "rt",encoding='utf-8')
    output = open(outputFileName, "wt",encoding='utf-8')

    #output.write(input.readline())

    for line in input:
        if CheckStringWithRePatterns(line,RePatternDict)[0] == False:
            output.write(line)

    input.close()
    output.close()