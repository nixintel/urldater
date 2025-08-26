from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import logging
import threading
from queue import Queue, Empty
import time

class WebDriverPool:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WebDriverPool, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.pool = Queue()
        self.max_drivers = 2  # Maximum number of concurrent drivers
        self.current_drivers = 0
        self.pool_lock = threading.Lock()
        
    def _create_driver(self):
        """Create a new Chrome WebDriver instance with standard options"""
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.binary_location = '/usr/bin/google-chrome-stable'
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        chrome_options.page_load_strategy = 'eager'
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
        
    def get_driver(self, timeout=10):
        """Get a WebDriver instance from the pool or create a new one"""
        try:
            # Try to get an existing driver from the pool
            driver = self.pool.get(timeout=timeout)
            logging.debug("Retrieved existing WebDriver from pool")
            return driver
        except Empty:
            # If no driver is available, check if we can create a new one
            with self.pool_lock:
                if self.current_drivers < self.max_drivers:
                    self.current_drivers += 1
                    logging.debug(f"Creating new WebDriver (total: {self.current_drivers})")
                    return self._create_driver()
                else:
                    # If at max drivers, wait for one to become available
                    try:
                        logging.debug("Waiting for WebDriver to become available")
                        return self.pool.get(timeout=timeout)
                    except Empty:
                        raise TimeoutError("No WebDriver instance available within timeout period")
    
    def return_driver(self, driver):
        """Return a WebDriver instance to the pool"""
        if driver:
            try:
                # Reset the driver state
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
                self.pool.put(driver)
                logging.debug("Returned WebDriver to pool")
            except Exception as e:
                logging.error(f"Error returning driver to pool: {str(e)}")
                self._cleanup_driver(driver)
    
    def _cleanup_driver(self, driver):
        """Clean up a WebDriver instance"""
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logging.warning(f"Error cleaning up driver: {str(e)}")
            finally:
                with self.pool_lock:
                    self.current_drivers -= 1
                    
    def cleanup_all(self):
        """Clean up all WebDriver instances in the pool"""
        while True:
            try:
                driver = self.pool.get_nowait()
                self._cleanup_driver(driver)
            except Empty:
                break
        with self.pool_lock:
            self.current_drivers = 0

# Global instance
driver_pool = WebDriverPool()
