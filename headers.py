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
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.binary_location = '/usr/bin/google-chrome-stable'
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    results = []
    driver = None
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)  # Increased timeout
        
        logging.debug(f"Fetching URL: {url}")
        driver.get(url)
        
        # Wait for page to be fully loaded
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # Additional wait for dynamic content
        try:
            WebDriverWait(driver, 20).until(
                lambda d: len(d.find_elements(By.TAG_NAME, "img")) > 0 or
                         len(d.find_elements(By.TAG_NAME, "link")) > 0
            )
        except TimeoutException:
            logging.warning("No images or links found after waiting")
        
        # Get favicon with retry
        favicon_url = None
        try:
            favicon_elements = get_elements_with_retry(driver, By.CSS_SELECTOR, "link[rel*='icon']")
            if favicon_elements:
                favicon_url = favicon_elements[0].get_attribute('href')
            elif driver.find_elements(By.CSS_SELECTOR, "/favicon.ico"):
                favicon_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}/favicon.ico"
        except Exception as e:
            logging.warning(f"Error getting favicon: {str(e)}")
        
        # Get images with retry
        VALID_IMAGE_EXTENSIONS = ('.gif', '.jpg', '.jpeg', '.png', '.svg', '.ico', '.webp', 
                                '.tif', '.tiff', '.bmp', '.heif', '.eps')
        
        image_urls = set()
        
        # Get images from img tags
        try:
            images = get_elements_with_retry(driver, By.TAG_NAME, 'img')
            for img in images:
                try:
                    src = img.get_attribute('src')
                    if src:
                        image_urls.add(src)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.warning(f"Error getting images: {str(e)}")
        
        # Get images from picture sources
        try:
            sources = get_elements_with_retry(driver, By.CSS_SELECTOR, 'picture source[srcset]')
            for source in sources:
                try:
                    srcset = source.get_attribute('srcset')
                    if srcset:
                        for srcset_part in srcset.split(','):
                            if srcset_part.strip():
                                url_part = srcset_part.strip().split(' ')[0]
                                image_urls.add(url_part)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.warning(f"Error getting picture sources: {str(e)}")
        
        # Get background images
        try:
            elements_with_bg = get_elements_with_retry(driver, By.CSS_SELECTOR, '[style*="background-image"]')
            for element in elements_with_bg:
                try:
                    style = element.get_attribute('style')
                    if 'url(' in style:
                        bg_url = style.split('url(')[1].split(')')[0].strip('"\'')
                        image_urls.add(bg_url)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.warning(f"Error getting background images: {str(e)}")
        
        # Filter valid image URLs
        image_urls = [
            url for url in image_urls
            if any(url.lower().endswith(ext) for ext in VALID_IMAGE_EXTENSIONS)
        ]
        
        # Get videos with retry
        video_urls = []
        try:
            videos = get_elements_with_retry(driver, By.TAG_NAME, 'video')
            for video in videos:
                try:
                    src = video.get_attribute('src')
                    if src:
                        video_urls.append(src)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.warning(f"Error getting videos: {str(e)}")
        
        try:
            video_sources = get_elements_with_retry(driver, By.CSS_SELECTOR, 'video source')
            for source in video_sources:
                try:
                    src = source.get_attribute('src')
                    if src:
                        video_urls.append(src)
                except StaleElementReferenceException:
                    continue
        except Exception as e:
            logging.warning(f"Error getting video sources: {str(e)}")
        
        # Create session for async requests
        async with aiohttp.ClientSession() as session:
            tasks = []
            
            if favicon_url:
                tasks.append(('favicon', favicon_url))
            for img_url in image_urls:
                tasks.append(('image', img_url))
            for video_url in video_urls:
                tasks.append(('video', video_url))
            
            for file_type, resource_url in tasks:
                last_modified = await get_last_modified(session, resource_url)
                if last_modified:
                    results.append({
                        'type': file_type,
                        'url': resource_url,
                        'last_modified': format_datetime(last_modified),
                        '_last_modified_dt': last_modified
                    })
    
    except Exception as e:
        logging.error(f"Error processing URL: {str(e)}")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logging.warning(f"Error closing browser: {str(e)}")
    
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