from playwright.sync_api import sync_playwright
import json
from datetime import datetime

def scrape_nparks_events():
    events = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.nparks.gov.sg/visit/activities/fun-children", wait_until="networkidle")

        headings = page.query_selector_all("h2, h3, h4")

        # Inspect the NParks page and adjust selectors if needed
        event_cards = page.query_selector_all("article, .event-item, .event-card, li, div.event")  # Example selectors

        for idx, h in enumerate(headings):
            title = h.inner_text().strip()
            events.append({
                "id": f"nparks-{idx}",
                "title": title,
                "description": h.inner_text().strip(),
                "url": page.url,
                "scraped_at": datetime.now().isoformat()
            })

        browser.close()
    return events


if __name__ == "__main__":
    events = scrape_nparks_events()
    print(f"Found {len(events)} events")
    
    # Save to JSON (standalone)
    with open("nparks_events.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    
    print(" Saved events to nparks_events.json")
