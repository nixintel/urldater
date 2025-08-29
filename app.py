print("Starting Flask app...")

from flask import Flask, Blueprint, render_template, request, jsonify, send_file
import validators
import logging
import pandas as pd
import io
import asyncio
from datetime import datetime, timezone
import zipfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from markdown2 import Markdown
import os
import atexit

from headers import get_media_dates
from rdap import get_domain_info
from certs import get_first_certificate, extract_main_domain, get_certificate_data
from chrome_driver_pool import driver_pool

app = Flask(__name__)

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
app.logger.setLevel(logging.DEBUG)

# Create a Blueprint for all routes
bp = Blueprint('urldater', __name__, 
               static_folder='static',
               template_folder='templates')

# Register the blueprint immediately after creation
app.register_blueprint(bp)

# Add this near your other imports
markdowner = Markdown()

@app.before_request
def log_all_requests():
    logger.debug("=" * 80)
    logger.debug(f"Request Method: {request.method}")
    logger.debug(f"Request URL: {request.url}")
    logger.debug(f"Request Path: {request.path}")
    logger.debug(f"Request Headers: {dict(request.headers)}")
    if request.is_json:
        try:
            logger.debug(f"Request JSON: {request.get_json()}")
        except Exception as e:
            logger.debug(f"Raw Request Data: {request.get_data(as_text=True)}")
            logger.debug(f"Failed to parse JSON: {str(e)}")
    logger.debug("=" * 80)

@bp.before_request
def log_request_info():
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())

@bp.route('/urldater/', methods=['GET'])
def index():
    logging.debug("Index route called!")
    try:
        return render_template('index.html', blueprint='urldater')
    except Exception as e:
        logging.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@bp.route('/urldater/analyze', methods=['POST'])
async def analyze():
    logger.debug("Analyze route called with:")
    logger.debug(f"Headers: {dict(request.headers)}")
    logger.debug(f"Raw Data: {request.get_data(as_text=True)}")
    logger.debug(f"Content Type: {request.content_type}")
    logger.debug(f"Mimetype: {request.mimetype}")
    
    try:
        # Validate content type
        if not request.is_json:
            logger.error(f"Invalid content type: {request.content_type}, expected application/json")
            return jsonify({'error': 'Invalid content type, expected application/json'}), 415
            
        try:
            # Get JSON data from request
            data = request.get_json()
            logger.debug(f"Parsed JSON data: {data}")
        except Exception as e:
            logger.error(f"Failed to parse JSON data: {str(e)}")
            logger.error(f"Raw request data: {request.get_data(as_text=True)}")
            return jsonify({'error': 'Invalid JSON format'}), 400
            
        if not data or 'url' not in data:
            logging.error("No URL provided")
            return jsonify({'error': 'No URL provided'}), 400
        
        url = data['url']
        search_type = data.get('searchType', 'all')  # Default to 'all' if not specified
        logging.info(f"[ANALYZE] Processing {search_type} search for URL: {url}")
        
        if not validators.url(url):
            logging.error(f"Invalid URL format: {url}")
            return jsonify({'error': 'Invalid URL format'}), 400
        
        domain = extract_main_domain(url)
        logging.debug(f"Extracted domain: {domain}")
        
        all_results = {
            'rdap': [],
            'headers': [],
            'certs': []
        }
        
        try:
            # Handle different search types
            if search_type == 'all':
                logging.debug("Getting all data types concurrently...")
                
                # Get RDAP data synchronously first
                try:
                    all_results['rdap'] = get_domain_info(url)
                except Exception as e:
                    logging.error(f"Error getting RDAP data: {str(e)}")
                    all_results['rdap'] = [{
                        'type': 'Error',
                        'error': f'Error retrieving RDAP data: {str(e)}'
                    }]

                # Then get headers and certs concurrently
                async def fetch_headers():
                    try:
                        results = await get_media_dates(url)
                        return results if results else [{
                            'type': 'Error',
                            'error': 'No header data could be found.'
                        }]
                    except Exception as e:
                        logging.error(f"Error getting headers data: {str(e)}")
                        return [{
                            'type': 'Error',
                            'error': f'Error retrieving header data: {str(e)}'
                        }]

                async def fetch_certs():
                    try:
                        success, cert_data = await get_first_certificate(domain)
                        if success:
                            return [cert_data]
                        else:
                            # Pass through the error from certs.py
                            return [cert_data]
                    except Exception as e:
                        logging.error(f"Error getting certificate data: {str(e)}")
                        return [{
                            'type': 'SSL Certificate',
                            'error': 'Unable to retrieve certificate data',
                            'status': 'Error',
                            'message': 'The certificate service is currently unavailable. Please try again later.'
                        }]

                # Try concurrent execution first
                tasks_started = datetime.now(timezone.utc)
                logging.info(f"[TASKS] Starting concurrent execution at {tasks_started}")
                
                try:
                    # Run headers and certs tasks concurrently
                    headers_task = asyncio.create_task(fetch_headers())
                    certs_task = asyncio.create_task(fetch_certs())
                    active_tasks = [headers_task, certs_task]
                    
                    try:
                        # Wait for both tasks with a timeout
                        all_results['headers'], all_results['certs'] = await asyncio.wait_for(
                            asyncio.gather(*active_tasks, return_exceptions=True),
                            timeout=60  # 60 second timeout for concurrent execution
                        )
                        logging.info("[TASKS] All concurrent tasks completed successfully")
                        
                    except asyncio.TimeoutError:
                        logging.warning("[TASKS] Concurrent execution timed out, falling back to sequential execution")
                        # Cancel and clean up any pending tasks
                        for task in active_tasks:
                            if not task.done():
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    logging.info(f"[TASKS] Successfully cancelled task {task}")
                                except Exception as e:
                                    logging.error(f"[TASKS] Error cancelling task {task}: {str(e)}")
                        
                        # Run sequentially
                        logging.info("[TASKS] Starting sequential execution after timeout")
                        all_results['headers'] = await fetch_headers()
                        all_results['certs'] = await fetch_certs()
                        
                except Exception as e:
                    logging.error(f"[TASKS] Error during concurrent execution: {str(e)}")
                    # Run sequentially as fallback
                    logging.info("[TASKS] Starting sequential execution after error")
                    all_results['headers'] = await fetch_headers()
                    all_results['certs'] = await fetch_certs()
                
                finally:
                    # Clean up and log completion
                    tasks_completed = datetime.now(timezone.utc)
                    duration = (tasks_completed - tasks_started).total_seconds()
                    logging.info(f"[TASKS] All tasks completed at {tasks_completed} (took {duration:.2f} seconds)")
                    
                    # Force cleanup of any resources
                    driver_pool.cleanup_all()
                    logging.info("[TASKS] WebDriver pool cleaned up")

                # Handle any exceptions from gather
                for key, result in all_results.items():
                    if isinstance(result, Exception):
                        logging.error(f"[TASKS] Error in {key} task: {str(result)}")
                        all_results[key] = [{
                            'type': 'Error',
                            'error': f'Task failed: {str(result)}'
                        }]
                    else:
                        logging.info(f"[TASKS] Successfully completed {key} task")
                
                return jsonify(all_results)
                
            elif search_type == 'rdap':
                logging.info("[ANALYZE] Starting RDAP lookup")
                results = get_domain_info(url)
                logging.info("[ANALYZE] RDAP lookup completed")
                return jsonify(results if results else [])
                
            elif search_type == 'headers':
                logging.debug("Getting media dates...")
                results = await get_media_dates(url)
                return jsonify(results if results else [])
                
            elif search_type == 'certs':
                logging.debug("Getting certificate data...")
                success, cert_data = await get_first_certificate(domain)
                if success:
                    return jsonify([cert_data])
                else:
                    logging.error(f"Certificate error: {cert_data}")
                    # Pass through the error from certs.py
                    return jsonify([cert_data])
            
            else:
                return jsonify({'error': 'Invalid search type'}), 400
                
        except Exception as e:
            logging.error(f"Error processing request: {str(e)}", exc_info=True)
            return jsonify({'error': f"Error processing request: {str(e)}"}), 500
    
    except Exception as e:
        logging.error(f"Error in analyze route: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@bp.route('/urldater/export/<export_type>', methods=['POST'])
def export(export_type):
    try:
        data = request.json
        domain = data.get('domain', 'unknown')
        # Replace dots with underscores in domain name
        domain = domain.replace('.', '_')
        # Format timestamp as DDMMYYYY
        timestamp = datetime.now().strftime('%d%m%Y')
        
        if export_type == 'all':
            # Create a ZIP file containing all CSVs
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w') as zf:
                # Export RDAP data
                if 'rdap_data' in data:
                    rdap_df = pd.DataFrame(data['rdap_data'])
                    rdap_csv = io.StringIO()
                    rdap_df.to_csv(rdap_csv, index=False)
                    rdap_filename = f"{domain}_{timestamp}_rdap.csv"
                    zf.writestr(rdap_filename, rdap_csv.getvalue())

                # Export Headers data
                if 'headers_data' in data:
                    headers_df = pd.DataFrame(data['headers_data'])
                    headers_csv = io.StringIO()
                    headers_df.to_csv(headers_csv, index=False)
                    headers_filename = f"{domain}_{timestamp}_headers.csv"
                    zf.writestr(headers_filename, headers_csv.getvalue())
                    
                # Export Certificate data
                if 'cert_data' in data:
                    cert_df = pd.DataFrame(data['cert_data'])
                    cert_csv = io.StringIO()
                    cert_df.to_csv(cert_csv, index=False)
                    cert_filename = f"{domain}_{timestamp}_certs.csv"
                    zf.writestr(cert_filename, cert_csv.getvalue())

            memory_file.seek(0)
            zip_filename = f"{domain}_{timestamp}_all.zip"
            response = send_file(
                memory_file,
                mimetype='application/zip',
                as_attachment=True,
                download_name=zip_filename
            )
            response.headers['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
            return response
        else:
            # Export single table
            df = pd.DataFrame(data['table_data'])
            output = io.StringIO()
            df.to_csv(output, index=False)
            
            filename = f"{domain}_{timestamp}_{export_type}.csv"
            
            response = send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=filename
            )
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
            
    except Exception as e:
        logging.error(f"Error in export route: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/urldater/export/all', methods=['POST'])
def export_all():
    try:
        data = request.json
        domain = data.get('domain', 'unknown')
        # Replace dots with underscores in domain name
        domain = domain.replace('.', '_')
        # Format timestamp as DDMMYYYY
        timestamp = datetime.now().strftime('%d%m%Y')
        
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            # Export RDAP data
            if 'rdap_data' in data:
                rdap_df = pd.DataFrame(data['rdap_data'])
                rdap_csv = io.StringIO()
                rdap_df.to_csv(rdap_csv, index=False)
                rdap_filename = f"{domain}_{timestamp}_rdap.csv"
                zf.writestr(rdap_filename, rdap_csv.getvalue())

            # Export Certificate data
            if 'cert_data' in data:
                cert_df = pd.DataFrame(data['cert_data'])
                cert_csv = io.StringIO()
                cert_df.to_csv(cert_csv, index=False)
                cert_filename = f"{domain}_{timestamp}_certs.csv"
                zf.writestr(cert_filename, cert_csv.getvalue())

            # Export Headers data
            if 'headers_data' in data:
                headers_df = pd.DataFrame(data['headers_data'])
                headers_csv = io.StringIO()
                headers_df.to_csv(headers_csv, index=False)
                headers_filename = f"{domain}_{timestamp}_headers.csv"
                zf.writestr(headers_filename, headers_csv.getvalue())

        memory_file.seek(0)
        zip_filename = f"{domain}_{timestamp}_all.zip"
        response = send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        response.headers['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
        return response
    except Exception as e:
        logging.error(f"Error in export route: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/urldater/search', methods=['POST'])
async def search():
    task_started = datetime.now(timezone.utc)
    logging.info(f"[TASK] Starting {request.method} /search at {task_started}")
    
    try:
        # Handle both form data and JSON data
        if request.is_json:
            data = request.get_json()
            domain = data.get('domain')
            search_type = data.get('searchType')
        else:
            domain = request.form.get('domain')
            search_type = request.form.get('searchType')
        
        logging.info(f"[TASK] Processing {search_type} search for domain: {domain}")
        
        if not domain:
            return jsonify({'error': 'No domain provided'}), 400
            
        try:
            if search_type == 'rdap':
                results = get_domain_info(domain)
                logging.info("[TASK] RDAP search completed")
            elif search_type == 'headers':
                results = await get_media_dates(domain)
                logging.info("[TASK] Headers search completed")
            elif search_type == 'certs':
                success, cert_data = await get_first_certificate(domain)
                if success:
                    results = [cert_data]
                    logging.info("[TASK] Certificate search completed successfully")
                else:
                    results = [{
                        'type': 'SSL Certificate',
                        'error': str(cert_data) if isinstance(cert_data, str) else cert_data.get('error', 'Unknown error'),
                        'status': cert_data.get('status', 'Error') if isinstance(cert_data, dict) else 'Error',
                        'message': cert_data.get('message', 'Unable to retrieve certificate data') if isinstance(cert_data, dict) else str(cert_data)
                    }]
                    logging.warning("[TASK] Certificate search completed with errors")
            else:
                return jsonify({'error': 'Invalid search type'}), 400
                
        except Exception as e:
            logging.error(f"[TASK] Error during {search_type} search: {str(e)}")
            raise
            
        finally:
            # Clean up resources
            driver_pool.cleanup_all()
            logging.info("[TASK] WebDriver pool cleaned up")
            
            # Log completion time and duration
            task_completed = datetime.now(timezone.utc)
            duration = (task_completed - task_started).total_seconds()
            logging.info(f"[TASK] Search completed at {task_completed} (took {duration:.2f} seconds)")
            
        logging.debug(f"[TASK] Search results: {results}")
        return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error processing search request: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/urldater/about')
def about():
    try:
        # Read the markdown file
        md_path = os.path.join(app.root_path, 'templates', 'about.md')
        with open(md_path, 'r') as f:
            content = f.read()
            
        # Convert markdown to HTML
        html_content = markdowner.convert(content)
        
        return render_template('about.html', content=html_content, blueprint='urldater')
    except Exception as e:
        app.logger.error(f"Error rendering about page: {str(e)}")
        return f"Error loading about page: {str(e)}", 500

@bp.route('/urldater/faq')
def faq():
    try:
        # Read the markdown file
        md_path = os.path.join(app.root_path, 'templates', 'faq.md')
        with open(md_path, 'r') as f:
            content = f.read()
            
        # Convert markdown to HTML
        html_content = markdowner.convert(content)
        
        return render_template('faq.html', content=html_content, blueprint='urldater')
    except Exception as e:
        app.logger.error(f"Error rendering FAQ page: {str(e)}")
        return f"Error loading FAQ page: {str(e)}", 500

def create_chrome_driver():
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
    
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.binary_location = '/usr/bin/google-chrome-stable'
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install())
    return webdriver.Chrome(service=service, options=chrome_options)

# Register cleanup function
def cleanup_webdriver_pool():
    logging.info("Cleaning up WebDriver pool")
    driver_pool.cleanup_all()

atexit.register(cleanup_webdriver_pool)

if __name__ == '__main__':
    app.run(debug=True, port=5000) 