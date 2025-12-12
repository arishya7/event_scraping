import os
import requests
from bs4 import BeautifulSoup
from google import genai
from playwright.sync_api import sync_playwright
import pandas as pd
from pathlib import Path
import json, re
import time
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# --- Setup Gemini ---
API_KEY = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=API_KEY)

def parse_out(out):
    if not out:
        return "No output", "Uncategorized"
    try:
        cleaned = re.sub(r"^```(json)?|```$", "", str(out).strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        return data.get("summary", "No summary"), data.get("category", "Uncategorized")
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
        # fallback crude extraction
        match = re.search(r'"summary"\s*:\s*"([^"]+)"', str(out))
        summary = match.group(1) if match else str(out)[:200]
        return summary, "Uncategorized"


CATEGORIES = """
Breastpumps, Strollers, Carseat, Carriers, Cots, Playpen, Bassinet, Playmats, Play yard,
Baby Camera, Bumper Bed, Food Processor, Weaning, Toys, Clothing, Confinement Herbs,
Chicken Essence, Bouncer/Rocker, Highchair, Bathtime, Sleeptime, Massage, Sterilizers,
Bottle Washer, Milk Maker, Warmers, Bottles, Baby Skincare, Maternity Skincare,
Trike/Scooter, Diaper, Diaper bag, Baby Food, Baby Supplements, Healthy Drinks,
Maternity Wear, Maternity Bra, Lactation Supply, Wipes, Sanitizing, Detergent/Wash,
Swim School, Photography, Tencel, Bamboo, Maid Agency, Nanny, Confinement Food,
Hospital, Cordblood
"""

def normalize_url(url):
    """Ensure URL has proper protocol"""
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def get_html_with_playwright(url, retries=2):
    """Improved Playwright scraper with retries and better error handling"""
    for attempt in range(retries):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                
                # Set longer timeout and wait for network idle
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                
                content = page.content()
                browser.close()
                
                if len(content) > 300:  # Basic validation
                    return content
                    
        except Exception as e:
            print(f"Playwright attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2)
            
    return None

def get_html_with_requests(url, retries=2):
    """Fallback requests method with retries"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            resp.raise_for_status()
            
            if len(resp.text) > 500:
                return resp.text
                
        except Exception as e:
            print(f"Requests attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                
    return None

def extract_text_from_html(html_content):
    """Extract and clean text from HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove unwanted elements
    for element in soup(["script", "style", "nav", "footer", "header"]):
        element.extract()
    
    # Try to find main content areas first
    main_content = soup.find(['main', 'article', 'div'], class_=re.compile(r'content|main|body', re.I))
    if main_content:
        text = " ".join(main_content.stripped_strings)
    else:
        text = " ".join(soup.stripped_strings)
    
    # Clean and truncate
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:8000]

def scrape_and_classify(url, max_retries=3):
    url = normalize_url(url)
    print(f"Processing {url}")
    
    html_content = get_html_with_playwright(url) or get_html_with_requests(url)

    # Try with www prefix if still nothing
    if not html_content:
        parsed = urlparse(url)
        if not parsed.netloc.startswith("www."):
            alt_url = f"{parsed.scheme}://www.{parsed.netloc}{parsed.path}"
            print(f"Trying with www: {alt_url}")
            html_content = get_html_with_requests(alt_url)

    if not html_content:
        return {"summary": "Failed to scrape site", "category": "Unknown", "raw": None}

    text = extract_text_from_html(html_content)

    prompt = f"""
    Summarize the main description of this website in 3–4 sentences. 
    Then assign **one or more categories** from this list:

    {CATEGORIES}

    If no category fits, create a new one.

    Website text:
    {text}

    Respond in JSON with keys: "summary" and "category".
    """

    for attempt in range(max_retries):
        try:
            gemini_resp = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return {"summary": gemini_resp.text, "category": None, "raw": gemini_resp.text}
        except Exception as e:
            print(f"Gemini API attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)

    return {"summary": "Classification failed", "category": "Unknown", "raw": text}


def main():
    inp_file = PROJECT_ROOT / "accounts.csv"
    accounts_df = pd.read_csv(inp_file)
    accounts_df = accounts_df[:10]

    results = []
    failed_urls = []
    
    for idx, row in accounts_df.iterrows():
        name = str(row.get("Account Name", "")).strip()
        url = str(row.get("Website", "")).strip()
        
        if not url or url.lower() == "nan":
            continue

        res = scrape_and_classify(url)
        
        if res:
            summary, category = parse_out(res)
            results.append({
                "Account Name": name,
                "Website": url,
                "Summary": summary,
                "Category": category,
                "Status": "Success"
            })
        else:
            results.append({
                "Account Name": name,
                "Website": url,
                "Summary": "Failed to scrape",
                "Category": "Unknown",
                "Status": "Failed"
            })
            failed_urls.append(url)
        
        # Rate limiting - be nice to websites
        time.sleep(1)

    output_dir = PROJECT_ROOT / "category"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "cat_tests.xlsx"
    results_df = pd.DataFrame(results)
    results_df.to_excel(output_file, index=False)
    print(f"\nFile saved successfully: {output_file}")
    print(f"Success rate: {len([r for r in results if r['Status'] == 'Success'])}/{len(results)}")
    
    if failed_urls:
        print(f"\nFailed URLs ({len(failed_urls)}):")
        for url in failed_urls:
            print(f"  - {url}")

if __name__ == "__main__":
    main()