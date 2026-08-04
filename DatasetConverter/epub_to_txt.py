import ebooklib
from ebooklib import epub
import os
from bs4 import BeautifulSoup
import docx2txt
#from win32com import client as wc
#import docx
#import textract

def OSWALK(ROOTPATH):
    result = []
    for dirPath, dirNames, fileNames in os.walk(ROOTPATH):
        for f in fileNames:
            result.append(os.path.join(dirPath, f))
    return result


def doSaveAas(file):
    word = wc.Dispatch('Word.Application')
    doc = word.Documents.Open(file)        # 目標路徑下的檔案
    doc.SaveAs(file.replace(".doc",".docx"), 12, 
               False, "", True, "", False, 
               False, False, False)  # 轉化後路徑下的檔案    
    doc.Close()
    word.Quit()

ROOTPATH = ".\\"
#ROOTPATH = ".\\经济预测分析-2016\\"
ROOTPATH = r"D:\VirtualBox VMs\shared\rdy To OCR"
ROOTPATH = r"H:\bought pdf\= 好讀 =\奇幻小說\劉慈欣\《三體》"
for file in OSWALK(ROOTPATH):
    print(file)
    if file.endswith(".epub"):
        book = epub.read_epub(file)
        OUTPUT = file.replace(".epub",".txt")
        with open(OUTPUT,'wt',encoding='utf-8') as f:
            for doc in list(
                    book.get_items_of_type(ebooklib.ITEM_DOCUMENT)):
                soup = BeautifulSoup(doc.content, 'html.parser')
                f.write(soup.text)
        print("file {} is converted.".format(file))

    elif file.endswith(".doc"):
        #doSaveAas(file)
        #text = docx2txt.process(file.replace(".doc",".docx"))
        #text = docx2txt.process(file.replace(".doc",".docx"), "/tmp/img_dir")
        #file = "./经济预测分析-2016/第36期 上半年消费形势分析及全年预测.doc"
        text = textract.process(file)
        print(text)

    elif file.endswith(".png"):
        file = "1.png"
        print(file)
        #doSaveAas(file)
        #text = docx2txt.process(file.replace(".doc",".docx"))
        #text = docx2txt.process(file.replace(".doc",".docx"), "/tmp/img_dir")
        #file = "./经济预测分析-2016/第36期 上半年消费形势分析及全年预测.doc"
        text = textract.process(file)
        print(text)
        
    elif file.endswith(".docx"):
        # extract text
        text = docx2txt.process(file)
        print(text)
        # extract text and write images in /tmp/img_dir
        text = docx2txt.process(file, "/tmp/img_dir")
