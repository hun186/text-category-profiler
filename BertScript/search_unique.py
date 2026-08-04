file = "test_results_verification_法輪.txt"

SaveList = []
PreviousLine = ""
with open(file,'rt',encoding='utf-8') as f:
    for line in f:
        if line.split(":")[0] != PreviousLine.split(":")[0]:
            SaveList.append(line)
        PreviousLine = line
#print(SaveList)
#SaveList = sorted(set(SaveList))
#SaveList = list(set(SaveList))
#print(SaveList)
with open(file.replace(".txt","_unique.txt"),'wt',encoding='utf-8') as f:
    for line in SaveList:
        f.write(line)


        