import os, json, requests
from pathlib import Path
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import re

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not found")

GOOGLE_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def googlePlace_searchText(query: str):
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "places.formattedAddress,places.location"
    }
    body = {
        "textQuery": query,
        "regionCode": "SG",
        "languageCode": "en"
    }
    response = requests.post(
        url=GOOGLE_PLACES_SEARCH_URL, headers=headers, json=body, timeout=10
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("places"):
        return None
    return result["places"][0]

def cleaning(desc):
    if not isinstance(desc,str):
        return 
    district_match = re.search(r"<th>PLN_AREA_N<\/th>\s*<td>([^<]+)<", desc)
    region_match = re.search(r"<th>REGION_N<\/th>\s*<td>([^<]+)<", desc)
    district = district_match.group(1) if district_match else None
    region  = region_match.group(1) if region_match else None
    return district,region

#getting district 
districts = gpd.read_file(PROJECT_ROOT/"config"/"districts.geojson")
districts[['PLN_AREA_N','REGION_N']] =  districts["Description"].apply(
    lambda d: pd.Series(cleaning(d))
)

def which_district(lo,la):
    point = Point(lo,la)
    match = districts[districts.contains(point)]
    if not match.empty:
        return match.iloc[0]["PLN_AREA_N"], match.iloc[0]["REGION_N"]
    return None,None


def enrich_with_coordinates(json_input_path, json_output_path):
    #input path for json file
    with open(json_input_path, "r", encoding="utf-8") as f:
        events = json.load(f)

    #input path for excel
    #df = pd.read_csv(json_input_path)
    #events = df.to_dict(orient="records")

    enriched = []
    for ev in events:
        query = ev.get("venue_name")
        # venue_name = ev.get("venue_name")
        # title = ev.get("title")
        # category = ev.get("categories")
        coords = {"longitude": None, "latitude": None}
        formatted_address = query
        if query:
            try:
                place = googlePlace_searchText(query)
                if place:
                    formatted_address = place.get("formattedAddress", query)
                    loc = place.get("location", {})
                    coords["longitude"] = loc.get("longitude")
                    coords["latitude"] = loc.get("latitude")
            except Exception as e:
                print(f"Error for {query}: {e}")
    

        district,area = (None,None)
        if coords["latitude"] and coords["longitude"]:
            res =  which_district(coords["longitude"],coords["latitude"])
            if res: 
                district, area = res

        ev["address_display"] = formatted_address
        ev["longitude"] = coords["longitude"]
        ev["latitude"] = coords["latitude"]
        ev["planning_area"] = district.title() if district else None
        ev["region"] = area.title() if area else None

        enriched.append(ev)

        # enriched.append({
        #     "category":category,
        #     "title":title,
        #     "venue name":venue_name,
        #     "resolved address":formatted_address,
        #     "area":area.title() if area else None,
        #     "district": district.title() if district else None,
        #     "longitude": coords["longitude"] if coords["longitude"] else "",
        #     "latitude": coords["latitude"] if coords["latitude"] else ""
        # })'
        
    #output path for json
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(enriched,f, indent=2, ensure_ascii=False)

    #output path for excel
   #pd.DataFrame(enriched).to_csv(json_output_path, index=False)
    
    #df_new = pd.DataFrame(enriched,columns = ["category","title","venue name","resolved address","area","district","longitude","latitude"])

    #if os.path.exists(output_file):
    #    old_df = pd.read_excel(output_file)
     #   combined_df = pd.concat([old_df,df_new],ignore_index = True)
    #else: 
     #   combined_df = df_new

    #combined_df.to_excel(output_file, index = False)

    print(f"Saved {len(enriched)} events with coordinates → {json_output_path}")

if __name__ == "__main__":
    # # # loading all jsons
    inp_path = PROJECT_ROOT/"valid_data"/"November"/"19Nov"
    out_path = PROJECT_ROOT/"valid_data"/"November"/"19Nov"
    out_path.mkdir(parents=True, exist_ok=True)

    for file in inp_path.glob("*.json"):
        print(f"Processing {file.name}...")
        enrich_with_coordinates(file, out_path/f"{file.stem}.json")
    # df = pd.read_csv(inp_path)
    # events = df.to_dict(orient="records")
    

