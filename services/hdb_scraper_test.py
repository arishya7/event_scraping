from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pandas as pd
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parent


def test_scrape_one_letter():
    """
    Test scraping with just one letter to verify the approach works
    """
    base_url = "https://services2.hdb.gov.sg/webapp/BN31AWERRCMobile/BN31PContractorResult.jsp"
    all_contractors = []

    with sync_playwright() as p:
        # Launch browser (not headless so we can see what's happening)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # Navigate to the page
        print("Loading initial page...")
        try:
            page.goto(base_url, wait_until='domcontentloaded', timeout=60000)
            time.sleep(3)  # Wait for any JS to finish
            print("Page loaded successfully!")
        except PlaywrightTimeoutError:
            print("Initial page load timeout, continuing anyway...")

        # Test with just letter 'A'
        letter = 'A'
        print(f"\n{'='*60}")
        print(f"Testing with letter: {letter}")
        print(f"{'='*60}")

        try:
            # Try to click on the letter link
            print(f"\n👆 Attempting to click letter '{letter}'...")

            # Try different approaches to find the letter link
            clicked = False

            # Approach 1: Direct text match with navigation wait
            try:
                # Wait for navigation after clicking
                with page.expect_navigation(timeout=10000):
                    page.click(f"text={letter}")
                print(f"   ✓ Clicked using text={letter} (navigation completed)")
                clicked = True
                time.sleep(2)  # Additional wait for JS
            except Exception as e1:
                print(f"   ✗ Approach 1 failed: {str(e1)[:100]}")

                # Approach 2: Using href attribute
                try:
                    link = page.query_selector(f'a[href*="alpha={letter}"]')
                    if link:
                        with page.expect_navigation(timeout=10000):
                            link.click()
                        print(f"   ✓ Clicked using href attribute (navigation completed)")
                        clicked = True
                        time.sleep(2)
                except Exception as e2:
                    print(f"   ✗ Approach 2 failed: {str(e2)[:100]}")

            if clicked:

                # Debug: save screenshot and HTML
                print("\n🔍 Debugging page after click...")
                screenshot_path = PROJECT_ROOT / "debug_screenshot.png"
                page.screenshot(path=str(screenshot_path))
                print(f"   Screenshot saved to: {screenshot_path}")

                # Get page HTML
                html_content = page.content()
                html_path = PROJECT_ROOT / "debug_page.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"   HTML saved to: {html_path}")

                # Now try to extract table data
                print("\n📊 Extracting table data...")

                # Find the table
                tables = page.query_selector_all('table')
                print(f"   Found {len(tables)} tables")

                for idx, table in enumerate(tables):
                    rows = table.query_selector_all('tr')
                    print(f"\n   Table {idx + 1}: {len(rows)} rows")

                    if len(rows) > 1:
                        # Print first few rows to see structure
                        for i, row in enumerate(rows[:5]):
                            cols = row.query_selector_all('td')
                            if cols:
                                col_texts = [col.inner_text().strip()[:50] for col in cols]
                                print(f"     Row {i}: {col_texts}")

                        # Extract actual data
                        for row in rows[1:]:  # Skip header
                            cols = row.query_selector_all('td')
                            if len(cols) >= 3:
                                contractor = {
                                    'company_name': cols[0].inner_text().strip(),
                                    'case_trust': cols[1].inner_text().strip() if len(cols) > 1 else '',
                                    'address': cols[2].inner_text().strip() if len(cols) > 2 else '',
                                    'phone': cols[3].inner_text().strip() if len(cols) > 3 else '',
                                    'email': cols[4].inner_text().strip() if len(cols) > 4 else '',
                                    'letter_category': letter
                                }
                                all_contractors.append(contractor)

                print(f"\n✓ Extracted {len(all_contractors)} contractors for letter '{letter}'")

                # Check pagination
                print("\n🔢 Checking for pagination...")
                pagination_elements = page.query_selector_all('a, button')
                pagination_texts = []
                for elem in pagination_elements:
                    text = elem.inner_text().strip().lower()
                    if any(word in text for word in ['next', 'previous', 'page', '>', '<', '»', '«']):
                        pagination_texts.append(text)

                if pagination_texts:
                    print(f"   Pagination elements found: {pagination_texts}")
                else:
                    print("   No obvious pagination found")

        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()

        # Keep browser open for a moment to inspect
        print("\n⏸️  Browser will stay open for 5 seconds...")
        time.sleep(5)

        browser.close()

    return all_contractors


if __name__ == "__main__":
    print("="*70)
    print("HDB Contractor Scraper - TEST MODE")
    print("="*70)
    print("Testing with letter 'A' only to verify the approach\n")

    contractors = test_scrape_one_letter()

    if contractors:
        print(f"\n{'='*70}")
        print(f"✅ SUCCESS! Scraped {len(contractors)} contractors")
        print(f"{'='*70}")
        print("\nSample data:")
        for c in contractors[:5]:
            print(f"  - {c['company_name']}")
            print(f"    📍 {c['address'][:80]}")
            print(f"    📞 {c['phone']}")
            print(f"    📧 {c['email']}")
            print()
    else:
        print("\n❌ No contractors scraped - need to adjust selectors")
