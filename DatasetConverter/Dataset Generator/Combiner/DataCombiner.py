import random
import datetime
#from JobTitleGenerator.jobtitlegenerator import generate_job_title
#from faker import Faker
import os
import locale

def MKDIR(DirName):
    if DirName == "":
        #print("DirName is empty string, skipping MKDIR(DirName).")
        return
    #fileNameNormalizer.proc(DirName)
    os.makedirs(DirName, exist_ok=True)


GreetingPhrases = [
    #Various official “best regards” alternatives
    "Cordially","Take care","Sending you the best","Respectfully",
    "All My Best","Best Wishes","Warm Wishes","Regards",
    "Sincerely","Speak With You Soon","Wishing You a Wonderful Day",
    "Warm Regards","Warmly",
    #Various informal “best regards” alternatives
    "Best","All the best","Cheers","Talk soon",
    "Looking forward to our next conversation",
    "Looking forward to hearing from you",
    "Have a wonderful day", "Have a wonderful weekend",
    "Happy weekend",
    #Ways to end an email with appreciation
    "Thank you for reading","I can’t thank you enough",
    "Many thanks","Thank you","With appreciation",
    "Thanks for your consideration","With gratitude",
    "Thanks again","Thank you for your time",
    "All my thanks","Thanks in advance",
    "I owe you one","Thanks a million",
    "Much appreciated","Thank you for everything",
    "Thanks for reading","Many thanks",
    "Thanks so much","Thanks for your help",
    "Let me know if you need anything",
    ]

SepChars = [" ",",",";","\n"]
EmailHeaderFields = [
    #{"from":"","mailto":"","cc":"","date":"date","subject":"subject"},
    {"from":"from:","mailto":"mailto:","cc":"cc:","date":"date:","subject":"subject:"},
    {"from":"from:","mailto":"mailto:","cc":"cc:","date":"sent:","subject":"subject:"},
    {"from":"sender:","mailto":"receiver:","cc":"copy:","date":"date:","subject":"subject:"},
    {"from":"sender:","mailto":"receiver:","cc":"copy:","date":"sent:","subject":"subject:"},
    {"from":"寄件人:","mailto":"收件人:","cc":"副本:","date":"日期:","subject":"主旨:"},
    {"from":"寄件人：","mailto":"收件人：","cc":"副本：","date":"時間：","subject":"主旨："},
    {"from":"寄件人:","mailto":"收件人:","cc":"抄送:","date":"時間：","subject":"標題:"},
    {"from":"寄件人：","mailto":"收件人：","cc":"抄送：","date":"发送时间：","subject":"主题："},
    {"from":"发送人：","mailto":"收件人：","cc":"抄送：","date":"送达时间：","subject":"主题："},
    ]

DateTimeFMTList = [
    "%a, %d %b %Y %H:%M:%S",
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S[%Z]",
    "%Y-%m-%dT%H:%M:%S[%z]",
    "%Y/%m/%dT%H:%M:%S",
    "%Y/%m/%dT%H:%M:%S[%Z]",
    "%Y/%m/%dT%H:%M:%S[%z]",
    "%d/%m/%Y T %H:%M:%S",
    "%d/%m/%Y T %H:%M:%S[%Z]",
    "%d/%m/%Y T %H:%M:%S[%z]",
    ]

nBigPool = 20000
#nBigPool = 200
#nGen = 6000
nGen = 100
if nGen < nBigPool:
    nBigPool = nGen

#產生亂數選擇池
def GeneratePool(LocaleName):
    locale.setlocale(locale.LC_ALL,LocaleName)
    global fake,Names,JobTitles,CountryCallingCodes
    global PhoneNumberTitles,PhoneNumbers,EmailTitles,CompanyEmails
    global CompanyNames,HomepageUrls
    global AddressTitles,Addresses,Cities
    global UserAgents
    global RandomDatetimes
    #global MimeTypes
    global MessageIDs,ContentTransferEncodings
    fake = Faker(LocaleName)
    Names = [fake.name() for i in range(nBigPool)]
    #JobTitles = [generate_job_title() for i in range(10000)]
    JobTitles = [fake.job() for i in range(10000)]
    CountryCallingCodes = [fake.country_calling_code() for i in range(1000)]
    PhoneNumberTitles = ["TEL","Mobile","Mob.","Cell"]
    PhoneNumbers = [fake.phone_number() for i in range(nBigPool)]
    EmailTitles = ["E-mail:","Email:",""]
    CompanyEmails = [fake.ascii_company_email() for i in range(nBigPool)]
    #company_prefix不含"有限公司"結尾，company有含
    try:
        CompanyNames = [fake.company_prefix() for i in range(nBigPool)]
    except:
        CompanyNames = []
    CompanyNames.extend([fake.company() for i in range(nBigPool//10)])
    HomepageUrls = [fake.url() for i in range(nBigPool)]
    AddressTitles = ["Address:","Add:",""]
    Addresses = [fake.address() for i in range(nBigPool)]
    Cities = [fake.city() for i in range(nBigPool)]
    #Countries = [fake.country() for i in range(1000)]
    UserAgents = [fake.user_agent() for i in range(min(nBigPool,2000))]
    RandomDatetimes = [fake.date_time_this_decade(tzinfo=fake.pytimezone()) for i in range(nBigPool)]
    #MimeTypes = [fake.mime_type() for i in range(min(nBigPool,2000))]
    MessageIDs = [f"{fake.msisdn()}{fake.bban()}@{fake.domain_name()}" for i in range(nBigPool)]
    ContentTransferEncodings = ["8bit"]*10+["binary"]*3+["base64"]*3+["quoted-printable"]+["7bit"]+["x-token"]
    Charsets = ["UTF-8"]*9+["ISO-8859-1"]

#信件問候語
def GenerateLetterGreetings():
    OutputFN = "LetterGreetingsForClosing.tsv"
    for i in range(nGen):
        emailClosing = f"{random.choice(GreetingPhrases)},{random.choice(Names)},{random.choice(JobTitles)}"
        with open(OutputFN,'at',encoding='utf-8') as f:
            f.write(emailClosing+"\n")

#聯絡資訊
def GenerateContactInformation(LocaleName="en_US"):
    print(f"Generating Contact Information for {LocaleName}")
    GeneratePool(LocaleName)
    SubDir = os.path.join("#T#[Uncertainty-Contact Information]","Generated Contact Information",LocaleName)
    MKDIR(SubDir)
    for i in range(nGen):
        OutputFN = os.path.join(SubDir,f"ContactInformation_{i}.txt")
        FAXStr = f"FAX:{random.choice(CountryCallingCodes)} {random.choice(PhoneNumbers),}" if random.random()>0.9 else ""''""
        UrlStr = f"{random.choice(HomepageUrls) }" if random.random()>0.9 else ""''""
        CTX = f"""{random.choice(Names)},
        {random.choice(JobTitles).rstrip()},
        {FAXStr}
        {random.choice(PhoneNumberTitles)}:{random.choice(CountryCallingCodes)} {random.choice(PhoneNumbers)},
        {random.choice(EmailTitles)}{random.choice(CompanyEmails)},
        {UrlStr}
        {random.choice(CompanyNames)},
        {random.choice(Addresses)},
        {random.choice(Cities)},
        {fake.current_country()}
        """
        
        CTX = '\n'.join(l.strip() for l in CTX.splitlines())
        with open(OutputFN,'wt',encoding='utf-8') as f:
            f.write(CTX+"\n")
#%%寄件者、收件者、副本Email清單
def UserEmailSets():
    FromList = []
    MailtoList = []
    CCtoList = []
    
    for (rge,term) in [((1,1),FromList),((1,5),MailtoList),((1,10),CCtoList)]:
        for i in range(random.randint(*rge)):
            userEmail = random.choice(CompanyEmails)
            term.append(userEmail)
    return FromList,MailtoList,CCtoList

#%%信件主旨、內容
def EmailTextSets():
    EmailSubjects = [fake.sentence(nb_words=random.randint(1,15)) for i in range(nBigPool//10)]
    EmailContents = [fake.paragraphs(nb=random.randint(1,15)) for i in range(nBigPool//10)]
    return EmailSubjects,EmailContents

#%%Email標頭電郵資訊生成函式
def GenerateEmailAddressInEmailHeader(nGen,LocaleName="en_US"):
    print(f"Generating Email Address In Email Header for {LocaleName}")
    GeneratePool(LocaleName)
    SubDir = os.path.join("#T#[Email Header-Email Address]",LocaleName)
    MKDIR(SubDir)
    for i in range(nGen):
        OutputFN = os.path.join(SubDir,f"Email Address_{i}.txt")
        FromList,MailtoList,CCtoList = UserEmailSets()
        EHF = random.choice(EmailHeaderFields)
        Sep = random.choice(SepChars)
        CTX = ""
        for (field,term) in [
            (EHF["from"],FromList),
            (EHF["mailto"],MailtoList),
            (EHF["cc"],CCtoList)]:
                CTX += field
                CTX += f'{Sep}'.join(term)
                CTX += "\n"
        #MailStr = f'{Sep}'.join(MailtoList)
        #CCStr = f'{Sep}'.join(CCtoList)
        CTX = '\n'.join(l.strip() for l in CTX.splitlines())
        print("="*50)
        print(CTX)
        #print("="*50)
        with open(OutputFN,'wt',encoding='utf-8') as f:
            f.write(CTX+"\n")
            

#%%Email header
'''
  From a@b.c Mon Mar 10 06:08:51 1997
  Return-Path: <a@b.c>
  Delivered-To: target@email.address
  Received: (qmail 21305 invoked from network); 10 Mar 1997 06:08:45 -0000
  Received: from relay.host (1.2.3.4)
    by email.address with SMTP; 10 Mar 1997 06:08:45 -0000
  Received: from my.funny.host (xyz@kryten.eng.monash.edu.au [130.194.140.2])
    by relay.host (8.7.3/8.6.4) with SMTP id RAA23002
    for <target@email.address>; Mon, 10 Mar 1997 17:07:19 +1100
  Date: Mon, 10 Mar 1997 17:07:19 +1100
  Message-Id: <199703100607.RAA23002@relay.host>
  From: kilroy@was.here
  To: who@knows.where
  Subject: Testing - please ignore
'''

'''
Return-path: <john@domain.com>
Message-ID: <5268274827050904@domain.com>
Date: Thu, 05 Jun 2014 22:45:12 +0300
From: John Smith <john@domain.com>
User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:17.0) Gecko/20130625 Thunderbird/17.0.7
MIME-Version: 1.0
To: david@domain2.com
Subject: Re: Hello
References:  <5262A5C746050102@domain2.com>  <5262EC3B06010804@domain.com>  
<5268213A72000805@domain2.com>
In-Reply-To: <5268213A72000805@domain2.com>
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 8bit
'''

def GenerateEmailHeader(nGen,LocaleName="en_US"):
    print(f"Generating Email Header for {LocaleName}")
    GeneratePool(LocaleName)
    SubDir = os.path.join("#T#[Email Header]",LocaleName)
    MKDIR(SubDir)
    EmailSubjects,EmailContents = EmailTextSets()
    ReDict = {}
    
    for i in range(nGen):
        FromList,MailtoList,CCtoList = UserEmailSets()
        EHF = random.choice(EmailHeaderFields)
        Sep = random.choice(SepChars)
        
        FromListStr = ','.join([f"<{x}>" for x in FromList])
        MailtoListStr = ','.join([f"<{x}>" for x in MailtoList])
        CCtoListStr = ','.join([f"<{x}>" for x in CCtoList])
        ReStr = ""
        cnt = 0
        while(random.random()<0.5):
            ReStr += "Re: "
            cnt += 1
        ReDict[cnt] = ReDict.get(cnt,0) + 1
        #SubjectStr = f"{'Re: '*random.randint(1,5)} {random.choice(EmailSubjects)}"
        SubjectStr = f"{ReStr} {random.choice(EmailSubjects)}"
        DateTimeStr = f"{datetime.datetime.strftime(random.choice(RandomDatetimes),random.choice(DateTimeFMTList))}"

        ReferencesStr = ""
        while(random.random()<0.5):
            ReferencesStr += f" <{random.choice(MessageIDs)}>"
        if ReferencesStr != "":
            ReferencesStr = "References: "+ReferencesStr
        if random.random()<0.5:
            InReplyToStr = f"In-Reply-To: <{random.choice(MessageIDs)}>"
        else:
            InReplyToStr = ""
        #print("DateTimeStr",DateTimeStr)
        #Content-Type: text/plain; charset=UTF-8
        #Message-ID: <5268274827050904@{fake.domain_name()}>
        #MessageIDStr = f"Message-ID: <{fake.msisdn()}{fake.bban()}@{fake.domain_name()}>"
        CTXList = [
            ("CTX1",f"""
            Return-path: {FromListStr}
            Message-ID: <{random.choice(MessageIDs)}>
            Date: {DateTimeStr}
            From: {fake.name()} {FromListStr}
            {fake.user_agent()}
            MIME-Version: 1.0
            To: {MailtoListStr}
            Subject: {SubjectStr}
            CC: {CCtoListStr}
            {ReferencesStr}
            {InReplyToStr}
            Content-Type: {fake.mime_type()}; charset=UTF-8
            Content-Transfer-Encoding: {random.choice(ContentTransferEncodings)}
            """),
            ]
        FromList = [x if random.random()<0.8 else f"{fake.name()} {x}" for x in FromList]
        MailtoList = [x if random.random()<0.8 else f"{fake.name()} {x}" for x in MailtoList]
        CCtoList = [x if random.random()<0.8 else f"{fake.name()} {x}" for x in CCtoList]
        #CCtoList = [x if lambda x:x if random.random()<0.01 else f"{fake.name()} {x}" for x in CCtoList]
        SubjectStr = f"{ReStr} {random.choice(EmailSubjects)}"
        DateTimeStr = f"{datetime.datetime.strftime(random.choice(RandomDatetimes),random.choice(DateTimeFMTList))}"

        CTX2 = ""
        for (field,term,SEP) in [
            (EHF["from"],FromList,Sep),
            (EHF["mailto"],MailtoList,Sep),
            (EHF["subject"],SubjectStr,""),
            (EHF["date"],DateTimeStr,""),
            (EHF["cc"],CCtoList,Sep)
            ]:
                CTX2 += field
                CTX2 += f'{SEP}'.join(term)
                CTX2 += "\n"      
        CTXList.append(("CTX2",CTX2))
        for (CTXsubDir,CTX) in CTXList:
            CTX = '\n'.join(l.strip() for l in CTX.splitlines())
            print("="*50)
            print(CTX)
            #print("="*50)
            CTXsubDir = os.path.join(SubDir,CTXsubDir)
            MKDIR(CTXsubDir)
            OutputFN = os.path.join(CTXsubDir,f"Email Header_{i}.txt")
            with open(OutputFN,'wt',encoding='utf-8') as f:
                f.write(CTX+"\n")
    ReDict = dict(sorted(ReDict.items()))
    ReDict = {k:v/sum(ReDict.values()) for k,v in ReDict.items()}
    #print(ReDict)


if __name__=='__main__':      
    #%%信件問候語
    #for LocaleName in ['en_US']:GeneratePool(LocaleName);GenerateLetterGreeting()
    
    #%%聯絡資訊
    for LocaleName in [
        'zh_TW','zh_CN','en_US','fr_FR','de_DE','es_ES','jp_JP','ru_RU',
        ]:
        #聯絡資訊
        #GenerateContactInformation(LocaleName=LocaleName)
        pass
    #%%Email標頭電郵資訊
    for LocaleName in [
        'zh_TW','zh_CN','en_US','fr_FR','de_DE','es_ES','jp_JP','ru_RU',
        ]:
        #Email Header-Email Address
        GenerateEmailAddressInEmailHeader(nGen,LocaleName=LocaleName)
        GenerateEmailHeader(nGen,LocaleName=LocaleName)
        pass
