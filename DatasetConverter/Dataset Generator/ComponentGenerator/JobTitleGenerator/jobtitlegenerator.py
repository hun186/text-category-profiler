import random
import json
import os

WDFNCands = [
    "words.json",
    "JobTitleGenerator/words.json",
    ]
for FN in WDFNCands:
    if os.path.isfile(FN):
        with open(FN, 'r') as f:
            data = f.read()
        words = json.loads(data)
        break

def generate_job_title():
    adj1 = random.randrange(len(words['adjective1']))
    adj2 = random.randrange(len(words['adjective2']))
    adj3 = random.randrange(len(words['adjective3']))
    pos = random.randrange(len(words['position']))
    jobtitle = ""
    if words['adjective1'][adj1] != "":
        jobtitle += words['adjective1'][adj1].rstrip() + " "
    if words['adjective2'][adj2] != "":
        jobtitle += words['adjective2'][adj2].rstrip() + " "
    if words['adjective3'][adj3] != "":
        jobtitle += words['adjective3'][adj3].rstrip() + " "
    if words['position'][pos] != "":
        jobtitle += words['position'][pos].rstrip() + " "
    return jobtitle

def print_job_title():
    jobtitle = generate_job_title()
    print("Your new job title:")
    print(jobtitle)

if __name__ == '__main__':
    resp = ""
    while True:
        resp = input("Press ENTER to generate new job title, or type 'q' to quit: ")
        if resp.lower() == "q":
            print("Thank you for using Job Title Generator")
            break
        else:
            print_job_title()
            print("")
