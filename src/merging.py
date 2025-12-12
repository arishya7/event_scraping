import pandas as pd
import json
import os
import glob
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

files = glob.glob(str(PROJECT_ROOT / "review" / "dining" / "*.json"))
all_dfs = []

for f in files:
    try:
        if os.stat(f).st_size > 0:
            with open(f, "r", encoding="utf-8") as infile:
                print("Processing:", f)
                data = json.load(infile)
                if data: 
                    df = pd.json_normalize(data)
                    if not df.empty:
                        all_dfs.append(df)
                    else:
                        print("Empty dataframe from", f)
                else:
                    print("No data in", f)
        else:
            print("Empty file:", f)
    except Exception as e:
        print(f"Error processing {f}: {e}")
        continue
            
if all_dfs:
    final = pd.concat(all_dfs, ignore_index=True)
    final.to_excel("combined_dining.xlsx", index=False)
    print("done")
else:
    print("No data to combine.")