from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import time
import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def extract_main_domain(url):
    """Extract the main domain from a URL, ignoring subdomains."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    domain_parts = parsed.netloc.split('.')
    
    # Handle cases like co.uk, com.au, etc.
    if len(domain_parts) > 2 and domain_parts[-2] in ['co', 'com', 'org', 'net']:
        return '.'.join(domain_parts[-3:])
    return '.'.join(domain_parts[-2:])

def parse_certificate_data(html_content):
    logger.debug("Starting to parse certificate data")
    
    if not html_content:
        logger.warning("Received empty HTML content")
        return None
        
    soup = BeautifulSoup(html_content, 'html.parser')
    logger.debug("Created BeautifulSoup object")
    
    # Find the main table containing certificate data (it's nested inside another table)
    outer_table = soup.find('table')
    if not outer_table:
        logger.warning("No outer table found")
        return None
        
    # Get the nested table that contains the certificate rows
    inner_table = outer_table.find('td', class_='outer').find('table')
    if not inner_table:
        logger.warning("No inner table found")
        return None
    
    # Get all rows except the header row
    rows = inner_table.find_all('tr')[1:]  # Skip header row
    logger.debug(f"Found {len(rows)} certificate rows")
    
    if not rows:
        logger.warning("No certificate rows found")
        return None
    
    # Get the last row (most recent certificate)
    last_row = rows[0]  # First row is the most recent since they're sorted by date
    cells = last_row.find_all('td')
    logger.debug(f"Processing last row with {len(cells)} cells")
    
    try:
        cert_id = cells[0].find('a').text.strip()
        logged_at = cells[1].text.strip()
        common_name = cells[4].text.strip()  # Common Name is in the 5th column
        
        logger.debug(f"Extracted raw data - ID: {cert_id}, Date: {logged_at}, CN: {common_name}")
        
        # Convert date from YYYY-MM-DD to DD-MM-YYYY
        try:
            date_obj = datetime.strptime(logged_at, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d-%m-%Y')
            logger.debug(f"Successfully formatted date from {logged_at} to {formatted_date}")
        except ValueError as e:
            logger.warning(f"Date parsing failed: {e}. Using original date format: {logged_at}")
            formatted_date = logged_at
        
        cert_data = {
            'type': 'First SSL Certificate',
            'common_name': common_name,
            'logged_at': formatted_date,
            'id': cert_id
        }
        
        logger.info(f"Successfully created certificate data: {cert_data}")
        return cert_data
        
    except Exception as e:
        logger.error(f"Error processing certificate data: {str(e)}")
        logger.error(f"Row content: {last_row}")
        return None

def get_first_certificate(domain):
    """
    Connect to crt.sh and attempt to retrieve certificate information.
    Returns tuple of (success, result), where result is either the data or error message.
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')  # Updated headless mode syntax
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')  # Required for some Linux systems
    chrome_options.add_argument('--remote-debugging-port=9222')  # Add debugging port
    chrome_options.add_argument('--window-size=1920,1080')  # Set window size
    
    max_retries = 3
    timeout = 5
    
    service = Service()  # Initialize Chrome service
    
    for attempt in range(max_retries):
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(timeout)
            
            url = f"https://crt.sh/?q={domain}"
            driver.get(url)
            
            # Check HTTP status code
            status_code = driver.execute_script("return window.performance.getEntries()[0].responseStatus") or 200
            logging.debug(f"crt.sh response status: {status_code}")
            
            # If we get a 4xx or 5xx status code, stop retrying
            if str(status_code).startswith(('4', '5')):
                return False, f"Server error: HTTP {status_code}"
            
            # Wait for the table to load
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            
            # Get the page source and parse it
            html_content = driver.page_source
            cert_data = parse_certificate_data(html_content)
            
            if cert_data:
                logging.info(f"Successfully retrieved certificate data for {domain}")
                return True, cert_data
            else:
                return False, "No certificate data found"
            
        except TimeoutException:
            error_msg = f"Timeout error on attempt {attempt + 1}/{max_retries}"
            logging.warning(f"crt.sh timeout for {domain}: {error_msg}")
            if attempt == max_retries - 1:
                return False, error_msg
            time.sleep(2)
            
        except WebDriverException as e:
            error_msg = f"Browser error: {str(e)}"
            logging.error(f"crt.sh browser error for {domain}: {error_msg}")
            # Don't retry on browser initialization errors
            if "DevToolsActivePort" in str(e) or "session not created" in str(e):
                return False, "Chrome browser initialization failed. Please check Chrome installation."
            if attempt == max_retries - 1:
                return False, error_msg
            time.sleep(2)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception as e:
                    logging.warning(f"Error closing browser: {str(e)}")
    
    return False, f"Failed after {max_retries} attempts"

def get_certificate_data(domain):
    # Your existing certificate fetching code
    # Should return the parsed certificate data
    try:
        html_content = fetch_certificate_data(domain)  # Your existing fetch function
        return parse_certificate_data(html_content)
    except Exception as e:
        logger.error(f"Error getting certificate data: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Get the first SSL certificate for a domain from crt.sh')
    parser.add_argument('url', help='The URL or domain to check (e.g., example.com or https://example.com)')
    args = parser.parse_args()

    # Extract the main domain
    domain = extract_main_domain(args.url)
    print(f"Extracted domain: {domain}")
    
    # Get certificate info
    print(f"Attempting to fetch certificate information from crt.sh...")
    success, result = get_first_certificate(domain)
    
    if success:
        print("\nCertificate found:")
        print(f"ID: {result['id']}")
        print(f"Logged at: {result['logged_at']}")
        print(f"Not Before: {result['not_before']}")
        print(f"Not After: {result['not_after']}")
        print(f"Common Name: {result['common_name']}")
        print(f"Matching Identities: {result['matching_identities']}")
        print(f"Issuer: {result['issuer']}")
    else:
        print("Failed!")
        print(f"Error: {result}")

if __name__ == "__main__":
    main() 