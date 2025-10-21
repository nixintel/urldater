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
import json

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
                logging.info(f"Attempting to connect to {url}")
                logging.info(f"Connection status: {response.status}")
                # Handle 4xx and 5xx errors differently
                if 400 <= response.status < 500:
                    # Client errors (4xx) - no retry needed
                    error_msg = {
                        400: 'Bad Request - The server cannot process the request',
                        401: 'Unauthorized - Authentication is required',
                        403: 'Forbidden - Access to this resource is forbidden',
                        404: 'Not Found - The requested resource does not exist',
                    }.get(response.status, f'Client Error {response.status}')
                    return [{
                        'type': 'Error',
                        'error': error_msg,
                        'status_code': response.status,
                        'no_retry': True
                    }]
                elif response.status >= 500:
                    # Server errors (5xx) - can be retried
                    return [{
                        'type': 'Error',
                        'error': f'Server Error {response.status}',
                        'status_code': response.status,
                        'no_retry': False
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
                        if last_modified and isinstance(last_modified, datetime):
                            results.append({
                                'type': 'image' if any(ext in media_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']) else 'favicon',
                                'url': media_url,
                                'last_modified': format_datetime(last_modified)
                            })
                        elif isinstance(last_modified, dict) and 'error' in last_modified:
                            # Handle error responses
                            results.append({
                                'type': 'Error',
                                'url': media_url,
                                'error': last_modified['error']
                            })
                    
                    return results if results else [{
                        'type': 'Info',
                        'message': 'No media files with last-modified dates found'
                    }]
                else:
                    return [{
                        'type': 'Error',
                        'error': 'Invalid content type',
                        'message': 'The URL does not point to a valid web page'
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
            if 400 <= response.status < 500:
                # Client errors (4xx) - no retry needed
                error_msg = {
                    400: 'Bad Request',
                    401: 'Unauthorized',
                    403: 'Forbidden',
                    404: 'Not Found',
                }.get(response.status, f'Client Error {response.status}')
                logging.error(f"{error_msg} for {url}")
                return {'error': error_msg, 'status_code': response.status, 'no_retry': True}
            elif response.status >= 500:
                # Server errors (5xx) - can be retried
                logging.error(f"Server error {response.status} for {url}")
                return {'error': f'Server Error {response.status}', 'status_code': response.status, 'no_retry': False}
                
            # Validate content type if present
            content_type = response.headers.get('Content-Type', '')
            if content_type and 'text/html' in content_type.lower():
                logging.warning(f"Unexpected HTML response for {url}")
                return None
                
            # Check various possible header names, don't always seem to be standard. 
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

def is_media_url(url):
    """Check if URL is a media file (image, favicon, etc.)"""
    if not url:
        return False
    
    # Skip data URLs
    if url.startswith('data:'):
        return False
    
    # Check for media file extensions
    media_extensions = ('.gif', '.jpg', '.jpeg', '.png', '.svg', '.ico', '.webp', 
                       '.tif', '.tiff', '.bmp', '.heif', '.eps')
    
    url_lower = url.lower()
    return any(url_lower.endswith(ext) for ext in media_extensions)

def get_media_type(url):
    """Determine media type from URL"""
    if not url:
        return 'unknown'
    
    url_lower = url.lower()
    if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heif']):
        return 'image'
    elif any(ext in url_lower for ext in ['.ico', '.svg']):
        return 'favicon'
    else:
        return 'media'

def get_media_dates_with_cdp(driver, url):
    """Get media dates using Chrome DevTools Protocol (CDP) - much faster approach"""
    prefix = log_prefix("get_media_dates_with_cdp")
    logger.info(f"{prefix} Starting CDP-based retrieval for URL: {url}")
    
    try:
        # Clear any existing logs
        driver.get_log('performance')
        
        # Navigate to the page with shorter timeout
        logger.info(f"{prefix} Navigating to: {url}")
        driver.set_page_load_timeout(10)  # Reduced from 15
        driver.get(url)
        
        # Wait for page to load (interactive or complete)
        try:
            WebDriverWait(driver, 3).until(
                lambda d: d.execute_script('return document.readyState') in ['interactive', 'complete']
            )
            logger.info(f"{prefix} Page load complete (interactive or complete)")
        except TimeoutException:
            logger.warning(f"{prefix} Page load timeout - continuing with partial content")
        
        # Reduced wait time
        time.sleep(1)  # Reduced from 2
        
        # Get performance logs with error handling
        try:
            logs = driver.get_log('performance')
            logger.info(f"{prefix} Retrieved {len(logs)} performance log entries")
        except Exception as e:
            logger.error(f"{prefix} Failed to get performance logs: {e}")
            return []
        
        # Process logs with memory management
        media_responses = []
        processed_urls = set()  # Avoid duplicates
        
        # Limit the number of logs processed to prevent memory issues
        max_logs = 1000
        logs_to_process = logs[:max_logs] if len(logs) > max_logs else logs
        
        for log in logs_to_process:
            try:
                message = json.loads(log['message'])
                method = message['message'].get('method')
                
                if method == 'Network.responseReceived':
                    params = message['message']['params']
                    response = params['response']
                    response_url = response['url']
                    
                    # Check if this is a media URL
                    if is_media_url(response_url) and response_url not in processed_urls:
                        processed_urls.add(response_url)
                        
                        # Get headers
                        headers = response.get('headers', {})
                        last_modified = (
                            headers.get('last-modified') or
                            headers.get('Last-Modified') or
                            headers.get('x-last-modified') or
                            headers.get('X-Last-Modified')
                        )
                        
                        if last_modified:
                            try:
                                # Parse the date
                                dt = datetime.strptime(last_modified, '%a, %d %b %Y %H:%M:%S GMT')
                                dt = dt.replace(tzinfo=timezone.utc)
                                
                                media_type = get_media_type(response_url)
                                
                                media_responses.append({
                                    'type': media_type,
                                    'url': response_url,
                                    'last_modified': format_datetime(dt),
                                    '_last_modified_dt': dt
                                })
                                
                                logger.info(f"{prefix} Found {media_type}: {response_url} - {format_datetime(dt)}")
                                
                            except ValueError as e:
                                logger.warning(f"{prefix} Invalid date format for {response_url}: {last_modified} - {e}")
                        else:
                            logger.debug(f"{prefix} No last-modified header for {response_url}")
                            
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"{prefix} Error parsing log entry: {e}")
                continue
        
        logger.info(f"{prefix} CDP method found {len(media_responses)} media items with last-modified headers")
        return media_responses
        
    except Exception as e:
        logger.error(f"{prefix} Error in CDP method: {str(e)}")
        return []

async def get_media_dates(url):
    prefix = log_prefix("get_media_dates")
    logger.info(f"{prefix} Starting for URL: {url}")
    
    from headers_driver_pool import headers_driver_pool
    
    results = []
    driver = None
    max_retries = 2  # Fewer retries for headers
    session_id = None  # Track session ID for debugging
    
    # Try CDP method first (fastest)
    try:
        logging.info(f"{prefix} Attempting CDP method first")
        driver = headers_driver_pool.get_driver()
        if driver:
            session_id = driver.session_id
            logging.info(f"{prefix} Got WebDriver with session ID: {session_id}")
            
            # Try CDP method
            cdp_results = get_media_dates_with_cdp(driver, url)
            # CDP succeeded - return results (even if empty)
            logging.info(f"{prefix} CDP method completed, found {len(cdp_results)} results")
            headers_driver_pool.return_driver(driver)
            return cdp_results if cdp_results else [{
                'type': 'Info',
                'error': 'No media files with last-modified headers found'
            }]
    except Exception as e:
        logging.warning(f"{prefix} CDP method failed: {str(e)}")
        if driver:
            headers_driver_pool.return_driver(driver)
            driver = None
        # Only proceed to fallback if CDP actually failed
    
    # If CDP method fails, try aiohttp fallback
    try:
        results = await get_media_dates_fallback(url)
        if results and not (len(results) == 1 and results[0].get('type') in ['Error', 'Info']):
            logging.info(f"{prefix} Successfully got results using aiohttp fallback")
            if driver:
                headers_driver_pool.return_driver(driver)
            return results
    except Exception as e:
        logging.warning(f"{prefix} Fallback method failed, will try WebDriver: {str(e)}")
    
    # If we still don't have a driver, try to get one for WebDriver fallback
    if driver is None:
        try:
            logging.info(f"{prefix} Getting WebDriver from pool for fallback")
            driver = headers_driver_pool.get_driver()
            if driver:
                session_id = driver.session_id
                logging.info(f"{prefix} Got WebDriver with session ID: {session_id}")
        except TimeoutError:
            logging.error(f"{prefix} Could not get WebDriver from pool")
            return results if results else await get_media_dates_fallback(url)
        except Exception as e:
            logging.error(f"{prefix} Error getting WebDriver: {str(e)}")
            return results if results else await get_media_dates_fallback(url)
    
    # Use WebDriver fallback method (original DOM-based approach)
    try:
        logging.info(f"{prefix} Using WebDriver fallback method")
        driver.set_page_load_timeout(15)  # Short timeout for headers
        driver.get(url)
        
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
                    try:
                        favicon_url = favicon.get_attribute('href')
                        if favicon_url and not favicon_url.startswith('data:'):
                            media_dict[favicon_url] = 'favicon'
                            logging.info(f"{prefix} Found favicon: {favicon_url}")
                            favicon_found = True
                        else:
                            logging.debug(f"{prefix} Skipping data URL or empty favicon: {favicon_url}")
                    except StaleElementReferenceException:
                        logging.warning(f"{prefix} Stale element reference when getting favicon href, skipping this favicon")
                        continue
                    except Exception as e:
                        logging.warning(f"{prefix} Error getting favicon href: {str(e)}")
                        continue
            except Exception as e:
                logging.warning(f"{prefix} Error getting favicon with selector {selector}: {str(e)}")
        
        if not favicon_found:
            default_favicon = f"{urlparse(url).scheme}://{urlparse(url).netloc}/favicon.ico"
            media_dict[default_favicon] = 'favicon'
            logging.info(f"Added default favicon location: {default_favicon}")
        
        # Get images
        logging.info("Searching for images...")
        try:
            images = driver.find_elements(By.TAG_NAME, 'img')
            for img in images:
                try:
                    src = img.get_attribute('src')
                    if src:
                        media_dict[src] = 'image'
                        logging.info(f"Found image: {src}")
                except StaleElementReferenceException:
                    logging.warning("Stale element reference when getting image src, skipping this image")
                    continue
                except Exception as e:
                    logging.warning(f"Error getting image src: {str(e)}")
                    continue
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
                    'error': 'No images or icons found on the page.'
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
                    if isinstance(last_modified, dict) and 'error' in last_modified:
                        # Handle error response
                        if last_modified.get('no_retry', False):
                            # For 4xx errors, add to results and continue
                            results.append({
                                'type': 'Error',
                                'url': media_url,
                                'error': last_modified['error']
                            })
                            logging.info(f"Added error result for {media_url}: {last_modified['error']}")
                        else:
                            # For 5xx errors, allow retry logic to handle it
                            logging.warning(f"Server error for {media_url}: {last_modified['error']}")
                    elif last_modified and isinstance(last_modified, datetime):
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
                    'error': 'Image URLs were found but no Last Modified headers were identified.'
                }]
    
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
            # For other WebDriver errors, return error
            if driver:
                headers_driver_pool.return_driver(driver)
            return await get_media_dates_fallback(url)
    
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
    # Add code to run this module independently, careful of the venv!
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        results = asyncio.run(get_media_dates(url))
        for result in sorted(results, key=lambda x: x['_last_modified_dt'], reverse=True):
            del result['_last_modified_dt']
            print(result) 