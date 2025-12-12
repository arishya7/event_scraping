import csv
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from typing import Set, List
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailScraper:
    def __init__(self, delay=2):
        """
        Initialize the email scraper.

        Args:
            delay: Delay in seconds between requests (default: 2)
        """
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def extract_emails_from_text(self, text: str) -> Set[str]:
        """
        Extract email addresses from text using regex.

        Args:
            text: Text to search for emails

        Returns:
            Set of unique email addresses found
        """
        # Email regex pattern
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = set(re.findall(email_pattern, text))

        # Filter out common false positives
        filtered_emails = {
            email for email in emails
            if not any(x in email.lower() for x in ['example.com', 'domain.com', 'yourdomain', 'sentry'])
        }

        return filtered_emails

    def scrape_website(self, url: str) -> Set[str]:
        """
        Scrape a website for email addresses.

        Args:
            url: Website URL to scrape

        Returns:
            Set of unique email addresses found
        """
        emails = set()
        visited_urls = set()

        try:
            # Normalize URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            base_domain = urlparse(url).netloc

            # Pages to check (homepage, contact, about)
            pages_to_check = [
                url,
                urljoin(url, '/contact'),
                urljoin(url, '/contact-us'),
                urljoin(url, '/contact us'),
                urljoin(url, '/about'),
                urljoin(url, '/about-us'),
            ]

            for page_url in pages_to_check:
                if page_url in visited_urls:
                    continue

                try:
                    logger.info(f"Checking: {page_url}")
                    response = self.session.get(page_url, timeout=15, allow_redirects=True)
                    response.raise_for_status()
                    visited_urls.add(page_url)

                    # Extract emails from page text
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Extract emails from the raw HTML first (catches obfuscated emails)
                    raw_emails = self.extract_emails_from_text(response.text)
                    emails.update(raw_emails)

                    # Remove script and style elements
                    for script in soup(['script', 'style']):
                        script.decompose()

                    # Get text content from entire page
                    text = soup.get_text()
                    page_emails = self.extract_emails_from_text(text)
                    emails.update(page_emails)

                    # Also check mailto links
                    mailto_links = soup.find_all('a', href=re.compile(r'^mailto:', re.I))
                    for link in mailto_links:
                        email = link.get('href', '').replace('mailto:', '').split('?')[0].strip()
                        if email and '@' in email:
                            emails.add(email.lower())

                    # Check all href attributes for emails and follow email-related links
                    all_links = soup.find_all('a', href=True)
                    email_related_links = []

                    for link in all_links:
                        href = link.get('href', '')
                        found_emails = self.extract_emails_from_text(href)
                        emails.update(found_emails)

                        # Check link text and attributes for emails (for mail icon links)
                        link_text = link.get_text().strip().lower()
                        found_emails = self.extract_emails_from_text(link.get_text())
                        emails.update(found_emails)

                        # Check data attributes and title that might contain emails
                        for attr in ['data-email', 'data-mail', 'title', 'aria-label']:
                            attr_value = link.get(attr, '')
                            if attr_value:
                                found_emails = self.extract_emails_from_text(attr_value)
                                emails.update(found_emails)

                        # Identify links that might lead to email pages (mail icons, email buttons, etc.)
                        link_class = ' '.join(link.get('class', [])).lower()
                        link_id = link.get('id', '').lower()

                        # Check if link seems to be email-related
                        email_indicators = ['mail', 'email', 'envelope', 'contact']
                        if any(indicator in link_text for indicator in email_indicators) or \
                           any(indicator in link_class for indicator in email_indicators) or \
                           any(indicator in link_id for indicator in email_indicators):
                            # Convert to absolute URL
                            full_url = urljoin(page_url, href)
                            # Only follow links on the same domain
                            if urlparse(full_url).netloc == base_domain and full_url not in visited_urls:
                                email_related_links.append(full_url)

                    # Follow email-related links (limit to avoid too many requests)
                    for email_link in email_related_links[:3]:
                        if email_link in visited_urls:
                            continue

                        try:
                            logger.info(f"Following email-related link: {email_link}")
                            email_response = self.session.get(email_link, timeout=15, allow_redirects=True)
                            email_response.raise_for_status()
                            visited_urls.add(email_link)

                            # Extract emails from this page
                            email_soup = BeautifulSoup(email_response.text, 'html.parser')
                            email_text = email_soup.get_text()
                            link_emails = self.extract_emails_from_text(email_text)
                            emails.update(link_emails)

                            # Also check raw HTML
                            raw_link_emails = self.extract_emails_from_text(email_response.text)
                            emails.update(raw_link_emails)

                            time.sleep(self.delay)
                        except requests.exceptions.RequestException as e:
                            logger.warning(f"Error following email link {email_link}: {str(e)}")
                            continue

                    # Check meta tags
                    meta_emails = soup.find_all('meta', attrs={'name': re.compile(r'email', re.I)})
                    for meta in meta_emails:
                        content = meta.get('content', '')
                        page_emails = self.extract_emails_from_text(content)
                        emails.update(page_emails)

                    # Check contact info in footer, header, and contact sections
                    for section in soup.find_all(['footer', 'header', 'div'], class_=re.compile(r'contact|footer|header', re.I)):
                        section_text = section.get_text()
                        section_emails = self.extract_emails_from_text(section_text)
                        emails.update(section_emails)

                    # Delay between requests
                    time.sleep(self.delay)

                except requests.exceptions.RequestException as e:
                    logger.warning(f"Error fetching {page_url}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")

        return emails

    def process_csv(self, input_file: str, output_file: str, website_column: str = 'Website'):
        """
        Process a CSV file and scrape emails for each website.

        Args:
            input_file: Path to input CSV file
            output_file: Path to output CSV file
            website_column: Name of the column containing website URLs
        """
        results = []

        # Read input CSV
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        logger.info(f"Processing {len(rows)} companies...")

        # Process each row
        for idx, row in enumerate(rows, 1):
            website = row.get(website_column, '').strip()
            company_name = row.get('Name', 'Unknown')

            logger.info(f"[{idx}/{len(rows)}] Processing: {company_name}")

            if not website:
                logger.warning(f"No website found for {company_name}")
                row['Emails'] = ''
                results.append(row)
                continue

            # Scrape emails
            emails = self.scrape_website(website)

            if emails:
                logger.info(f"Found {len(emails)} email(s): {', '.join(emails)}")
                row['Emails'] = ', '.join(sorted(emails))
            else:
                logger.info("No emails found")
                row['Emails'] = ''

            results.append(row)

        # Write output CSV
        if results:
            fieldnames = list(results[0].keys())
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)

            logger.info(f"Results saved to {output_file}")

        # Print summary
        total_companies = len(results)
        companies_with_emails = sum(1 for r in results if r.get('Emails'))
        logger.info(f"\n=== Summary ===")
        logger.info(f"Total companies processed: {total_companies}")
        logger.info(f"Companies with emails found: {companies_with_emails}")
        logger.info(f"Success rate: {companies_with_emails/total_companies*100:.1f}%")


def main():
    """Main function to run the email scraper."""
    # Configuration
    input_csv = 'services/home_market/home_services_2.csv'
    output_csv = 'services/home_market/home_services__2with_emails.csv'

    # Create scraper instance
    scraper = EmailScraper(delay=2)  # 2 second delay between requests

    # Process the CSV file
    scraper.process_csv(input_csv, output_csv)


if __name__ == '__main__':
    main()
