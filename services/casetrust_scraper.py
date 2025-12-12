import csv
import requests
from bs4 import BeautifulSoup
import time
import logging
import re
from typing import List, Dict
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CaseTrustScraper:
    def __init__(self, delay=2):
        """
        Initialize the CaseTrust directory scraper.

        Args:
            delay: Delay in seconds between requests (default: 2)
        """
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        })
        self.base_url = 'https://www.case.org.sg'

    def extract_emails(self, text: str) -> str:
        """Extract emails from text."""
        if not text:
            return ''
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        # Filter out common false positives
        filtered = [e for e in emails if not any(x in e.lower() for x in ['example.com', 'domain.com', 'sentry'])]
        return ', '.join(set(filtered)) if filtered else ''

    def extract_phone(self, text: str) -> str:
        """Extract phone numbers from text."""
        if not text:
            return ''
        # Singapore phone patterns
        phone_pattern = r'(?:\+65\s?)?[689]\d{3}[\s-]?\d{4}'
        phones = re.findall(phone_pattern, text)
        return ', '.join(set(phones)) if phones else ''

    def scrape_company_detail(self, company_url: str) -> Dict[str, str]:
        """
        Scrape individual company detail page.

        Args:
            company_url: URL of company detail page

        Returns:
            Dictionary with additional company details
        """
        details = {
            'email': '',
            'phone': '',
            'address': '',
            'website': ''
        }

        try:
            logger.info(f"Scraping detail page: {company_url}")
            response = self.session.get(company_url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Get all text
            page_text = soup.get_text()

            # Extract contact info
            details['email'] = self.extract_emails(page_text)
            details['phone'] = self.extract_phone(page_text)

            # Look for address
            address_keywords = soup.find_all(text=re.compile(r'Address|Office|Location', re.I))
            for keyword in address_keywords:
                parent = keyword.find_parent()
                if parent:
                    addr_text = parent.get_text()
                    # Simple address extraction
                    if 'Singapore' in addr_text:
                        details['address'] = addr_text.strip()
                        break

            # Look for website
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if href.startswith('http') and 'case.org.sg' not in href.lower():
                    details['website'] = href
                    break

            time.sleep(self.delay)

        except Exception as e:
            logger.error(f"Error scraping detail page {company_url}: {str(e)}")

        return details

    def scrape_search_results(self, contractor_type: str, search_term: str = '') -> List[Dict[str, str]]:
        """
        Scrape search results for a specific contractor type and search term.

        Args:
            contractor_type: Type of contractor (e.g., 'Renovation Contractor', 'Window Contractor')
            search_term: Search term (letter or company name)

        Returns:
            List of company dictionaries
        """
        companies = []

        try:
            # The actual search URL - adjust based on the real form submission
            search_url = 'https://www.case.org.sg/casetrust/directory'

            # Form data - you'll need to inspect the actual form to get correct field names
            form_data = {
                'type': contractor_type,
                'search': search_term
            }

            logger.info(f"Searching for {contractor_type} - term: '{search_term}'")

            # Try GET request with params first
            response = self.session.get(search_url, params=form_data, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Parse results - adjust selectors based on actual HTML structure
            # Common patterns to try:
            result_containers = (
                soup.find_all('div', class_=re.compile(r'company|result|listing|item|card', re.I)) or
                soup.find_all('div', {'data-company': True}) or
                soup.find_all('tr') or
                soup.find_all('li', class_=re.compile(r'company|result|listing', re.I))
            )

            logger.info(f"Found {len(result_containers)} potential result containers")

            for container in result_containers:
                company = {
                    'company_name': '',
                    'address': '',
                    'phone': '',
                    'email': '',
                    'website': '',
                    'contractor_type': contractor_type,
                    'reference_number': ''
                }

                # Extract company name
                name_elem = (
                    container.find(['h1', 'h2', 'h3', 'h4', 'h5']) or
                    container.find('a', class_=re.compile(r'name|title|company', re.I)) or
                    container.find('strong') or
                    container.find('b')
                )

                if name_elem:
                    company['company_name'] = name_elem.get_text().strip()

                # Get all text from container
                container_text = container.get_text()

                # Extract contact info
                company['phone'] = self.extract_phone(container_text)
                company['email'] = self.extract_emails(container_text)

                # Look for reference number
                ref_match = re.search(r'(?:Ref|Reference|No)[:\s#]*([A-Z0-9-]+)', container_text, re.I)
                if ref_match:
                    company['reference_number'] = ref_match.group(1)

                # Look for detail page link
                detail_link = container.find('a', href=True)
                if detail_link:
                    detail_url = detail_link.get('href')
                    if detail_url and not detail_url.startswith(('http', 'mailto', 'tel', '#', 'javascript')):
                        detail_url = urljoin(self.base_url, detail_url)

                        # Scrape detail page for more info
                        detail_info = self.scrape_company_detail(detail_url)

                        # Update company info with details (don't overwrite if already found)
                        if detail_info['email'] and not company['email']:
                            company['email'] = detail_info['email']
                        if detail_info['phone'] and not company['phone']:
                            company['phone'] = detail_info['phone']
                        if detail_info['address'] and not company['address']:
                            company['address'] = detail_info['address']
                        if detail_info['website']:
                            company['website'] = detail_info['website']

                # Only add if we have at least a company name
                if company['company_name']:
                    companies.append(company)
                    logger.info(f"Found: {company['company_name']}")

            time.sleep(self.delay)

        except Exception as e:
            logger.error(f"Error scraping search results for {contractor_type} - '{search_term}': {str(e)}")

        return companies

    def scrape_contractor_type(self, contractor_type: str) -> List[Dict[str, str]]:
        """
        Scrape all companies for a specific contractor type by searching A-Z.

        Args:
            contractor_type: Type of contractor

        Returns:
            List of all companies found
        """
        all_companies = []
        seen_companies = set()

        # First try empty search to get all
        logger.info(f"\n{'='*60}")
        logger.info(f"Scraping: {contractor_type}")
        logger.info(f"{'='*60}")

        companies = self.scrape_search_results(contractor_type, '')
        for company in companies:
            comp_key = company['company_name'].lower()
            if comp_key not in seen_companies:
                seen_companies.add(comp_key)
                all_companies.append(company)

        # Then search A-Z to catch any missed
        for letter in 'abcdefghijklmnopqrstuvwxyz':
            logger.info(f"Searching {contractor_type} - Letter: {letter.upper()}")
            companies = self.scrape_search_results(contractor_type, letter)

            for company in companies:
                comp_key = company['company_name'].lower()
                if comp_key not in seen_companies:
                    seen_companies.add(comp_key)
                    all_companies.append(company)

        logger.info(f"Total found for {contractor_type}: {len(all_companies)}")
        return all_companies

    def scrape_all_types(self, output_file: str):
        """
        Scrape all contractor types and save to CSV.

        Args:
            output_file: Path to output CSV file
        """
        # Contractor types to scrape
        contractor_types = [
            'CaseTrust Accredited Contractor',
            'Renovation Contractor',
            'Window Contractor',
            'Renovation and Window Contractor'
        ]

        all_companies = []

        for contractor_type in contractor_types:
            companies = self.scrape_contractor_type(contractor_type)
            all_companies.extend(companies)

        # Write to CSV
        if all_companies:
            fieldnames = ['company_name', 'contractor_type', 'address', 'phone', 'email', 'website', 'reference_number']
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_companies)

            logger.info(f"\n{'='*60}")
            logger.info(f"Results saved to: {output_file}")
            logger.info(f"{'='*60}")

        # Print summary
        companies_with_emails = sum(1 for c in all_companies if c.get('email'))
        companies_with_phones = sum(1 for c in all_companies if c.get('phone'))

        logger.info(f"\n=== SUMMARY ===")
        logger.info(f"Total companies found: {len(all_companies)}")
        logger.info(f"Companies with emails: {companies_with_emails}")
        logger.info(f"Companies with phones: {companies_with_phones}")

        # Breakdown by type
        for contractor_type in contractor_types:
            count = sum(1 for c in all_companies if c['contractor_type'] == contractor_type)
            logger.info(f"{contractor_type}: {count}")


def main():
    """Main function to run the CaseTrust scraper."""

    logger.info("="*60)
    logger.info("CaseTrust Directory Scraper")
    logger.info("="*60)

    # Configuration
    output_csv = 'services/home_market/casetrust_contractors.csv'

    # Create scraper instance
    scraper = CaseTrustScraper(delay=2)

    # Run the scraper
    scraper.scrape_all_types(output_csv)


if __name__ == '__main__':
    main()
