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

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())  # Allow parent logger to handle output

def log_prefix(func_name):
    """Create a consistent log prefix"""
    return f"[HEADERS] {func_name}:"

def format_datetime(dt):
    """Format datetime to DD-MM-YYYY HH:mm:ss Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%d-%m-%Y %H:%M:%S %Z')

async def get_media_dates_fallback(url):
    """Fallback method that uses pure aiohttp without WebDriver"""
    logging.info(f"Using aiohttp fallback for URL: {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status >= 400:
                    return [{
                        'type': 'Error',
                        'error': f'HTTP error {response.status}',
                        'message': 'Failed to fetch the page'
                    }]
                
                # Parse response headers for Link tags
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    html = await response.text()
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find all image and icon links
                    media_urls = set()
                    
                    # Add favicon links
                    for link in soup.find_all('link', rel=lambda x: x and ('icon' in x.lower() or 'shortcut' in x.lower())):
                        if 'href' in link.attrs:
                            media_urls.add(link['href'])
                    
                    # Add image sources
                    for img in soup.find_all('img'):
                        if 'src' in img.attrs:
                            media_urls.add(img['src'])
                    
                    # Process each media URL
                    results = []
                    for media_url in media_urls:
                        if media_url.startswith('data:'):
                            continue
                            
                        # Make URL absolute if needed
                        if not media_url.startswith(('http://', 'https://')):
                            from urllib.parse import urljoin
                            media_url = urljoin(url, media_url)
                        
                        last_modified = await get_last_modified(session, media_url)
                        if last_modified:
                            results.append({
                                'type': 'image' if any(ext in media_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']) else 'favicon',
                                'url': media_url,
                                'last_modified': format_datetime(last_modified)
                            })
                    
                    return results if results else [{
                        'type': 'Info',
                        'message': 'No media files with last-modified dates found'
                    }]
                else:
                    return [{
                        'type': 'Error',
                        'error': 'Invalid content type',
                        'message': 'The URL does not point to a web page'
                    }]
    except Exception as e:
        logging.error(f"Error in fallback method: {str(e)}")
        return [{
            'type': 'Error',
            'error': str(e),
            'message': 'Failed to fetch the page'
        }]

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
    prefix = log_prefix("get_media_dates")
    logger.info(f"{prefix} Starting for URL: {url}")
    
    from headers_driver_pool import headers_driver_pool
    
    results = []
    driver = None
    max_retries = 2  # Fewer retries for headers
    session_id = None  # Track session ID for debugging
    
    # First try the aiohttp approach as it's faster and lighter
    try:
        results = await get_media_dates_fallback(url)
        if results and not (len(results) == 1 and results[0].get('type') in ['Error', 'Info']):
            logging.info("Successfully got results using aiohttp fallback")
            return results
    except Exception as e:
        logging.warning(f"Fallback method failed, will try WebDriver: {str(e)}")
    
    try:
        for attempt in range(max_retries):
            if driver is None:
                logging.info("Getting WebDriver from pool")
                try:
                    driver = headers_driver_pool.get_driver()
                    if driver:
                        session_id = driver.session_id
                        logging.info(f"Got WebDriver with session ID: {session_id}")
                except TimeoutError:
                    logging.error("Could not get WebDriver from pool")
                    return results if results else await get_media_dates_fallback(url)
                except Exception as e:
                    logging.error(f"Error getting WebDriver: {str(e)}")
                    return results if results else await get_media_dates_fallback(url)
            
            logging.info(f"Fetching URL: {url}")
            try:
                driver.set_page_load_timeout(15)  # Short timeout for headers
                driver.get(url)
            except WebDriverException as e:
                error_message = str(e).lower()
                if any(err in error_message for err in [
                    'err_name_not_resolved',
                    'err_connection_refused',
                    'err_connection_timed_out',
                    'err_ssl_protocol_error'
                ]):
                    # For connection errors, try aiohttp approach
                    if driver:
                        headers_driver_pool.return_driver(driver)
                        driver = None
                    return await get_media_dates_fallback(url)
                else:
                    # For other WebDriver errors, retry with a new driver
                    if driver:
                        headers_driver_pool.return_driver(driver)
                        driver = None
                    if attempt == max_retries - 1:
                        return await get_media_dates_fallback(url)
                    continue
        
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
                # Verify session is still valid before returning
                try:
                    if driver.session_id == session_id:
                        headers_driver_pool.return_driver(driver)
                        logging.info(f"WebDriver with session ID {session_id} returned to pool")
                    else:
                        logging.warning(f"Session ID mismatch: expected {session_id}, got {driver.session_id}")
                        headers_driver_pool._cleanup_driver(driver)
                except Exception:
                    logging.warning("Could not verify session ID, forcing cleanup")
                    headers_driver_pool._cleanup_driver(driver)
            except Exception as e:
                logging.warning(f"Error handling WebDriver cleanup: {str(e)}")
                try:
                    headers_driver_pool._cleanup_driver(driver)
                except Exception as e2:
                    logging.error(f"Final cleanup attempt failed: {str(e2)}")
    
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