from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin 
from src.get_links import get_all_links
import re


def extract_main_content(url: str) -> dict:
    data = {
        "title": None,
        "organiser": None,
        "paragraphs": None,
        "blurb": None,
        "description": None,
        "images": [],
        "url": url,
        "activity_or_event": None,
        "contact": None,
        "venue_name": None,
        "venue_address": None,
        "datetime_display": None,
        "datetime_start": None,
        "datetime_end": None,
        "registration_info": None,
        "eligibility": None,
        "price_display": None,
        "price": None,
        "tags": [],
        "categories": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"Navigating to {url}")
        page.goto(url, timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        content = page.content()
        browser.close()

    soup = BeautifulSoup(content, "html.parser")

    # Title
    data["title"] = (soup.title.string.strip() if soup.title else None) or \
                    (soup.find("h1").get_text(strip=True) if soup.find("h1") else None)

    # Paragraphs & blurb
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    data["paragraphs"] = "\n".join(paragraphs) if paragraphs else None
    data["blurb"] = paragraphs[0] if paragraphs else None
    data["description"] = data["paragraphs"]

    # Images
    data["images"] = [img.get("src") for img in soup.find_all("img") if img.get("src")]

    # Meta tags fallback
    meta_desc = soup.find("meta", attrs={"name": "description"}) or \
                soup.find("meta", attrs={"property": "og:description"}) or \
                soup.find("meta", attrs={"name": "twitter:description"})
    if meta_desc:
        meta_content = meta_desc.get("content", "").strip()
        if not data["blurb"]:
            data["blurb"] = meta_content
        if not data["description"]:
            data["description"] = meta_content

    # Organizer
    org_labels = ["Organiser", "Organizer", "By", "Author", "Name"]
    for label in org_labels:
        tag = soup.find(string=re.compile(f"{label}", re.I))
        if tag:
            sibling = tag.find_next(string=True)
            if sibling:
                data["organiser"] = sibling.strip()
            break

    # Venue
    venue_labels = ["Venue", "Location", "Place", "Where", "Address"]
    for label in venue_labels:
        tag = soup.find(string=re.compile(f"{label}", re.I))
        if tag:
            sibling = tag.find_next(string=True)
            if sibling:
                data["venue_name"] = sibling.strip()
            break

    # Price
    price_tag = soup.find(string=re.compile(r"\$\d+|\bFree\b", re.I))
    if price_tag:
        data["price_display"] = price_tag.strip()
        match = re.search(r"\d+", price_tag)
        data["price"] = int(match.group()) if match else 0

    # Datetime
    time_tags = soup.find_all("time")
    if time_tags:
        data["datetime_display"] = "; ".join([t.get_text(strip=True) for t in time_tags])
        data["datetime_start"] = time_tags[0].get("datetime") if time_tags[0].get("datetime") else None

    # Categories & tags
    keywords = soup.find("meta", attrs={"name": "keywords"})
    if keywords:
        data["categories"] = [k.strip() for k in keywords["content"].split(",")]
        data["tags"] = data["categories"]

    return data
if __name__ == "__main__":
    seed = input("Enter seed URL:").strip()
    #1 get all links
    links = get_all_links(seed)
    print(f"Found {len(links)} links on {seed}:")
    for i, link in enumerate(links):
        print(f"[{i}],{link}")

    choice = int(input("Enter index of link to get content from: "))
    chosen = links[choice]

    print(f"extracting content from {chosen}")
    article = extract_main_content(chosen)
    print(article)