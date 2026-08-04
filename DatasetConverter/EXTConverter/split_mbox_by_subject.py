import os
import re
from email import message_from_string
from email.policy import default

def clean_filename(s):
    # 移除不可見字元（如 tab、newline）和非法檔名字元
    s = re.sub(r'[\t\n\r]+', ' ', s)              # 移除不可見字元
    s = re.sub(r'[\\/*?:"<>|]', '_', s)           # 移除非法字元
    s = re.sub(r'\s+', ' ', s).strip()            # 多空白壓縮為單一空格
    return s[:150] if s else "No_Found_Subject"   # 加入長度限制並處理空檔名

def split_emails_and_save(input_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)

    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        raw_text = f.read()

    # 使用 From r 開頭作為信件分隔符號
    raw_emails = re.split(r'^From .*\n', raw_text, flags=re.MULTILINE)
    email_count = {}

    for idx, raw in enumerate(raw_emails):
        if not raw.strip():
            continue

        try:
            msg = message_from_string(raw.strip(), policy=default)
            subject = msg.get('Subject', 'No_Found_Subject').strip()
        except Exception:
            subject = 'No_Found_Subject'

        base_name = clean_filename(subject) or 'No_Found_Subject'

        # 防止重名：記錄出現次數並加編號
        count = email_count.get(base_name, 0)
        email_count[base_name] = count + 1
        if count == 0:
            filename = f"{base_name}.txt"
        else:
            filename = f"{base_name}_{count}.txt"

        save_path = os.path.join(output_folder, filename)
        with open(save_path, 'w', encoding='utf-8') as out_f:
            out_f.write(raw.strip())

    print(f"✔ 共儲存 {len(email_count)} 種主題，共 {sum(email_count.values())} 封信件")

input_path = r"D:\shared\TopicClassification\TopicTextCrawler\Books\特定主題\電郵文本\original\fraudulent emails_original.txt"
output_folder = r"D:\shared\TopicClassification\DatasetConverter\EXTConverter\sep_emails"
split_emails_and_save(input_path, output_folder)
