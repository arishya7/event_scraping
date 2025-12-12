from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import pandas as pd
from pathlib import Path
import time
import re

PROJECT_ROOT = Path(__file__).resolve().parent


def scrape_hdb_contractors():
    """
    Scrape all HDB contractors from the directory using Playwright.
    Handles pagination and alphabetical filtering with JavaScript interaction.
    """
    base_url = "https://services2.hdb.gov.sg/webapp/BN31AWERRCMobile/BN31PContractorResult.jsp"
    all_contractors = []

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)  # Set to True for production
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # Navigate to the page
        print("Loading initial page...")
        try:
            page.goto(base_url, wait_until='networkidle', timeout=60000)
            time.sleep(2)  # Wait for any JS to finish
        except PlaywrightTimeoutError:
            print("Initial page load timeout, continuing anyway...")

        # Letters to iterate through (A-Z plus Others)
        letters = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') + ['Others']

        for letter in letters:
            print(f"\n{'='*60}")
            print(f"Processing letter: {letter}")
            print(f"{'='*60}")

            try:
                # Click on the letter link
                print(f"  → Clicking on letter '{letter}'...")

                # Find and click the letter link
                letter_selector = f"a:has-text('{letter}')"
                try:
                    page.click(letter_selector, timeout=5000)
                    page.wait_for_load_state('networkidle', timeout=10000)
                    time.sleep(1)
                except Exception as e:
                    print(f"  ✗ Could not click letter '{letter}': {e}")
                    continue

                # Now scrape all pages for this letter
                page_num = 1
                while True:
                    print(f"  → Scraping page {page_num} for letter '{letter}'...")

                    try:
                        # Wait for table to be visible
                        page.wait_for_selector('table', timeout=10000)

                        # Extract the table data
                        rows = page.query_selector_all('table tr')

                        if len(rows) <= 1:  # Only header row or no rows
                            print(f"  ✓ No data rows found for letter '{letter}' page {page_num}")
                            break

                        page_contractors = []
                        # Skip header row (index 0)
                        for row in rows[1:]:
                            cols = row.query_selector_all('td')
                            if len(cols) >= 3:  # At least company name, address, phone
                                contractor = {
                                    'company_name': cols[0].inner_text().strip(),
                                    'case_trust': cols[1].inner_text().strip() if len(cols) > 1 else '',
                                    'address': cols[2].inner_text().strip() if len(cols) > 2 else '',
                                    'phone': cols[3].inner_text().strip() if len(cols) > 3 else '',
                                    'email': cols[4].inner_text().strip() if len(cols) > 4 else '',
                                    'letter_category': letter
                                }
                                page_contractors.append(contractor)

                        if not page_contractors:
                            print(f"  ✓ No contractors found on page {page_num}")
                            break

                        all_contractors.extend(page_contractors)
                        print(f"  ✓ Extracted {len(page_contractors)} contractors (Total: {len(all_contractors)})")

                        # Check for next page button/link
                        # Look for pagination - could be "Next", ">" or page numbers
                        next_button = None

                        # Try different selectors for next button
                        next_selectors = [
                            'a:has-text("Next")',
                            'a:has-text(">")',
                            f'a:has-text("{page_num + 1}")',
                            'a.next',
                            'button:has-text("Next")'
                        ]

                        for selector in next_selectors:
                            try:
                                next_button = page.query_selector(selector)
                                if next_button and next_button.is_visible():
                                    break
                            except:
                                continue

                        if next_button:
                            print(f"  → Moving to page {page_num + 1}...")
                            next_button.click()
                            page.wait_for_load_state('networkidle', timeout=10000)
                            time.sleep(1)
                            page_num += 1
                        else:
                            print(f"  ✓ No more pages for letter '{letter}'")
                            break

                    except PlaywrightTimeoutError:
                        print(f"  ✗ Timeout on page {page_num} for letter '{letter}'")
                        break
                    except Exception as e:
                        print(f"  ✗ Error on page {page_num} for letter '{letter}': {e}")
                        break

            except Exception as e:
                print(f"  ✗ Error processing letter '{letter}': {e}")
                continue

            # Small delay between letters
            time.sleep(1)

        browser.close()

    return all_contractors


def main():
    print("="*70)
    print("HDB Contractor Directory Scraper")
    print("="*70)
    print(f"Target: https://services2.hdb.gov.sg/webapp/BN31AWERRCMobile/BN31PContractorResult.jsp")
    print()

    # Scrape all contractors
    contractors = scrape_hdb_contractors()

    if not contractors:
        print("\n❌ No data scraped. Please check:")
        print("   - Website is accessible")
        print("   - Page structure hasn't changed")
        print("   - Playwright is installed correctly")
        return

    print(f"\n{'='*70}")
    print(f"✓ Successfully scraped {len(contractors)} contractors")
    print(f"{'='*70}")

    # Save to Excel
    output_dir = Path(PROJECT_ROOT.parent / "babies_data")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "hdb_contractors.xlsx"

    df = pd.DataFrame(contractors)
    df.to_excel(output_file, index=False)

    print(f"\n✓ Data saved to: {output_file}")
    print(f"\nTotal contractors by letter:")
    print(df['letter_category'].value_counts().sort_index())
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst few records:")
    print(df.head(10))


if __name__ == "__main__":
    main()
