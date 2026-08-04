import os
import uuid
SubDir = "特定主題/制式片段/#T#[UNEH-UUID]"
for i in range(1000):
    uuidTerm = str(uuid.uuid4())
    with open(os.path.join(SubDir,uuidTerm+".txt"),'wt',encoding='utf-8') as f:
        f.write(uuidTerm)