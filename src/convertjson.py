import pandas as pd
import ast
import json
from pathlib import Path

# === CONFIGURATION ===
PROJECT_ROOT = Path("/Users/jindalarishya/event_scraping/final")
INPUT_CSV = PROJECT_ROOT / "updated.csv"
OUTPUT_CSV = PROJECT_ROOT / "output_again.csv"

# === LOAD CSV ===
df = pd.read_csv(INPUT_CSV, dtype=str)
print(f"✅ Loaded {len(df)} rows from {INPUT_CSV}")

# === STEP 1: PARSE PYTHON-LIKE LISTS/DICTS ===
def safe_parse(value):
    """Parse strings like '[{...}]' or '["a","b"]' to real Python objects."""
    if pd.isna(value) or not isinstance(value, str) or not value.strip():
        return value
    # Only try parsing if it looks like a list/dict
    if value.strip().startswith("[") or value.strip().startswith("{"):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value
    return value

df = df.applymap(safe_parse)

# === STEP 2: CLEAN SLASHES (GLOBAL + NESTED) ===
# def clean_all_slashes(value):
#     """
#     Replace all backslashes (\ or \\) and escaped forward slashes (\/) with forward slashes (/).
#     Works recursively for lists and dicts.
#     """
#     if isinstance(value, str):
#         # Replace both single '\' and double '\\' and escaped '\/'
#         return value.replace("\\\\", "/").replace("\\", "/").replace("\\/", "/")
#     elif isinstance(value, list):
#         return [clean_all_slashes(v) for v in value]
#     elif isinstance(value, dict):
#         return {k: clean_all_slashes(v) for k, v in value.items()}
#     return value

# Apply everywhere
# df = df.applymap(clean_all_slashes)

# === STEP 3: CONVERT NESTED OBJECTS BACK TO JSON STRINGS ===
def to_json_string(value):
    """Convert Python lists/dicts back into proper JSON strings for CSV storage."""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value

for col in df.columns:
    if df[col].apply(lambda x: isinstance(x, (list, dict))).any():
        print(f"📦 Converting nested column: {col}")
        df[col] = df[col].apply(to_json_string)

# === STEP 4: SAVE CLEAN CSV ===
df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
print(f"✅ Saved cleaned CSV (all forward slashes) to: {OUTPUT_CSV}")


