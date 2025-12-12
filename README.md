# Event Scraping Project

A comprehensive web scraping and data processing pipeline for extracting, enriching, and managing event/activity data with location intelligence and image handling.

## Table of Contents
- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Workflow](#workflow)
- [Source Files (src/)](#source-files-src)
- [Services (services/)](#services-services)

## Overview

This project automates the extraction of event/activity data from various websites, enriches it with location information (coordinates, planning areas, regions), downloads and processes images, and prepares validated CSV outputs for production use.


## Installation

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export GOOGLE_API_KEY="your_google_api_key" (places api and generative are different api keys)
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

## Project Structure

```
event_scraping/
├── src/                    # Main event scraping and processing
├── services/              # Specialized scrapers for different sources
├── config/                # Configuration files (schema, instructions, districts)
├── valid_data/           # Validated event data organized by date
├── other_data/           # Additional scraped data
└── requirements.txt      # Python dependencies
```

---

## Source Files (src/)

### 1. scraper_gemini.py (PRIMARY SCRAPER)
**Purpose**: Main event/activity extraction tool using Gemini AI

**Key Features**:
- Web scraping using Playwright and BeautifulSoup
- AI-powered content extraction via Google Gemini API
- Automatic image downloading and processing
- Character encoding normalization
- JSON schema validation

**Dependencies**:
- Google Gemini API
- Playwright (browser automation)
- BeautifulSoup4 (HTML parsing)
- PIL/Pillow (image processing)
- jsonschema (validation)

**Usage**:
```python
python src/scraper_gemini.py
```

**Output**: JSON files with event data + downloaded images

---

### 2. location.py
**Purpose**: Enrich event data with location intelligence

**Key Features**:
- Google Places API integration for address resolution
- Geocoding (latitude/longitude extraction)
- Planning area and region mapping using Singapore GeoJSON districts
- Batch processing for multiple JSON files

**Dependencies**:
- Google Places API
- geopandas (geospatial analysis)
- shapely (geometric operations)
- pandas (data processing)

**Usage**:
```python
python src/location.py
```

**Enriches each event with**:
- `address_display`: Formatted full address
- `longitude`, `latitude`: Coordinates
- `planning_area`: Singapore planning area
- `region`: Geographic region

---

### 3. cleaning_csv.py
**Purpose**: Clean and standardize CSV format for database upload (very important)

**Key Features**:
- Column ordering and standardization
- JSON field validation and formatting
- Newline character normalization
- Quote escaping for CSV safety

**Column Order**:
```
id, title, organiser, blurb, description, guid, activity_or_event, url,
is_free, price_display_teaser, price_display, price, min_price, max_price,
age_group_display, min_age, max_age, datetime_display_teaser, datetime_display,
start_datetime, end_datetime, venue_name, address_display, categories, images,
longitude, latitude, checked, source_file, region, planning_area,
label_tag, keyword_tag
```

**Usage**:
```python
python src/cleaning_csv.py
```

---

### 4. merging.py / convertjson.py
**Status**: Deprecated utility files (not actively used)

---

## Services (services/)

Specialized scrapers for different data sources and business directories.

### 1. category.py
**Purpose**: Categorize companies from Zoho CRM into baby/maternity product categories

**Key Features**:
- Playwright-based web scraping
- AI-powered categorization using Gemini
- Multi-category classification

**Categories Include**:
- Baby Products: Strollers, Carseat, Carriers, Cots, Toys, Clothing
- Feeding: Breastpumps, Bottles, Food Processor, Weaning
- Health: Baby Supplements, Chicken Essence, Baby Skincare
- Services: Swim School, Photography, Maid Agency, Confinement Food, Hospital
- And 30+ more categories

**Usage**:
```python
python services/category.py
```

---

### 2. email_scraper.py
**Purpose**: Extract email addresses from websites

**Key Features**:
- Recursive website crawling
- Email pattern matching with regex
- False positive filtering
- CSV export

**Usage**:
```python
from services.email_scraper import EmailScraper
scraper = EmailScraper(delay=2)
emails = scraper.scrape_website("https://example.com")
```

---

### 3. hdb_scraper.py
**Purpose**: Scrape HDB contractor directory

**Key Features**:
- Alphabetical pagination handling
- JavaScript-rendered content scraping
- Contractor details extraction

**Data Extracted**:
- Company name
- Contact information
- Registration details

**Usage**:
```python
python services/hdb_scraper.py
```

---

### 4. casetrust_scraper.py
**Purpose**: Scrape CaseTrust accredited businesses directory

**Key Features**:
- Business listing extraction
- Contact detail parsing (email, phone)
- Retry logic with exponential backoff

**Usage**:
```python
python services/casetrust_scraper.py
```

---

## Workflow

### Complete Event Processing Pipeline:

1. **Scrape Events**
   ```bash
   python src/scraper_gemini.py
   ```
   Extracts events/activities and downloads images

2. **Add Location Data**
   ```bash
   python src/location.py
   ```
   Enriches with addresses, coordinates, planning areas, and regions

3. **Transfer to Review System**
   - Export JSON files to review laptop
   - Add local image paths
   - Run review UI for human validation

4. **Post-Review Processing**
   - Format JSON files
   - Combine multiple JSONs into one
   - Convert to CSV
   - Run CSV validation
   - Downsize images

5. **Prepare for Production**
   ```bash
   python src/cleaning_csv.py
   ```
   - Reorder columns
   - Format and validate
   - Send final CSV to apps team

6. **Database Upload**
   - Wait for CSV to be uploaded to live
   - Download the live CSV
   - Run through `cleaning_csv.py` again
   - Upload to MySQL database

---

## Configuration Files

- **config/config.json**: JSON schema for event validation
- **config/instructions.txt**: Gemini AI extraction instructions
- **config/venue.txt**: Venue-specific processing rules
- **config/districts.geojson**: Singapore planning area boundaries

---


## Notes
- there are lots of data files - not really necessary so can either delete or just keep
- valid_data, loc_data, other_data, category are all folders with data that was scraped 
- play_around was just for testing and trying different methods (not rly important)