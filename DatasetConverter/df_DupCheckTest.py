import pandas as pd
import numpy as np
import time
import string
import random
from tqdm import tqdm

# 生成長度為256的隨機字串
def generate_random_string(length=256):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# 生成長度為30的隨機字串
def generate_random_outlabel(length=30):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# 生成10,000,000列的DataFrame
num_rows = 10000000

# 使用tqdm顯示進度條
data = [generate_random_string() for _ in tqdm(range(num_rows), desc="Generating text column")]
outlabels = [generate_random_outlabel() for _ in tqdm(range(num_rows), desc="Generating Outlabel column")]

# 創建DataFrame
df = pd.DataFrame({'text': data, 'Outlabel': outlabels})

# 檢測重複行並測量時間
start_time = time.time()

# 使用tqdm顯示檢測重複行的進度條
num_duplicates = 0
seen = set()
for row in tqdm(df.itertuples(index=False, name=None), desc="Checking duplicates", total=len(df)):
    if row in seen:
        num_duplicates += 1
    else:
        seen.add(row)
end_time1 = time.time()
df = df.drop_duplicates()
end_time2 = time.time()

# 輸出重複行的數量和耗費的時間
print(f"Number of duplicate rows: {num_duplicates}")
print(f"Time taken for duplicate detection: {end_time1 - start_time} seconds")
print(f"Time taken for duplicate removal: {end_time2 - end_time1} seconds")
print(f"New number of rows after removing duplicates: {len(df)}")
