from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import asyncio
import aiohttp
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse
import time

def format_datetime(dt):
    """Format datetime to DD-MM-YYYY HH:mm:ss Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%d-%m-%Y %H:%M:%S %Z')

async def get_last_modified(session, url):
    try:
        async with session.head(url, allow_redirects=True) as response:
            # Check response status
            if response.status >= 400:
                logging.error(f"HTTP error {response.status} for {url}")
                return None
                
            # Validate content type if present
            content_type = response.headers.get('Content-Type', '')
            if content_type and 'text/html' in content_type.lower():
                logging.warning(f"Unexpected HTML response for {url}")
                return None
                
            # Check various possible header names
            last_modified = (
                response.headers.get('last-modified') or
                response.headers.get('Last-Modified') or
                response.headers.get('x-last-modified') or
                response.headers.get('X-Last-Modified')
            )
            
            if last_modified:
                try:
                    dt = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S GMT')
                    dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    logging.warning(f"Invalid date format in header for {url}: {last_modified}")
                    return None
            else:
                # If HEAD request doesn't work, try GET
                async with session.get(url, allow_redirects=True) as get_response:
                    last_modified = (
                        get_response.headers.get('last-modified') or
                        get_response.headers.get('Last-Modified') or
                        get_response.headers.get('x-last-modified') or
                        get_response.headers.get('X-Last-Modified')
                    )
                    if last_modified:
                        try:
                            dt = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S GMT')
                            dt = dt.replace(tzinfo=timezone.utc)
                            return dt
                        except ValueError:
                            logging.warning(f"Invalid date format in header for {url}: {last_modified}")
                            return None
                    
                    logging.info(f"No last-modified header found for {url}. Headers: {dict(get_response.headers)}")
                    return None
    except Exception as e:
        logging.error(f"Error fetching last-modified for {url}: {str(e)}")
        return None

def get_element_with_retry(driver, by, value, max_retries=3, timeout=10):
    """Helper function to get elements with retry logic for stale elements"""
    for attempt in range(max_retries):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except StaleElementReferenceException:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)
    return None

def get_elements_with_retry(driver, by, value, max_retries=3, timeout=10):
    """Helper function to get elements with retry logic for stale elements"""
    for attempt in range(max_retries):
        try:
            elements = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((by, value))
            )
            return elements
        except StaleElementReferenceException:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)
    return []

async def get_media_dates(url):
    logging.info(f"Starting get_media_dates for URL: {url}")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.binary_location = '/usr/bin/google-chrome-stable'
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    results = []
    driver = None
    
    try:
        logging.info("Initializing Chrome WebDriver")
        chrome_options.page_load_strategy = 'eager'
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        
        logging.info(f"Fetching URL: {url}")
        try:
            driver.get(url)
        except WebDriverException as e:
            error_message = str(e).lower()
            if 'err_name_not_resolved' in error_message:
                return [{
                    'type': 'Error',
                    'error': 'Unable to connect to the provided URL. The website may be offline or inaccessible.'
                }]
            elif 'err_connection_refused' in error_message:
                return [{
                    'type': 'Error',
                    'error': 'Connection refused. The website is not accepting connections.'
                }]
            elif 'err_connection_timed_out' in error_message:
                return [{
                    'type': 'Error',
                    'error': 'Connection timed out. The website took too long to respond.'
                }]
            elif 'err_ssl_protocol_error' in error_message:
                return [{
                    'type': 'Error',
                    'error': 'SSL/TLS error. Could not establish a secure connection to the website.'
                }]
            else:
                # For other WebDriver errors, return a generic message
                return [{
                    'type': 'Error',
                    'error': 'Unable to connect to the website. Please check if the URL is correct and the website is accessible.'
                }]
        
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            logging.info("Page load complete")
        except TimeoutException:
            logging.warning("Page load timeout - continuing with partial content")
        
        # Dictionary to store media items with their types
        media_dict = {}  # Use dictionary instead of set to maintain order
        
        # Get favicon URLs
        favicon_selectors = [
            "link[rel='icon']",
            "link[rel='shortcut icon']",
            "link[rel='apple-touch-icon']",
            "link[rel*='icon']"
        ]
        
        logging.info("Searching for favicons...")
        favicon_found = False
        for selector in favicon_selectors:
            try:
                favicon_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for favicon in favicon_elements:
                    favicon_url = favicon.get_attribute('href')
                    if favicon_url and not favicon_url.startswith('data:'):
                        media_dict[favicon_url] = 'favicon'
                        favicon_found = True
                        logging.info(f"Found favicon: {favicon_url}")
                    else:
                        logging.debug(f"Skipping data URL or empty favicon: {favicon_url}")
            except Exception as e:
                logging.warning(f"Error getting favicon with selector {selector}: {str(e)}")
        
        if not favicon_found:
            default_favicon = f"{urlparse(url).scheme}://{urlparse(url).netloc}/favicon.ico"
            media_dict[default_favicon] = 'favicon'
            logging.info(f"Added default favicon location: {default_favicon}")
        
        # Get images
        logging.info("Searching for images...")
        try:
            images = driver.find_elements(By.TAG_NAME, 'img')
            for img in images:
                src = img.get_attribute('src')
                if src:
                    media_dict[src] = 'image'
                    logging.info(f"Found image: {src}")
        except Exception as e:
            logging.warning(f"Error getting images: {str(e)}")
        
        # Filter valid URLs
        VALID_EXTENSIONS = ('.gif', '.jpg', '.jpeg', '.png', '.svg', '.ico', '.webp', 
                          '.tif', '.tiff', '.bmp', '.heif', '.eps')
        
        # Create filtered dictionary
        filtered_media = {
            url: type_ for url, type_ in media_dict.items()
            if url and any(url.lower().endswith(ext) for ext in VALID_EXTENSIONS)
        }
        
        logging.info(f"Found {len(filtered_media)} valid media items")
        
        # Process media URLs with aiohttp
        if not filtered_media:
            logging.info("No valid media items found to check")
            return [{
                'type': 'Info',
                'error': 'No images or icons found on the page to check for last-modified dates.'
            }]

        async with aiohttp.ClientSession() as session:
            tasks = {}  # Dictionary to map tasks to their URLs
            
            for media_url in filtered_media:
                # Skip data URLs
                if media_url.startswith('data:'):
                    logging.debug(f"Skipping data URL: {media_url}")
                    continue
                    
                task = asyncio.create_task(get_last_modified(session, media_url))
                tasks[task] = media_url
                logging.info(f"Created task for URL: {media_url}")
            
            if not tasks:
                logging.info("No valid URLs to check after filtering")
                return [{
                    'type': 'Info',
                    'error': 'No valid images or icons found on the page to check for last-modified dates.'
                }]
            
            # Wait for all tasks with timeout
            done, pending = await asyncio.wait(tasks.keys(), timeout=30)
            
            if pending:
                logging.warning(f"{len(pending)} tasks did not complete within timeout")
            
            logging.info(f"Processing {len(done)} completed tasks")
            for task in done:
                media_url = tasks[task]
                try:
                    last_modified = task.result()
                    if last_modified:
                        result = {
                            'type': filtered_media[media_url],
                            'url': media_url,
                            'last_modified': format_datetime(last_modified),
                            '_last_modified_dt': last_modified
                        }
                        results.append(result)
                        logging.info(f"Added result: {result}")
                except Exception as e:
                    logging.error(f"Error processing {media_url}: {str(e)}")
            
            if not results:
                return [{
                    'type': 'Info',
                    'status': 'No Results',
                    'error': 'A connection was made but no items with valid Last-Modified headers were found.'
                }]
    
    except WebDriverException as e:
        logging.error(f"WebDriver error in get_media_dates: {str(e)}")
        error_message = str(e).lower()
        if 'err_name_not_resolved' in error_message:
            return [{
                'type': 'Error',
                'error': 'Unable to connect to the provided URL. The website may be offline or inaccessible.'
            }]
        elif 'err_connection_refused' in error_message:
            return [{
                'type': 'Error',
                'error': 'Connection refused. The website is not accepting connections.'
            }]
        elif 'err_connection_timed_out' in error_message:
            return [{
                'type': 'Error',
                'error': 'Connection timed out. The website took too long to respond.'
            }]
        elif 'err_ssl_protocol_error' in error_message:
            return [{
                'type': 'Error',
                'error': 'SSL/TLS error. Could not establish a secure connection to the website.'
            }]
        else:
            return [{
                'type': 'Error',
                'error': 'Unable to connect to the website. Please check if the URL is correct and the website is accessible.'
            }]
    except Exception as e:
        logging.error(f"Error in get_media_dates: {str(e)}")
        return [{
            'type': 'Error',
            'error': 'An error occurred while analyzing the website. Please try again later.'
        }]
    finally:
        if driver:
            try:
                driver.quit()
                logging.info("Chrome WebDriver closed")
            except Exception as e:
                logging.warning(f"Error closing browser: {str(e)}")
    
    logging.info(f"Returning {len(results)} results")
    return results

if __name__ == "__main__":
    # Add code to run this module independently
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        results = asyncio.run(get_media_dates(url))
        for result in sorted(results, key=lambda x: x['_last_modified_dt'], reverse=True):
            del result['_last_modified_dt']
            print(result) 