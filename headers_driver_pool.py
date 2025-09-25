from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import logging
import threading
from queue import Queue, Empty
import time
import psutil

class HeadersWebDriverPool:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(HeadersWebDriverPool, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.pool = Queue()
        self.max_drivers = 3  # Smaller pool for headers
        self.current_drivers = 0
        self.pool_lock = threading.Lock()
        self.driver_timeouts = {}
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
        
    def _create_driver(self):
        """Create a new Chrome WebDriver instance optimized for header retrieval"""
        import os
        import tempfile
        
        chrome_options = Options()
        
        # Essential options for Docker environment
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        # Performance and stability options
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Memory and process management
        chrome_options.add_argument('--disable-features=site-per-process')
        chrome_options.add_argument('--disable-web-security')
        chrome_options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        
        # Browser identification
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
        
        # Performance optimizations
        chrome_options.page_load_strategy = 'eager'
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        chrome_options.add_argument('--disable-breakpad')
        chrome_options.add_argument('--disable-client-side-phishing-detection')
        chrome_options.add_argument('--disable-default-apps')
        chrome_options.add_argument('--disable-hang-monitor')
        chrome_options.add_argument('--disable-popup-blocking')
        chrome_options.add_argument('--disable-prompt-on-repost')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--force-color-profile=srgb')
        chrome_options.add_argument('--metrics-recording-only')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--password-store=basic')
        chrome_options.add_argument('--use-mock-keychain')
        
        # Create a unique user data directory for this instance
        user_data_dir = os.path.join(tempfile.gettempdir(), f'chrome_user_data_{os.getpid()}_{id(self)}')
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)
        chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
        
        # Store the user data directory path for cleanup
        self.user_data_dir = user_data_dir
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(15)  # Shorter timeout for headers
        return driver
        
    def _get_memory_usage(self):
        """Get current memory usage of the process"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024  # Convert to MB

    def _check_memory_threshold(self):
        """Check if memory usage is above threshold"""
        memory_usage = self._get_memory_usage()
        memory_threshold = 512  # Lower threshold (512MB) for headers pool
        return memory_usage > memory_threshold

    def _check_driver_health(self, driver):
        """Check if a WebDriver instance is still healthy"""
        try:
            # Simple health check - try to access a property
            _ = driver.current_url
            return True
        except Exception:
            return False

    def get_driver(self, timeout=5):  # Shorter timeout for headers
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
                return self.get_driver(timeout)
                
            logging.debug("Retrieved existing WebDriver from headers pool")
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
                    
                    self.current_drivers += 1
                    logging.debug(f"Creating new WebDriver for headers (total: {self.current_drivers})")
                    driver = self._create_driver()
                    self.driver_timeouts[id(driver)] = time.time()
                    return driver
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
                # Check driver health before returning to pool
                if not self._check_driver_health(driver):
                    logging.warning("Unhealthy driver detected in headers pool, cleaning up")
                    self._cleanup_driver(driver)
                    return

                # Reset the driver state
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
                
                # Update last used time
                self.driver_timeouts[id(driver)] = time.time()
                
                self.pool.put(driver)
                logging.debug("Returned WebDriver to headers pool")
                
            except Exception as e:
                logging.error(f"Error returning driver to headers pool: {str(e)}")
                self._cleanup_driver(driver)

    def _cleanup_driver(self, driver):
        """Clean up a WebDriver instance with enhanced error recovery and session validation"""
        if not driver:
            return
            
        driver_id = id(driver)
        cleanup_success = False
        
        try:
<<<<<<< HEAD
            # First check if session is still valid
=======
            # First try to get the user data directory path before closing the driver
            try:
                user_data_dir = driver.options.arguments[-1].replace('--user-data-dir=', '')
            except:
                user_data_dir = getattr(self, 'user_data_dir', None)
            
            # Try to close all windows first
>>>>>>> dev
            try:
                driver.current_url
                session_valid = True
            except:
                session_valid = False
                logging.debug("Session already invalid, proceeding with force cleanup")
            
<<<<<<< HEAD
            if session_valid:
                # Try to close all windows first
                try:
                    if hasattr(driver, 'window_handles'):
                        for handle in driver.window_handles:
                            driver.switch_to.window(handle)
                            driver.close()
                except Exception as e:
                    logging.debug(f"Error closing windows: {str(e)}")
                
                # Try to clear browser data only if session is valid
                try:
                    driver.execute_script("window.localStorage.clear();")
                    driver.execute_script("window.sessionStorage.clear();")
                    driver.delete_all_cookies()
                except Exception as e:
                    logging.debug(f"Error clearing browser data: {str(e)}")
            
=======
>>>>>>> dev
            # Try to quit the driver
            try:
                driver.quit()
                cleanup_success = True
            except Exception as e:
                logging.warning(f"Error quitting driver: {str(e)}")
                
            # If normal quit failed or session was invalid, try force quit
            if not cleanup_success:
                try:
                    import psutil
                    process = psutil.Process(driver.service.process.pid)
<<<<<<< HEAD
                    children = process.children(recursive=True)
                    for child in children:
                        try:
                            child.terminate()
                            child.wait(timeout=3)  # Wait for process to terminate
                        except psutil.TimeoutExpired:
                            child.kill()  # Force kill if terminate doesn't work
                    process.terminate()
                    process.wait(timeout=3)  # Wait for main process to terminate
=======
                    for child in process.children(recursive=True):
                        try:
                            child.terminate()
                            child.wait(timeout=3)
                        except:
                            child.kill()
                    process.terminate()
                    process.wait(timeout=3)
>>>>>>> dev
                    cleanup_success = True
                except Exception as e:
                    logging.error(f"Error force quitting driver: {str(e)}")
            
            # Clean up user data directory
            if user_data_dir:
                try:
                    import shutil
                    if os.path.exists(user_data_dir):
                        shutil.rmtree(user_data_dir, ignore_errors=True)
                        logging.info(f"Cleaned up user data directory: {user_data_dir}")
                except Exception as e:
                    logging.error(f"Error cleaning up user data directory: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Error in driver cleanup: {str(e)}")
        finally:
            with self.pool_lock:
                self.current_drivers -= 1
                if driver_id in self.driver_timeouts:
                    del self.driver_timeouts[driver_id]
                    
            # Force garbage collection after cleanup
            try:
                import gc
                gc.collect()
            except Exception as e:
                logging.debug(f"Error in garbage collection: {str(e)}")
                
            if not cleanup_success:
                logging.warning("Driver cleanup may have left orphaned processes")
                    
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
            self.driver_timeouts.clear()

# Global instance
headers_driver_pool = HeadersWebDriverPool()
