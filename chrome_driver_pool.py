from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import logging
import threading
from queue import Queue, Empty
import time
import psutil
import gc

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
        self.max_drivers = 5  # Increased maximum concurrent drivers
        self.current_drivers = 0
        self.pool_lock = threading.Lock()
        self.driver_timeouts = {}  # Track last usage time of drivers
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
        
    def _create_driver(self):
        """Create a new Chrome WebDriver instance with standard options"""
        chrome_options = Options()
        
        # Core settings
        chrome_options.binary_location = '/usr/bin/google-chrome-stable'
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # Process model settings
        chrome_options.add_argument('--process-per-site')  # More stable than single-process
        chrome_options.add_argument('--disable-renderer-backgrounding')
        
        # Memory and performance
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        
        # Stability improvements
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-crash-reporter')
        chrome_options.add_argument('--disable-in-process-stack-traces')
        
        # Logging and debugging
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent-debugger-extension-api')
        
        # Browser settings
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--hide-scrollbars')
        chrome_options.add_argument('--mute-audio')
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # Disable images for faster loading
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        # Page load strategy
        chrome_options.page_load_strategy = 'eager'
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(30)
        return driver
        
    def get_driver(self, timeout=10):
        """Get a WebDriver instance from the pool or create a new one"""
        try:
            # Check memory usage and cleanup if needed
            if self._check_memory_threshold():
                logging.warning("Memory usage above threshold, forcing cleanup")
                self.cleanup_all()
                
            # Try to get an existing driver from the pool
            driver = self.pool.get(timeout=timeout)
            
            # Verify driver health
            if not self._check_driver_health(driver):
                logging.warning("Retrieved unhealthy driver, cleaning up and retrying")
                self._cleanup_driver(driver)
                return self.get_driver(timeout)  # Recursive retry
                
            logging.debug("Retrieved existing WebDriver from pool")
            return driver
            
        except Empty:
            # If no driver is available, check if we can create a new one
            with self.pool_lock:
                if self.current_drivers < self.max_drivers:
                    # Check memory before creating new driver
                    if self._check_memory_threshold():
                        logging.warning("Memory usage too high for new driver")
                        # Try waiting for an existing driver
                        try:
                            return self.pool.get(timeout=timeout)
                        except Empty:
                            raise TimeoutError("Memory usage too high and no drivers available")
                    
                    # Try to create driver first, only increment counter on success
                    try:
                        logging.debug(f"Attempting to create new WebDriver")
                        driver = self._create_driver()
                        # Only increment counter after successful creation
                        self.current_drivers += 1
                        logging.debug(f"Successfully created WebDriver (total: {self.current_drivers})")
                        self.driver_timeouts[id(driver)] = time.time()
                        return driver
                    except Exception as e:
                        logging.error(f"Failed to create driver: {e}")
                        raise TimeoutError(f"Unable to create WebDriver: {str(e)}")
                else:
                    # If at max drivers, wait for one to become available
                    try:
                        logging.debug("Waiting for WebDriver to become available")
                        return self.pool.get(timeout=timeout)
                    except Empty:
                        raise TimeoutError("No WebDriver instance available within timeout period")
    
    def _check_driver_health(self, driver):
        """Check if a WebDriver instance is still healthy"""
        try:
            # Simple health check - try to access a property
            _ = driver.current_url
            return True
        except Exception:
            return False

    def _perform_cleanup(self):
        """Perform periodic cleanup of old drivers"""
        current_time = time.time()
        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        with self.pool_lock:
            # Clean up old drivers
            for driver_id, last_used in list(self.driver_timeouts.items()):
                if current_time - last_used > self.cleanup_interval:
                    self._cleanup_driver(driver_id)
            self.last_cleanup = current_time

    def return_driver(self, driver):
        """Return a WebDriver instance to the pool"""
        if driver:
            try:
                # Check driver health before returning to pool
                if not self._check_driver_health(driver):
                    logging.warning("Unhealthy driver detected, cleaning up")
                    self._cleanup_driver(driver)
                    return

                # Reset the driver state
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
                
                # Update last used time
                self.driver_timeouts[id(driver)] = time.time()
                
                self.pool.put(driver)
                logging.debug("Returned WebDriver to pool")
                
                # Perform periodic cleanup
                self._perform_cleanup()
            except Exception as e:
                logging.error(f"Error returning driver to pool: {str(e)}")
                self._cleanup_driver(driver)
    
    def _get_memory_usage(self):
        """Get current memory usage of the process"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # Convert to MB

    def _check_memory_threshold(self):
        """Check if memory usage is above threshold"""
        memory_usage = self._get_memory_usage()
        memory_threshold = 1024  # 1GB threshold
        return memory_usage > memory_threshold

    def _cleanup_driver(self, driver):
        """Clean up a WebDriver instance"""
        if driver:
            try:
                # Force garbage collection before cleanup
                gc.collect()
                
                # Quit the driver
                driver.quit()
                
                # Remove from timeouts tracking
                driver_id = id(driver)
                if driver_id in self.driver_timeouts:
                    del self.driver_timeouts[driver_id]
                    
            except Exception as e:
                logging.warning(f"Error cleaning up driver: {str(e)}")
            finally:
                with self.pool_lock:
                    self.current_drivers -= 1
                    
                # Force garbage collection after cleanup
                gc.collect()
                    
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
