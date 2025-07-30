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
    """Parse the HTML content from crt.sh and extract certificate information."""
    logging.debug("Starting to parse certificate data")
    
    if not html_content:
        logging.warning("Received empty HTML content")
        return None
        
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        logging.debug("Created BeautifulSoup object")
        
        # Find all tables
        tables = soup.find_all('table')
        logging.debug(f"Found {len(tables)} tables")
        
        # The certificate data is typically in the table with the most rows
        cert_table = None
        max_rows = 0
        
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            logging.debug(f"Table {i} has {len(rows)} rows")
            if len(rows) > max_rows:
                max_rows = len(rows)
                cert_table = table
        
        if not cert_table:
            logging.warning("No tables found with rows")
            return None
            
        rows = cert_table.find_all('tr')
        logging.debug(f"Using table with {len(rows)} rows")
        
        if len(rows) < 2:  # Need at least header row and one data row
            logging.warning("No certificate rows found")
            return None
        
        # Get the last row (most recent certificate)
        data_row = rows[-1]  # Get the last row
        cells = data_row.find_all(['td', 'th'])
        
        logging.debug(f"Processing last row with {len(cells)} cells")
        logging.debug(f"Cell contents: {[cell.text.strip() for cell in cells]}")
        
        if len(cells) < 6:  # crt.sh typically has at least 6 columns
            logging.warning(f"Unexpected number of cells: {len(cells)}")
            return None
            
        try:
            # Extract the certificate ID and create source URL
            cert_id = None
            id_link = cells[0].find('a')
            if id_link and 'href' in id_link.attrs:
                # Extract ID from href that looks like "?id=1234"
                href = id_link['href']
                cert_id = href.split('=')[-1] if '=' in href else None
            
            if not cert_id:
                cert_id = cells[0].text.strip()
            
            source_url = f"https://crt.sh/?id={cert_id}"
            
            # Get other certificate details
            logged_at = cells[1].text.strip()
            not_before = cells[2].text.strip()
            common_name = cells[4].text.strip()
            
            # Convert date format if needed
            try:
                logged_date = datetime.strptime(logged_at, '%Y-%m-%d')
                logged_at = logged_date.strftime('%d-%m-%Y')
            except ValueError:
                logging.warning(f"Could not parse date format: {logged_at}")
                # Keep original format if parsing fails
            
            try:
                valid_from = datetime.strptime(not_before, '%Y-%m-%d')
                not_before = valid_from.strftime('%d-%m-%Y')
            except ValueError:
                logging.warning(f"Could not parse date format: {not_before}")
                # Keep original format if parsing fails
            
            cert_data = {
                'type': 'SSL Certificate',
                'Common Name': common_name,
                'First Seen': logged_at,
                'Valid From': not_before,
                'Source': source_url
            }
            
            logging.info(f"Successfully parsed certificate data: {cert_data}")
            return cert_data
            
        except Exception as e:
            logging.error(f"Error extracting cell data: {str(e)}")
            logging.error(f"Row content: {data_row}")
            return None
            
    except Exception as e:
        logging.error(f"Error parsing certificate data: {str(e)}")
        return None

def check_crtsh_status(driver, timeout=30):
    """
    Check if crt.sh is responding and not showing a server error.
    Returns tuple of (is_up, error_message)
    """
    try:
        # First try a quick check with shorter timeout
        driver.set_page_load_timeout(10)
        try:
            driver.get("https://crt.sh")
        except Exception:
            # If quick check fails, try again with longer timeout
            driver.set_page_load_timeout(timeout)
            try:
                driver.get("https://crt.sh")
            except Exception as e:
                return False, f"crt.sh is responding too slowly or may be offline: {str(e)}"
        
        # Check for common server error indicators
        error_texts = [
            "502 Bad Gateway",
            "503 Service Temporarily Unavailable",
            "504 Gateway Time-out",
            "500 Internal Server Error",
            "Database connection failed",
            "Too Many Requests"
        ]
        
        try:
            # Use WebDriverWait to check for page load
            WebDriverWait(driver, 5).until(
                lambda d: len(d.page_source) > 0
            )
        except TimeoutException:
            return False, "crt.sh page load timeout"
            
        page_source = driver.page_source.lower()
        for error in error_texts:
            if error.lower() in page_source:
                return False, f"crt.sh is experiencing issues: {error}"
        
        return True, None
        
    except Exception as e:
        return False, f"crt.sh appears to be down: {str(e)}"

def get_first_certificate(domain):
    """
    Connect to crt.sh and attempt to retrieve certificate information.
    Returns tuple of (success, result), where result is either the data or error message.
    """
    logging.debug(f"Starting certificate search for domain: {domain}")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--dns-prefetch-disable')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    chrome_options.page_load_strategy = 'eager'  # Don't wait for all resources
    
    # Add more detailed logging
    logging.debug("Chrome options configured")
    
    max_retries = 3
    timeout = 45  # Increased timeout to 45 seconds for better loading
    
    try:
        for attempt in range(max_retries):
            driver = None
            service = None
            try:
                logging.debug(f"Attempt {attempt + 1}/{max_retries} to get certificate data")
                
                # Create a new service for each attempt
                service = Service()
                logging.debug("Chrome service initialized")
                
                # Add a small delay between attempts
                if attempt > 0:
                    time.sleep(5)
                
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                # Set initial shorter timeout for quick checks
                driver.set_page_load_timeout(20)
                
                # Check if crt.sh is up and responding
                is_up, error_message = check_crtsh_status(driver)
                if not is_up:
                    logging.error(error_message)
                    return False, {
                        'type': 'SSL Certificate',
                        'error': error_message,
                        'status': 'Service Unavailable',
                        'message': 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.'
                    }
                
                # If initial check passed, set longer timeout for actual query
                driver.set_page_load_timeout(timeout)
                url = f"https://crt.sh/?q={domain}"
                logging.debug(f"Accessing URL: {url}")
                
                try:
                    driver.get(url)
                except TimeoutException:
                    logging.warning("Initial quick attempt timed out, trying with longer timeout")
                    # If quick attempt fails, try one more time with full timeout
                    try:
                        driver.get(url)
                    except TimeoutException as e:
                        return False, {
                            'type': 'SSL Certificate',
                            'error': str(e),
                            'status': 'Timeout',
                            'message': 'Unable to retrieve certificate data. The crt.sh website is responding too slowly.'
                        }
                
                # Wait for initial table to load with a more specific selector
                logging.debug("Waiting for table to load...")
                try:
                    # First wait for any table to appear
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "table"))
                    )
                    logging.debug("Table element found")

                    # Then wait for rows to be present
                    WebDriverWait(driver, timeout).until(
                        lambda d: len(d.find_elements(By.TAG_NAME, "tr")) > 0
                    )
                    logging.debug("Table rows found")

                    # Finally wait for actual content
                    WebDriverWait(driver, timeout).until(
                        lambda d: any(
                            cell.text.strip() 
                            for row in d.find_elements(By.TAG_NAME, "tr") 
                            for cell in row.find_elements(By.TAG_NAME, "td")
                        )
                    )
                    logging.debug("Table content loaded successfully")
                except TimeoutException as e:
                    logging.warning(f"Timeout waiting for table content: {str(e)}")
                    raise
                
                # Ensure the entire page is loaded by scrolling down gradually
                logging.debug("Scrolling to ensure all content is loaded...")
                
                # Get initial table size
                initial_rows = len(driver.find_elements(By.TAG_NAME, "tr"))
                logging.debug(f"Initial row count: {initial_rows}")
                
                # Scroll down gradually to trigger any lazy loading
                last_height = driver.execute_script("return document.body.scrollHeight")
                while True:
                    # Scroll down to bottom
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    # Wait to load page
                    time.sleep(2)
                    
                    # Calculate new scroll height and compare with last scroll height
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        break
                    last_height = new_height
                
                # Check if more rows loaded after scrolling
                final_rows = len(driver.find_elements(By.TAG_NAME, "tr"))
                logging.debug(f"Final row count after scrolling: {final_rows}")
                
                # Extra delay to ensure everything is rendered
                time.sleep(3)
                
                # Get the page source and parse it
                html_content = driver.page_source
                logging.debug("Got page source, parsing certificate data...")
                cert_data = parse_certificate_data(html_content)
                
                if cert_data:
                    logging.info(f"Successfully retrieved certificate data for {domain}")
                    return True, cert_data
                else:
                    error_msg = "No certificate data found in the response"
                    logging.warning(f"Certificate data not found for {domain}: {error_msg}")
                    if attempt == max_retries - 1:
                        return False, error_msg
                    time.sleep(2)
                
            except TimeoutException as e:
                error_msg = f"Timeout error on attempt {attempt + 1}/{max_retries}: {str(e)}"
                logging.warning(f"crt.sh timeout for {domain}: {error_msg}")
                if attempt == max_retries - 1:
                    return False, {
                        'type': 'SSL Certificate',
                        'error': error_msg,
                        'status': 'Timeout',
                        'message': 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.'
                    }
                time.sleep(2)
                
            except WebDriverException as e:
                error_msg = f"Browser error: {str(e)}"
                logging.error(f"crt.sh browser error for {domain}: {error_msg}")
                
                # Check for specific error types
                if "chromedriver" in str(e).lower():
                    return False, {
                        'type': 'SSL Certificate',
                        'error': error_msg,
                        'status': 'Configuration Error',
                        'message': 'ChromeDriver error: Please ensure Chrome and ChromeDriver are properly installed'
                    }
                elif any(error in str(e).lower() for error in ['502', '503', '504', '500', 'gateway']):
                    return False, {
                        'type': 'SSL Certificate',
                        'error': error_msg,
                        'status': 'Service Unavailable',
                        'message': 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.'
                    }
                
                if attempt == max_retries - 1:
                    return False, {
                        'type': 'SSL Certificate',
                        'error': error_msg,
                        'status': 'Error',
                        'message': 'An error occurred while trying to retrieve certificate data. Please try again later.'
                    }
                time.sleep(2)
                
            finally:
                # Clean up resources
                if driver:
                    try:
                        driver.quit()
                        time.sleep(1)  # Give time for cleanup
                    except Exception as e:
                        logging.warning(f"Error closing browser: {str(e)}")
                    finally:
                        driver = None
                
                if service:
                    try:
                        service.stop()
                    except Exception as e:
                        logging.warning(f"Error stopping service: {str(e)}")
                    finally:
                        service = None
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logging.error(f"Unexpected error getting certificate data: {error_msg}")
        return False, {
            'type': 'SSL Certificate',
            'error': error_msg,
            'status': 'Error',
            'message': 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.'
        }
    
    return False, {
        'type': 'SSL Certificate',
        'error': f"Failed after {max_retries} attempts",
        'status': 'Error',
        'message': 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.'
    }

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