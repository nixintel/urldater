from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import asyncio
import aiohttp
from datetime import datetime, timezone
import logging
from urllib.parse import urlparse

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
        driver.get(url)
        
        # Wait for page to be fully loaded
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
        
        # Additional wait for dynamic content
        try:
            WebDriverWait(driver, 10).until(
                lambda d: len(d.find_elements(By.TAG_NAME, "img")) > 0
            )
        except:
            logging.warning("No images found after waiting")
        
        # Get favicon
        favicon_url = None
        favicon_elements = driver.find_elements(By.CSS_SELECTOR, "link[rel*='icon']")
        if favicon_elements:
            favicon_url = favicon_elements[0].get_attribute('href')
        elif driver.find_elements(By.CSS_SELECTOR, "/favicon.ico"):
            favicon_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}/favicon.ico"
        
        # Get images
        VALID_IMAGE_EXTENSIONS = ('.gif', '.jpg', '.jpeg', '.png', '.svg', '.ico', '.webp', 
                                '.tif', '.tiff', '.bmp', '.heif', '.eps')
        
        images = []
        images.extend(driver.find_elements(By.TAG_NAME, 'img'))
        images.extend(driver.find_elements(By.CSS_SELECTOR, 'picture source[srcset]'))
        images.extend(driver.find_elements(By.CSS_SELECTOR, '[style*="background-image"]'))
        
        image_urls = set()
        
        for img in images:
            src = img.get_attribute('src')
            if src:
                image_urls.add(src)
            srcset = img.get_attribute('srcset')
            if srcset:
                for srcset_part in srcset.split(','):
                    if srcset_part.strip():
                        url_part = srcset_part.strip().split(' ')[0]
                        image_urls.add(url_part)
        
        image_urls = [
            url for url in image_urls
            if any(url.lower().endswith(ext) for ext in VALID_IMAGE_EXTENSIONS)
        ]
        
        # Get videos
        videos = driver.find_elements(By.TAG_NAME, 'video')
        video_sources = driver.find_elements(By.CSS_SELECTOR, 'video source')
        video_urls = []
        
        for video in videos:
            src = video.get_attribute('src')
            if src:
                video_urls.append(src)
        
        for source in video_sources:
            src = source.get_attribute('src')
            if src:
                video_urls.append(src)
        
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
            driver.quit()
    
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