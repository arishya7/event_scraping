import pandas as pd
import csv
import json

INPUT = "/Users/jindalarishya/Downloads/14Nov.csv"
OUTPUT = "/Users/jindalarishya/Downloads/14Nov_clean.csv"

# Load everything as string
df = pd.read_csv(INPUT, dtype=str).fillna("")

# Desired column order
COL_ORDER = [
    "id", "title", "organiser", "blurb", "description", "guid",
    "activity_or_event", "url", "is_free", "price_display_teaser",
    "price_display", "price", "min_price", "max_price",
    "age_group_display", "min_age", "max_age",
    "datetime_display_teaser", "datetime_display",
    "start_datetime", "end_datetime",
    "venue_name", "address_display", "categories", "images",
    "longitude", "latitude", "checked", "source_file",
    "region", "planning_area", "label_tag", "keyword_tag"
]

# -----------------------
# Fix JSON Columns
# -----------------------
JSON_COLS = ["images"]

for col in JSON_COLS:
    def fix_json(s):
        try:
            obj = json.loads(s)
            return json.dumps(obj, ensure_ascii=False)
        except:
            return s  # leave unchanged

    df[col] = df[col].apply(fix_json)

# -----------------------
# Replace newlines
# -----------------------
df = df.replace({"\n": "\\n", "\r": "\\n"}, regex=True)

# -----------------------
# Force column order
# -----------------------
# Missing columns will be created as blank
for col in COL_ORDER:
    if col not in df.columns:
        df[col] = ""

df = df[COL_ORDER]

# -----------------------
# Save cleaned CSV
# -----------------------
df.to_csv(
    OUTPUT,
    index=False,
    quoting=csv.QUOTE_ALL,
    escapechar='"'
)

print(f"✅ Cleaned & Reordered CSV saved to: {OUTPUT}")
