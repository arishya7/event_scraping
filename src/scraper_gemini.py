#!/usr/bin/env python3
import os, sys, json, re, requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from jsonschema import Draft7Validator  # kept in case you validate later
from google import genai
from pathlib import Path
from google.genai import types as genai_types
from playwright.sync_api import sync_playwright
import time
from PIL import Image
from io import BytesIO



PROJECT_ROOT = Path(__file__).resolve().parents[1]

def load_schema():
    with open(PROJECT_ROOT / "config" / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)

SCHEMA = load_schema()

def load_instructions():
    with open(PROJECT_ROOT/ "config"/"instructions.txt",encoding="utf-8") as f: 
        return f.read()
def load_venue():
    with open(PROJECT_ROOT/"config"/"venue.txt") as f:
        return f.read()
    
    
INSTRUCTIONS = load_instructions()

#DOWNLOADING IMAGES
def download_images(items,output_dir):
    os.makedirs(output_dir,exist_ok = True)
    downloaded =0
    def slugify(text):
        return re.sub(r'[^a-zA-Z0-9]+', '_', text.strip())[:50] if text else "unknown" 
    for item in items:
        item_id = item.get("id") or "unknown"
        title = item.get("title") or "unknown"
        venue = item.get("venue_name") or "unknown"
        images = item.get("images") or []

        updated_images = []
        for i, img_url in enumerate(images):
            url = img_url.get("url") if isinstance(img_url, dict) else img_url
            if not url:
                continue
            filename = f"{slugify(venue)}_{i+1}.jpg"
            filepath = os.path.join(output_dir, filename)

            # Create image_entry with filename
            image_entry = {
                "url": url,
                "source_credit": img_url.get("source_credit") if isinstance(img_url, dict) else item.get("organiser"),
                "filename": filename
            }

            if os.path.exists(filepath):
                image_entry["local_path"] = str(filepath)
            else:
                try:
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    img_data = response.content

                    with Image.open(BytesIO(img_data)) as img:
                        img.convert("RGB").save(filepath, format="JPEG", quality=85)
                    image_entry["local_path"] = str(filepath)

                    downloaded += 1
                    print(f"Downloaded image for {item_id} from {url} → {filepath}")

                except Exception as e:
                    image_entry["local_path"] = None
                    print(f"Failed to download image from {item_id}")

            # Add the updated image entry to the list
            updated_images.append(image_entry)

        item["images"] = updated_images
    print(f"Total images downloaded: {downloaded}")

import unicodedata

#character normalization 
def fix_broken_characters(text: str) -> str:
    if not isinstance(text, str):
        return text

    # Step 1 — Try to fix mojibake (UTF-8 decoded as latin-1)
    try:
        text = text.encode("latin1").decode("utf8")
    except:
        pass

    # Step 2 — Normalize Unicode (curly quotes → straight quotes)
    text = unicodedata.normalize("NFKC", text)

    # Step 3 — Replace common bad sequences manually
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": "\"",
        "â€": "\"",
        "â€“": "-",
        "â€”": "-",
        "â€¢": "•",
        "â€¦": "...",
        "Ã©": "é",
        "Ã": "à",  
        "‚Äô": "'",
        "‚Äì": "-",
        "Â": "",   
    }

    for bad, good in replacements.items():
        text = text.replace(bad, good)

    return text

def _ensure_url(u, base=""):
    u = (u or "").strip()
    if not u:
        return ""
    if base:
        u = urljoin(base, u)
    try:
        p = urlparse(u)
        return u if p.scheme and p.netloc else ""
    except:
        return ""

#plain text
def extract_plain_text_blocks(html: str):
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text("\n", strip=True)

    # Split page text into lines
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    blocks = []
    for i, line in enumerate(lines):
        if re.search(r"SG\s*\d{6}", line) or (len(line) > 15 and not line.lower().startswith(("home", "cart", "subscribe", "newsletter"))):
            context = "\n".join(lines[max(0, i-2):i+2]) 
            blocks.append(
                {
                    "text":context,
                    "images": []
                }
            )

    return blocks

def enrich_free_price_fields(item):
    price_display_teaser = (item.get("price_display_teaser") or "").lower()

    # Determine is_free
    if "free" in price_display_teaser:
        item["is_free"] = True
    else:
        item["is_free"] = False

    # min_price
    if item["is_free"]:
        item["min_price"] = 0
    else:
        try:
            item["min_price"] = float(item["price"]) if item.get("price") else None
        except:
            item["min_price"] = None

    # max_price
    try:
        pd = item.get("price_display") or ""
        nums = re.findall(r"\d+(?:\.\d+)?", pd)
        if nums:
            item["max_price"] = float(nums[-1])
        else:
            item["max_price"] = item["min_price"]
    except:
        item["max_price"] = None

    return item

def fetch_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/115.0.0.0 Safari/537.36",
            java_script_enabled=True
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Wait longer for initial content
            time.sleep(10)  # Increased from 10
            
            # More aggressive scrolling to load all content
            for i in range(2):  # Increased if the website takes time to load
                page.mouse.wheel(0, 5000)  # Bigger scroll

                time.sleep(3)  # Longer wait between scrolls
                
                # Check if we've loaded more content
                project_count = len(page.query_selector_all('.project, [class*="project"]'))
                print(f"[debug] Scroll {i+1}: Found {project_count} projects", file=sys.stderr)
                
                # If we found 22+ projects, we can stop
                if project_count >= 15:
                    print(f"[debug] Found all {project_count} projects!", file=sys.stderr)
                    break

            # Final wait
            time.sleep(5)
            
            html = page.content()
            return html
        finally:
            browser.close()

def fetch_blocks(url: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        all_blocks = {}
        prev_height = 0
        same_height_count = 0

        while same_height_count < 7:  # allow more stability rounds
            page.mouse.wheel(0, 300)
            time.sleep(2)

            # Get current scroll height
            height = page.evaluate("document.body.scrollHeight")

            # Grab new blocks
            items = page.query_selector_all('div[data-index]')
            for item in items:
                index = item.get_attribute("data-index")
                if index not in all_blocks:
                    all_blocks[index] = {
                        "html": item.inner_html(),
                        "text": item.inner_text().strip()
                    }

            print(f"[debug] Height={height} | Total blocks={len(all_blocks)}", file=sys.stderr)

            # Stop only when height stops growing
            if height == prev_height:
                same_height_count += 1
            else:
                same_height_count = 0

            prev_height = height

        browser.close()
        return list(all_blocks.values())


def find_jsonld_events(soup: BeautifulSoup):
    blocks = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            raw = tag.get_text(strip=True) or ""
            if "Event" in raw:
                blocks.append(raw)
        except Exception:
            continue
    return blocks

#scoring the ranking
def score_card_html(html: str) -> int:
    """Higher = more likely to be a listing card."""
    s = 0
    h = html.lower()

    if any(word in h  for word in ['playground','facility','venue','location','attraction']):
        s+=5
    if any(word in h for word in ['about','overview','features','amenities']):
        s+=4
    if "<h1" in h or "<h2" in h or "<h3" in h or "<h4" in h:
        s += 4
    if "operating hours" in h or "contact" in h or "address" in h: 
        s+=3

    if any(word in h for word in ['book now','sgd','$','buy now','add to cart']):
        s+=2
    if "single admission" in h or "package" in h: 
        s+=2
    

    text_len = len(re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True)))
    if 200 <= text_len <= 2000:
        s += 2
    return s

#prices
def extract_price(text):
    if not text:
        return {
            "price": 0.0,
            "price_display": "Please contact for pricing",
            "price_display_teaser": "Contact for pricing"
        }
    if re.search(r"(complimentary|free)", text, re.I):
        return {
        "price": 0.0,
        "price_display": "Free",
        "price_display_teaser": "Free"
    }

    if re.search(r"(contact|check website)", text, re.I):
        return {
        "price": 0.0,
        "price_display": "Please contact for pricing",
        "price_display_teaser": "Contact for pricing"
    }

    
    text_clean = re.sub(r'\s+', ' ', text.strip())
    
    price_patterns = [
        # Range patterns -
        r'(?:from\s*)?s?\$\s*(\d+(?:\.\d{1,2})?)\s*(?:-|to)\s*s?\$\s*(\d+(?:\.\d{1,2})?)',  
        r'sgd\s*(\d+(?:\.\d{1,2})?)\s*(?:-|to)\s*sgd\s*(\d+(?:\.\d{1,2})?)',  
        
        # Single price patterns
        r'(?:from\s*)?s?\$\s*(\d+(?:\.\d{1,2})?)',  # $25.00, S$25, $ 25, from $25
        r'sgd\s*(\d+(?:\.\d{1,2})?)',   # SGD 25.00
        r'(\d+(?:\.\d{1,2})?)\s*sgd',   # 25.00 SGD
        r'price:\s*s?\$\s*(\d+(?:\.\d{1,2})?)',  # Price: $25
        r'cost:\s*s?\$\s*(\d+(?:\.\d{1,2})?)',   # Cost: $25
        
        # Special patterns
        r'complimentary.*(?:guests|members).*?(\d+(?:\.\d{1,2})?)',
        r'(\d+(?:\.\d{1,2})?).*?(?:per child|per adult|per entry)',
        r'(\d+)\s*dollars?',  # 25 dollars
        r'complimentary|free(?: of charge| free admission)?' # Free, Free of charge, Free admission
    ]
    
    has_free = bool(re.search(r"(complimentary|free)", text, re.I))
    text = text_clean.lower()

    for pattern in price_patterns: 
        matches = re.findall(pattern,text,re.IGNORECASE)
        if matches:
            if isinstance(matches[0], tuple):  # Range pattern
                min_price = float(matches[0][0])
                max_price = float(matches[0][1]) if matches[0][1] else min_price
                return {
                    "price": min_price,
                    "price_display": f"S${min_price:.2f} - S${max_price:.2f}",
                    "price_display_teaser": teaser_from_prices(min_price, max_price, has_free)
                }
            else: 
                price = float(matches[0])
                return {
                    "price": price,
                    "price_display": f"S${price:.2f}",
                    "price_display_teaser": teaser_from_prices(price, price, has_free)
                }
            

    
    # If we didn't match but saw "free"
    if has_free:
        return {
            "price": 0.0,
            "price_display": "Free",
            "price_display_teaser": "Free"
        }

    # Otherwise unknown
    return {
        "price": None,
        "price_display": "Please contact for pricing",
        "price_display_teaser": "From $"  # safe fallback
    }

def merge_price_fields(item: dict, text: str):
    price_info = extract_price(text)
    for k in ["price", "price_display", "price_display_teaser"]:
        val = item.get(k)
        if price_info.get(k) is not None and (
            val is None or (isinstance(val, str) and "Please" in val)
        ):
            item[k] = price_info[k]
    return item

#processing images
def process_images(url):
    """clean up images to remove blur and increase quality"""
    if "wixstatic.com" in url and "/v1/fill/" in url:
        url = re.sub(r'w_\d+,h_\d+',r'w_2000,h_2000',url) #increasing the size
        url = re.sub(r',blur_\d+','',url) #remove the blur
        url = re.sub(r'q_\d+',r'q_100',url) #increase quality
    elif "cloudinary.com" in url: 
        url = re.sub(r'w_\d+,h_\d+',r'w_2000,h_2000',url) #increasing the size
        url = re.sub(r',blur_\d+','',url) #remove the blur
        url = re.sub(r'q_\d+',r'q_100',url) #increase quality
    elif "images.unsplash.com" in url:
        url = re.sub(r'w=\d+&h=\d+', 'w=2000&h=2000', url)
    elif "wp-content/uploads" in url:
        if "?" in url:
            url = url.split("?")[0]   

    return url

def teaser_from_prices(min_price, max_price, has_free=False):
    if has_free and max_price > 0:
        return "Free + Paid options"
    if min_price == 0.0 and max_price == 0.0:
        return "Free"
    if min_price is not None and min_price > 0:
        if min_price == max_price: 
            return f"From ${min_price:.0f}"
    return "Check website for pricing"


def _extract_from_srcset(val: str):
    return [p.strip().split(" ")[0].strip() for p in (val or "").split(",") if p.strip()]

def images_from_node(node, base_url: str):
    imgs = []
    if not node:
        return imgs

    for img in node.find_all("img"):
        cand = [
            img.get("src"), img.get("data-src"), img.get("data-original"),
            img.get("data-lazy"), img.get("data-lazy-src"), img.get("data-zoom-image")
        ]
        for c in cand:
            v = _ensure_url(c, base_url)
            if v:
                imgs.append(v)

        for attr in ("srcset", "data-srcset"):
            if img.has_attr(attr):
                for u0 in _extract_from_srcset(img.get(attr, "")):
                    w = _ensure_url(u0, base_url)
                    if w:
                        imgs.append(w)

    for src in node.select("picture source[srcset]"):
        for u0 in _extract_from_srcset(src.get("srcset", "")):
            x = _ensure_url(u0, base_url)
            if x:
                imgs.append(x)

    style = node.get("style") or ""
    m = re.search(r'background-image:\s*url\(["\']?(.*?)["\']?\)', style, re.I)
    if m:
        bg_url = _ensure_url(m.group(1), base_url)
        if bg_url:
            imgs.append(bg_url)

    for div in node.find_all("div", style=True):
        style = div.get("style") or ""
        m = re.search(r'background-image:\s*url\(["\']?(.*?)["\']?\)', style, re.I)
        if m:
            bg_url = _ensure_url(m.group(1), base_url)
            if bg_url:
                imgs.append(bg_url)

    proc_imgs = [process_images(u) for u in imgs]

    # de-dup preserve order
    seen = set()
    dedup = []
    for u in proc_imgs:
        if u not in seen:
            seen.add(u)
            dedup.append(u)
    return dedup[:5]

def images_near_heading(node, base_url: str, max_siblings: int = 8):
    if not node:
        return []

    # First try the heading's parent
    imgs = images_from_node(node.parent if node.parent else node, base_url)
    if imgs:
        return imgs

    # Look in following siblings
    sib = node
    for _ in range(max_siblings):
        sib = sib.find_next_sibling()
        if not sib:
            break
        imgs = images_from_node(sib, base_url)
        if imgs:
            return imgs

    # Look in preceding siblings
    sib = node
    for _ in range(max_siblings):
        sib = sib.find_previous_sibling()
        if not sib:
            break
        imgs = images_from_node(sib, base_url)
        if imgs:
            return imgs

    # Try grandparent
    if node.parent and node.parent.parent:
        imgs = images_from_node(node.parent.parent, base_url)
        if imgs:
            return imgs

    return []


def extract_candidate_blocks(soup: BeautifulSoup, base_url: str):
    """Generic card/list/grid blocks likely representing listings, with local images."""
    selectors = [
        ".card", ".listing", "article", ".event", ".tile", ".result",
        "ul li", "ol li", ".grid > div", ".row > .col",
        
        # Venue focused selectors 
        ".venue", ".location", ".facility", ".center", ".club", 
        ".playground", ".attraction", "[class*=venue]", "[class*=location]",
        ".about", ".overview", ".facility-info", ".venue-details",
        "main", ".main-content", "#main", ".content",

        "a.project"
    ]
    bad = re.compile(r"(footer|header|nav|subscribe|breadcrumb|cookie|newsletter|promo|share)", re.I)

    nodes = []
    for sel in selectors:
        nodes.extend(soup.select(sel))
    seen = set()
    uniq = []
    for n in nodes:
        cls = " ".join(n.get("class") or [])
        if bad.search(cls):
            continue
        if id(n) not in seen:
            seen.add(id(n))
            uniq.append(n)
    
    blocks = []
    for n in uniq:
        text = re.sub(r"\s+", " ", n.get_text(" ", strip=True))
        if len(text) >= 10 and is_relevant_content(text):
            # Get images specific to this block
            block_images = images_from_node(n, base_url)
            blocks.append({
                "html": str(n),
                "images": block_images,
                "score": score_card_html(str(n)),
                "text": text  # Store text for easier access
            })


    blocks.sort(key=lambda b: b["score"], reverse=True)
    
    print(f"[debug] Found {len(blocks)} candidate blocks (top 3 shown)", file=sys.stderr)
    for i, b in enumerate(blocks[:3]):
        preview = b["text"][:200]
        print(f"[debug] Block {i+1} preview: {preview}...", file=sys.stderr)
        print(f"[debug] Block {i+1} images: {len(b['images'])} images", file=sys.stderr)

    return blocks[:40]

def extract_heading_groups(soup: BeautifulSoup, base_url: str):
    """Heading + nearby description + images near that heading section."""
    groups = []
    heads = soup.find_all(["h1","h2","h3","h4"])
    
    for h in heads:
        title = re.sub(r"\s+"," ", h.get_text(" ", strip=True))
        if not title:
            continue

        desc_parts = []
        for sib in h.find_all_next():
            if sib is h:
                continue
            if sib.name in ["h1","h2","h3","h4"]:
                break
            if sib.name in ["p","div","section","article","li"]:
                t = re.sub(r"\s+"," ", sib.get_text(" ", strip=True))
                if len(t) >= 40:
                    desc_parts.append(t)
            if len(desc_parts) >= 4:
                break

        if not desc_parts:
            continue

        full_text = title + "\n" + "\n".join(desc_parts)
        # Get images specific to this heading group
        imgs = images_near_heading(h, base_url, max_siblings=8)

        # Split into smaller logical sections
        for section in split_sections(full_text):
            groups.append({
                "text": section, 
                "images": imgs,  # Each group gets its own images
                "heading_element": h  # Store reference for debugging
            })

    print(f"[debug] Found {len(groups)} heading groups", file=sys.stderr)
    for i, g in enumerate(groups[:3]):
        print(f"[debug] Group {i+1} preview: {g['text'][:200]}...", file=sys.stderr)
        print(f"[debug] Group {i+1} images: {len(g['images'])} images", file=sys.stderr)

    return groups[:40]

def extract_content(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    return {
        "title": (soup.title.string.strip() if soup.title and soup.title.string else ""),
        "jsonld_raw": find_jsonld_events(soup),
        "blocks": extract_candidate_blocks(soup, base_url),
        "heading_groups": extract_heading_groups(soup, base_url),
    }

def is_relevant_content(text) -> bool:
    """check if the content is likely to contain event or activity """
    text = text.lower()
    keywords = ['dining','restaurant','menu','activity','event','playground','indoor playground','outdoor playground','attractions','mall related'
                ,'kids','children','family','babies','trip','party','shopping','play','learn','explore','educational']
    if not any(keyword in text for keyword in keywords):
        return False 
    return True

def build_projects_prompt(project_nodes, page_url):
    blocks_text = "\n\n".join([str(node) for node in project_nodes])
    instr = INSTRUCTIONS.replace("{SCHEMA}", json.dumps(SCHEMA, ensure_ascii=False))
    venue_focus_instructions = load_venue()

    return (
        instr + venue_focus_instructions
        + "\nSOURCE_URL:\n" + page_url
        +  "IMPORTANT: Each block may contain MULTIPLE individual events. Extract ALL listings separately."
          "Only extract venues explicitly visible in these blocks. "
          "Do not invent or include any other parks, attractions, or events not in the block."
        + "\nNOTE: Do NOT replace the URL with links found in the block. "
        + "Use the SOURCE_URL for both 'guid' and 'url'.\n"
        + "\nBLOCK:\n" + blocks_text[:150000]
        + "\nIMPORTANT: You must include these BLOCK_IMAGES in the 'images' field of each output object. "
        + "Each image must be an object with {url, source_credit}, where source_credit = organiser name.\n"
        + "\nOUTPUT:\nReturn only the JSON array. "
          "RULES: Extract any activities, attractions, playgrounds, or events that families, kids, or parents might attend. "
          "Never invent festivals, runs, or other events unless shown verbatim. "
          "If fields are missing, leave them null."
    )


def build_block_prompt(block_text: str, page_url: str, block_images: list[str]) -> str:
    price_info = extract_price(block_text)
    instr = INSTRUCTIONS.replace("{SCHEMA}", json.dumps(SCHEMA, ensure_ascii=False))

    price_hint = ""
    if price_info.get("price") is not None:
        price_hint = f"\nEXTRACTED_PRICE_INFO:\n{json.dumps(price_info, ensure_ascii=False)}"

    venue_focus_instructions = load_venue()

    return (
        instr + venue_focus_instructions
        + "\nSOURCE_URL:\n" + page_url
        + "\nIMPORTANT: Extract ALL separate venues or events from this block. "
        + "Do not merge events. Return one JSON object per event. "
        + "If multiple venues are shown, extract each separately.\n"
        + "\nNOTE: Do NOT replace the URL with links found in the block. "
        + "Use the SOURCE_URL for both 'guid' and 'url'.\n"
        + "\nBLOCK:\n" + block_text[:4000]  # 📌 NOT 4000
        + "\nBLOCK_IMAGES:\n" + json.dumps(block_images or [], ensure_ascii=False)[:2000]
        + "\nIMPORTANT: You must include these BLOCK_IMAGES in the 'images' field of each output object. "
        + "Each image must be an object with {url, source_credit}, where source_credit = organiser name.\n"
        + price_hint
        + "\nOUTPUT:\nReturn only the JSON array. "
          "RULES: Extract any activities, attractions, playgrounds, or events that families, kids, or parents might attend. "
          "Never invent festivals, runs, or other events unless shown verbatim. "
          "If fields are missing, leave them null."
    )

def split_sections(text: str) -> list[str]:
    sections = []
    current = []
    for line in text.splitlines():
        if re.search(r"(public admission|hotel|membership|package|price|timings)", line.lower()):
            if current:
                sections.append("\n".join(current).strip())
                current = []
        current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return sections


# Configure the Gemini client
try:
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    MODEL_NAME = os.getenv("GOOGLE_GENAI_MODEL", "gemini-2.0-flash")
except (KeyError, ValueError) as e:
    print(f"Error: {e}. Please ensure GOOGLE_API_KEY is set.", file=sys.stderr)
    client = None
    MODEL_NAME = None

def call_gemini_json(prompt: str):
    if not client or not MODEL_NAME:
        print("[debug] Gemini client not initialized. Skipping API call.", file=sys.stderr)
        return []

    try:
        print(f"[debug] Calling Gemini with prompt (first 300 chars): {prompt[:300]}...", file=sys.stderr)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        text = (response.text or "").strip()
        print(f"[debug] Gemini response (first 300 chars): {text[:300]}...", file=sys.stderr)

        objs = json.loads(text)
        if isinstance(objs, dict):
            return [objs]
        if isinstance(objs, list):
            return objs
        return []

    except Exception as e:
        print(f"[debug] Error calling Gemini: {e}", file=sys.stderr)
        return []


def dedup_items(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items: 
        if not isinstance(item, dict):
            continue
        key = (
            safe_strip(item.get('venue_name')).lower(),
            safe_strip(item.get('guid')).lower()
        )
        if key not in seen: 
            seen.add(key)
            deduped.append(item)
    return deduped

def extract_operating_hours(text: str) -> str | None:
    """Extract operating hours from text like 'Operating Hours: 10am - 10pm'"""
    if not text:
        return None

    # Look for phrases like "Operating Hours: 10am to 10pm"
    m = re.search(r'(Operating Hours[:\s]*)([^.;\n]+)', text, re.I)
    if m:
        return m.group(0).strip()

    # Look for "Open daily 10am to 10pm"
    m = re.search(r'(?:Open|Daily|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^.;\n]+', text, re.I)
    if m:
        return m.group(0).strip()

    return None

def is_valid_item(obj, keywords):
    if not isinstance(obj, dict):
        return False

    title = (obj.get("title") or "").strip().lower()
    venue_name = (obj.get("venue_name") or "").strip().lower()

    # Reject if no title at all
    if not title:
        return False

    # Keep if a venue name exists
    if venue_name:
        return True

    # Otherwise keep if any keyword match
    if any(kw in title for kw in keywords):
        return True

    return True

def extract_full_address_from_text(text):
    """Extract Singapore address with multiple fallback patterns."""
    if not text:
        return None
    
    # Pattern 1: Full address with postal code
    patterns = [
        # Complete address with postal code
        r'([^.\n]*?Singapore\s+\d{6}[^.\n]*)',
        # Address ending with Singapore + postal
        r'([^.\n]*?\d{6}\s+Singapore[^.\n]*)',
        # Street address with Singapore
        r'([^.\n]*?(?:Street|Road|Avenue|Drive|Lane|Walk|Park|Plaza|Centre|Building)[^.\n]*?Singapore[^.\n]*)',
        # Any line containing Singapore and numbers (likely postal)
        r'([^.\n]*?Singapore[^.\n]*?\d{6}[^.\n]*)',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            addr = match.group(1).strip()
            # Clean up the address
            addr = re.sub(r'\s+', ' ', addr)
            addr = re.sub(r'^[^\w]*|[^\w]*$', '', addr)  # Remove leading/trailing non-word chars
            if len(addr) > 10:  # Must be substantial
                return addr
    
    return None

def extract_full_address(html):
    """More comprehensive address extraction from entire HTML."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Try structured data first
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                # Look for address in structured data
                addr = data.get("address")
                if addr:
                    return str(addr) if isinstance(addr, str) else json.dumps(addr)
        except:
            pass
    
    # Try contact/address sections
    address_sections = soup.find_all(["div", "section", "p"], 
                                   class_=re.compile(r"address|contact|location", re.I))
    
    for section in address_sections:
        addr = extract_full_address_from_text(section.get_text())
        if addr:
            return addr
    
    # Fallback to full page text
    full_text = soup.get_text("\n", strip=True)

    return extract_full_address_from_text(full_text)

def global_address(html):
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    line_match = re.search(r".{0,100}(Singapore\s*\d{6}).{0,100}", text, re.I)
    if line_match:
        # Get the whole line (not just the postal code)
        line = line_match.group(0)
        # Clean multiple spaces
        return re.sub(r"\s+", " ", line).strip()

    return None

def get_fallback_images(html: str, base_url: str) -> list[str]:
    """Extract fallback images from the entire page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for main content images
    main_selectors = ["main img", ".main-content img", "#content img", "article img"]
    fallback_images = []
    
    for selector in main_selectors:
        imgs = soup.select(selector)
        for img in imgs[:10]:  # Limit to prevent too many images
            src = img.get("src") or img.get("data-src")
            if src:
                full_url = _ensure_url(src, base_url)
                if full_url:
                    processed_url = process_images(full_url)
                    fallback_images.append(processed_url)
    
    # Remove duplicates
    seen = set()
    unique_images = []
    for url in fallback_images:
        if url not in seen:
            seen.add(url)
            unique_images.append(url)
    
    return unique_images[:5]  

def safe_strip(value):
    if isinstance(value, str):
        return value.strip()
    return ""   
def scrape_park_images(park_url):
    html = requests.get(park_url).text
    soup = BeautifulSoup(html, "html.parser")
    
    # Gallery items
    img_tags = soup.select("img")  # or narrow down with [class*='gallery']
    img_urls = []
    for img in img_tags:
        src = img.get("src") or img.get("data-src")
        if src:
            img_urls.append(_ensure_url(src, park_url))
    return img_urls

#id loader
def load_id():
   tracker_path = PROJECT_ROOT/"config"/"id_tracker.txt"
   if tracker_path.exists():
       try: 
           with open(tracker_path, "r") as f:
                return int(f.read().strip())
       except (IOError, ValueError):
            return 0
   return 0
#save_id
def save_id(last_id: int):
    tracker_path = PROJECT_ROOT/"config"/"id_tracker.txt"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    with open(tracker_path, "w") as f:
          f.write(str(last_id))
    
def main():
    try:
        all_items = []
        processed_sources = [] 
        url = sys.argv[1] if len(sys.argv) > 1 else input("Enter URL: ").strip()
        if not url:
            print("[]")
            return

        print(f"[debug] Fetching URL: {url}", file=sys.stderr)
        html = fetch_html(url)

        print(f"[debug] HTML fetched, length: {len(html)} chars", file=sys.stderr)

        try:
            ctx = extract_content(html, base_url=url)
            blocks = fetch_blocks(url)
            print(f"[debug] Found {len(blocks)} candidate blocks", file=sys.stderr)
            # Custom handling for Gowhere project cards using data-index elements
            if blocks:
                print(f"[debug] Processing {len(blocks)} Gowhere event blocks", file=sys.stderr)

                for i, block in enumerate(blocks):
                    try:
                        block_text = block.get("text", "")
                        block_html = block.get("html", "")
                        block_images = images_from_node(BeautifulSoup(block_html, "html.parser"), url)

                        print(f"[debug] Processing Gowhere block {i+1}: {block_text[:120]}...", file=sys.stderr)

                        # Build prompt from block text + images
                        prompt = build_block_prompt(block_html, url, block_images)
                        arr = call_gemini_json(prompt)

                        if isinstance(arr, list) and arr:
                            for item in arr:
                                if isinstance(item, dict):
                                    item["_source_type"] = "gowhere_block"
                                    item["_source_index"] = i
                                    item["_source_images"] = block_images
                                    item["_source_text"] = block_text
                            all_items.extend(arr)
                        else:
                            print(f"[debug] Gowhere block {i+1} returned no valid items", file=sys.stderr)

                    except Exception as e:
                        print(f"[debug] Error processing Gowhere block {i+1}: {e}", file=sys.stderr)
                        continue

        except Exception as e:
            print(f"Error extracting content from {url}: {e}", file=sys.stderr)
            print("[]")
            blocks = []
        # #print
        #     f"[debug] title={ctx['title']!r} "
        #     f"jsonld={len(ctx['jsonld_raw'])} "
        #     f"blocks={len(ctx['blocks'])} "
        #     f"heads={len(ctx['heading_groups'])}",file=sys.stderr

 # Track which content sources we've processed
        soup = BeautifulSoup(html,"html.parser")

       # ADD ONE SELECTORS DEPENDING ON WEBSITE IF IT HAS A WEIRD STRUCTURE w no blocs/headings
       #a.project for playpoint
        # In the projects section, try this selector instead:
        # Gowhere-compatible project/event card selectors
        projects = soup.select("div[data-index]")


        if not projects:
            projects = soup.select(".project") 
        if not projects:
            projects = soup.select("[class*='project']")

        print(f"[debug] Found {len(projects)} project elements with improved selectors", file=sys.stderr)

        print(f"[debug] Found {len(projects)} <a.project> elements", file=sys.stderr)

        "---PROJECTS PROCESSSING---"
        if projects:
            print(f"[debug] Processing {len(projects)} project cards individually", file=sys.stderr)
            
            for i, project in enumerate(projects):
                try:
                    # Extract images from this specific project
                    project_images = images_from_node(project, url)
                    project_text = re.sub(r"\s+", " ", project.get_text(" ", strip=True))
                    
                    print(f"[debug] Processing project {i+1}/{len(projects)}: {project_text[:100]}...", file=sys.stderr)
                    
                    # Create individual prompt for this project
                    individual_prompt = build_projects_prompt([project], url)
                    
                    # Call Gemini for this specific project
                    arr = call_gemini_json(individual_prompt)
                    print(f"[debug] Raw arr result: {arr}", file=sys.stderr)
                    print(f"[debug] Type: {type(arr)}, Length: {len(arr) if hasattr(arr, '__len__') else 'N/A'}", file=sys.stderr)

                    if isinstance(arr, list) and len(arr) > 0:
                        print(f"[debug] Project {i+1} returned {len(arr)} items", file=sys.stderr)
                        # ... rest of your code
    
                        
                        # Add source tracking and images to each item
                        for item in arr:
                            if isinstance(item, dict):
                                item["_source_type"] = "project"
                                item["_source_index"] = i
                                item["_source_images"] = project_images
                                item["_source_text"] = project_text
                        
                        all_items.extend(arr)
                    else:
                        print(f"[debug] Project {i+1} validation failed - arr is not a non-empty list", file=sys.stderr)
        
                        
                except Exception as e:
                    print(f"[debug] Error processing project {i+1}: {e}", file=sys.stderr)
                    continue
                    
            print(f"[debug] Total items from projects: {len(all_items)}", file=sys.stderr)
            
            # If we still don't have enough items, try batch processing as fallback
            if len(all_items) < len(projects):
                print(f"[debug] Only got {len(all_items)} items from {len(projects)} projects, trying batch processing", file=sys.stderr)
                
                # Split projects into smaller batches to avoid token limits
                batch_size = 5
                for batch_start in range(0, len(projects), batch_size):
                    batch_end = min(batch_start + batch_size, len(projects))
                    batch_projects = projects[batch_start:batch_end]
                    
                    try:
                        batch_prompt = build_projects_prompt(batch_projects, url)
                        batch_arr = call_gemini_json(batch_prompt)
                        
                        if isinstance(batch_arr, list) and len(batch_arr) > 0:
                            print(f"[debug] Batch {batch_start//batch_size + 1} returned {len(batch_arr)} items", file=sys.stderr)
                            
                            for item in batch_arr:
                                if isinstance(item, dict):
                                    item["_source_type"] = "project_batch"
                                    item["_source_index"] = batch_start
                                    item["_source_images"] = []  
                                    item["_source_text"] = ""
                            
                            all_items.extend(batch_arr)
                            
                    except Exception as e:
                        print(f"[debug] Error processing batch {batch_start//batch_size + 1}: {e}", file=sys.stderr)

        else:
            if "semec.com.sg/public-residences" in url:
                # top_items = soup.select("div.item-link-wrapper[data-hook='item-link-wrapper']")
                # for i, item in enumerate(top_items):
                #     img_url = None

                #     img_tag = item.find("img")
                #     if img_tag:
                #         img_url = img_tag.get("src") or img_tag.get("data-src")
                #     elif item.get("style"):
                #         match = re.search(r'url\(["\']?(.*?)["\']?\)', item["style"])
                #         if match:
                #             img_url = match.group(1)

                #     if img_url:
                #         playground_title = f"Public Playground {i+1}"
                #         block_text = f"Venue Name: {playground_title}\nCategory: Outdoor Playground\nDescription: Public playground with SEMEC equipment."
                #         arr = call_gemini_json(build_block_prompt(block_text, url, [img_url]))
                #         if isinstance(arr, list):
                #             for obj in arr:
                #                 obj["_source_type"] = "semec_top"
                #                 obj["_source_index"] = i
                #                 obj["_source_images"] = [img_url]
                #             all_items.extend(arr)
                wix_items = soup.select("a.item-link-wrapper[data-hook='item-link-wrapper']")
                park_links = [_ensure_url(item.get("href"), url) for item in wix_items if item.get("href")]

                # Step 2: loop each park page
                for i, park_url in enumerate(park_links):
                    park_title = park_url.rstrip("/").split("/")[-1].replace("-", " ").title()
                    img_urls = scrape_park_images(park_url)

                    block_text = f"Venue Name: {park_title}\nCategory: Outdoor Playground\nDescription: Public playground with SEMEC equipment."
                    arr = call_gemini_json(build_block_prompt(block_text, park_url, img_urls))

                    if isinstance(arr, list) and arr:
                        for obj in arr:
                            obj["_source_type"] = "semec_individual"
                            obj["_source_index"] = i
                            obj["_source_url"] = park_url
                            obj["_source_images"] = img_urls
                        all_items.extend(arr)

 
        #FALLBACK TO headings, candidate, jsload blocks 

         # Get fallback images for items that don't have images
        fallback_images = get_fallback_images(html, url)
        print(f"[debug] Found {len(fallback_images)} fallback images", file=sys.stderr)

        if not all_items:
            print("[debug] No items from projects, falling back to heading/block extraction", file=sys.stderr)

            # 1) Always try heading groups first (venue-first extraction)
            print("[debug] Extracting venues from heading groups", file=sys.stderr)
            for i, group in enumerate(ctx.get("heading_groups", [])):
                try:
                    print(f"[debug] Processing heading group {i+1}/{len(ctx['heading_groups'])}", file=sys.stderr)
                    arr = call_gemini_json(
                        build_block_prompt(group["text"], url, group.get("images") or [])
                    )
                    if isinstance(arr, list) and arr:
                        # Associate each item with its source content and images
                        for item in arr:
                            if isinstance(item, dict):
                                item["_source_type"] = "heading_group"
                                item["_source_index"] = i
                                item["_source_images"] = group.get("images", [])
                                item["_source_text"] = group["text"]
                        all_items.extend(arr)
                        processed_sources.append(("heading_group", i))
                except Exception as e:
                    print(f"[debug] Error processing heading group {i+1}: {e}", file=sys.stderr)

            # 2) Fallback: use candidate blocks if headings gave nothing or few results
            if len(all_items) < 3:  # If we have very few items from headings
                print("[debug] Few/no venues from headings, trying candidate blocks", file=sys.stderr)
                for i, block in enumerate(ctx.get("blocks", [])):
                    try:
                        print(f"[debug] Processing candidate block {i+1}/{len(ctx['blocks'])}", file=sys.stderr)
                        arr = call_gemini_json(
                            build_block_prompt(block.get("text", ""), url, block.get("images") or [])
                        )
                        if isinstance(arr, list) and arr:
                            # Associate each item with its source content and images
                            for item in arr:
                                if isinstance(item, dict):
                                    item["_source_type"] = "block"
                                    item["_source_index"] = i
                                    item["_source_images"] = block.get("images", [])
                                    item["_source_text"] = block.get("text", "")
                            all_items.extend(arr)
                            processed_sources.append(("block", i))
                    except Exception as e:
                        print(f"[debug] Error processing block {i+1}: {e}", file=sys.stderr)

            # 3) Last resort: JSON-LD
            if not all_items:
                print("[debug] No venues from headings or blocks, trying JSON-LD", file=sys.stderr)
                for j, raw in enumerate(ctx.get("jsonld_raw", [])):
                    try:
                        arr = call_gemini_json(build_block_prompt(raw, url, []))
                        if isinstance(arr, list) and arr:
                            for item in arr:
                                if isinstance(item, dict):
                                    item["_source_type"] = "jsonld"
                                    item["_source_index"] = j
                                    item["_source_images"] = []
                                    item["_source_text"] = raw
                            all_items.extend(arr)
                            processed_sources.append(("jsonld", j))
                    except Exception as e:
                        print(f"[debug] Error processing JSON-LD block {j+1}: {e}", file=sys.stderr)

        print(f"[debug] Total items before validation: {len(all_items)}", file=sys.stderr)
        print(f"[debug] Processed sources: {processed_sources}", file=sys.stderr)

        # IMPROVED: Better deduplication that preserves more items
        valid = []
        seen_venues = set()
        seen_titles = set()
        
        for item in all_items:
            if not isinstance(item, dict):
                continue
                
            # Create multiple keys to check for duplicates
            venue_name = safe_strip(item.get('venue_name', '')).lower()
            title = safe_strip(item.get('title', '')).lower()
            
            # Skip if we've seen this exact venue name and title combination
            venue_title_key = (venue_name, title)
            if venue_title_key in seen_venues:
                print(f"[debug] Skipping duplicate venue: {venue_name} - {title}", file=sys.stderr)
                continue
                
            # Skip if we've seen this exact title and it's substantial
            if title and len(title) > 10 and title in seen_titles:
                print(f"[debug] Skipping duplicate title: {title}", file=sys.stderr)
                continue
            
            # If venue name exists, add to venue set
            if venue_name:
                seen_venues.add(venue_title_key)
                
            # If title is substantial, add to title set
            if title and len(title) > 10:
                seen_titles.add(title)
                
            valid.append(item)
        
        print(f"[debug] Items after deduplication: {len(valid)}", file=sys.stderr)
        
        # Enhanced post-processing with better image handling
        for i, item in enumerate(valid):
            if isinstance(item, dict):
                item["guid"] = url
                item["url"] = url
                
                # Get the original source text for this item
                source_text = item.get("_source_text", "")
                source_images = item.get("_source_images", [])
                
                # Process pricing
                valid[i] = merge_price_fields(item, source_text)
                print(f"[debug] Final price for item {i+1}: {valid[i].get('price_display')}", file=sys.stderr)
                valid[i] = enrich_free_price_fields(valid[i])


                # Process address
                adr = extract_full_address(source_text)
                if not adr: 
                    adr = global_address(html)
                if adr: 
                    item["address_display"] = adr
                else: 
                    item["address_display"] = "Not Available"

                # Process operating hours
                date_time = extract_operating_hours(source_text)
                if date_time and not item.get("datetime_display"):
                    item["datetime_display"] = date_time

                # FIXED IMAGE HANDLING
                current_images = item.get("images", [])
                
                # If item has no images or empty images, assign from source
                if not current_images or (isinstance(current_images, list) and len(current_images) == 0):
                    print(f"[debug] Item {i+1} has no images, assigning from source", file=sys.stderr)
                    
                    # Use images from the specific source that generated this item
                    if source_images:
                        organiser = item.get("organiser", item.get("venue_name", "Unknown"))
                        item["images"] = [
                            {"url": img_url, "source_credit": organiser} 
                            for img_url in source_images[:3]  # Max 3 images per item
                        ]
                        print(f"[debug] Assigned {len(item['images'])} images from source to item {i+1}", file=sys.stderr)
                    
                    # If still no images, use fallback images
                    elif fallback_images:
                        organiser = item.get("organiser", item.get("venue_name", "Unknown"))
                        # Rotate through fallback images to avoid all items having the same image
                        start_idx = i % len(fallback_images)
                        selected_fallbacks = fallback_images[start_idx:start_idx+2]  # Max 2 fallback images
                        if len(selected_fallbacks) < 2 and len(fallback_images) > 1:
                            selected_fallbacks.extend(fallback_images[:2-len(selected_fallbacks)])
                        
                        item["images"] = [
                            {"url": img_url, "source_credit": organiser} 
                            for img_url in selected_fallbacks
                        ]
                        print(f"[debug] Assigned {len(item['images'])} fallback images to item {i+1}", file=sys.stderr)
                    else:
                        item["images"] = []
                        print(f"[debug] No images available for item {i+1}", file=sys.stderr)
                
                # Ensure images are in correct format
                elif isinstance(current_images, list):
                    formatted_images = []
                    organiser = item.get("organiser", item.get("venue_name", "Unknown"))
                    
                    for img in current_images:
                        if isinstance(img, str):
                            # Convert string URL to object format
                            formatted_images.append({"url": img, "source_credit": organiser})
                        elif isinstance(img, dict) and img.get("url"):
                            # Already in correct format, but ensure source_credit exists
                            if not img.get("source_credit"):
                                img["source_credit"] = organiser
                            formatted_images.append(img)
                    
                    item["images"] = formatted_images
                    print(f"[debug] Formatted {len(formatted_images)} existing images for item {i+1}", file=sys.stderr)

                # Clean up temporary fields
                for temp_field in ["_source_type", "_source_index", "_source_images", "_source_text"]:
                    item.pop(temp_field, None)

        # Final validation
        print(f"[debug] Final validation: {len(valid)} items", file=sys.stderr)
        for i, item in enumerate(valid):
            img_count = len(item.get("images", []))
            venue_name = item.get("venue_name", "Unknown")
            print(f"[debug] Item {i+1} ({venue_name}): {img_count} images", file=sys.stderr)

        #GIVING UNIQUE ID
        starting_id = load_id() + 1
        for idx, item in enumerate(valid,start=starting_id):
            item["id"] = idx
        image_dir = PROJECT_ROOT / "valid_data" / "November" /"19Nov"/"images"
        download_images(valid, image_dir)
        out_path = PROJECT_ROOT / "valid_data" / "November" /"19Nov"/"countdown_1.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        json_output = json.dumps(valid, ensure_ascii=False, indent=2)
        print(f"[debug] Writing {len(json_output)} chars to {out_path}", file=sys.stderr)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        
        if valid:
            save_id(valid[-1]["id"])

        print(f"[debug] File written successfully. File size: {out_path.stat().st_size} bytes", file=sys.stderr)
        print(json_output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("[]")

if __name__ == "__main__":
    main()