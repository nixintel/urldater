print("Starting Flask app...")

from flask import Flask, render_template, request, jsonify, send_file
import validators
import logging
import pandas as pd
import io
from datetime import datetime, timezone
import zipfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from markdown2 import Markdown
import os

from headers import get_media_dates
from rdap import get_domain_info
from certs import get_first_certificate, extract_main_domain, get_certificate_data

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Add this near your other imports
markdowner = Markdown()

@app.before_request
def log_request_info():
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())

@app.route('/', methods=['GET'])
def index():
    logging.debug("Index route called!")
    try:
        return render_template('index.html')
    except Exception as e:
        logging.error(f"Error rendering template: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/analyze', methods=['POST'])
async def analyze():
    logging.debug("Analyze route called")
    try:
        # Get JSON data from request
        data = request.get_json()
        logging.debug(f"Received data: {data}")
        
        if not data or 'url' not in data:
            logging.error("No URL provided")
            return jsonify({'error': 'No URL provided'}), 400
        
        url = data['url']
        search_type = data.get('searchType', 'all')  # Default to 'all' if not specified
        logging.debug(f"Processing URL: {url} with search type: {search_type}")
        
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
                logging.debug("Getting all data types...")
                
                # Get RDAP data
                try:
                    rdap_results = get_domain_info(url)
                    all_results['rdap'] = rdap_results if rdap_results else [{
                        'type': 'Error',
                        'error': 'No RDAP data could be found for this domain.'
                    }]
                except Exception as e:
                    logging.error(f"Error getting RDAP data: {str(e)}")
                    all_results['rdap'] = [{
                        'type': 'Error',
                        'error': f'Error retrieving RDAP data: {str(e)}'
                    }]
                
                # Get Headers data
                try:
                    headers_results = await get_media_dates(url)
                    all_results['headers'] = headers_results if headers_results else [{
                        'type': 'Error',
                        'error': 'No header data could be found.'
                    }]
                except Exception as e:
                    logging.error(f"Error getting headers data: {str(e)}")
                    all_results['headers'] = [{
                        'type': 'Error',
                        'error': f'Error retrieving header data: {str(e)}'
                    }]
                
                # Get Certificate data
                try:
                    success, cert_data = get_first_certificate(domain)
                    if success:
                        all_results['certs'] = [cert_data]
                    else:
                        all_results['certs'] = [{
                            'type': 'SSL Certificate',
                            'error': str(cert_data) if isinstance(cert_data, str) else cert_data.get('error', 'Unknown error'),
                            'status': cert_data.get('status', 'Error') if isinstance(cert_data, dict) else 'Error',
                            'message': cert_data.get('message', 'Unable to retrieve certificate data') if isinstance(cert_data, dict) else str(cert_data)
                        }]
                except Exception as e:
                    logging.error(f"Error getting certificate data: {str(e)}")
                    all_results['certs'] = [{
                        'type': 'SSL Certificate',
                        'error': f'Error retrieving certificate data: {str(e)}',
                        'status': 'Error',
                        'message': 'Unable to retrieve certificate data'
                    }]
                
                return jsonify(all_results)
                
            elif search_type == 'rdap':
                logging.debug("Getting domain info...")
                results = get_domain_info(url)
                return jsonify(results if results else [])
                
            elif search_type == 'headers':
                logging.debug("Getting media dates...")
                results = await get_media_dates(url)
                return jsonify(results if results else [])
                
            elif search_type == 'certs':
                logging.debug("Getting certificate data...")
                success, cert_data = get_first_certificate(domain)
                if success:
                    return jsonify([cert_data])
                else:
                    logging.error(f"Certificate error: {cert_data}")
                    return jsonify({'error': str(cert_data)}), 400
            
            else:
                return jsonify({'error': 'Invalid search type'}), 400
                
        except Exception as e:
            logging.error(f"Error processing request: {str(e)}", exc_info=True)
            return jsonify({'error': f"Error processing request: {str(e)}"}), 500
    
    except Exception as e:
        logging.error(f"Error in analyze route: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/export/<export_type>', methods=['POST'])
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

@app.route('/export/all', methods=['POST'])
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

@app.route('/search', methods=['POST'])
def search():
    try:
        # Handle both form data and JSON data
        if request.is_json:
            data = request.get_json()
            domain = data.get('domain')
            search_type = data.get('searchType')
        else:
            domain = request.form.get('domain')
            search_type = request.form.get('searchType')
        
        app.logger.debug(f"Received search request - Type: {search_type}, Domain: {domain}")
        
        if not domain:
            return jsonify({'error': 'No domain provided'}), 400
            
        if search_type == 'rdap':
            results = get_domain_info(domain)
        elif search_type == 'headers':
            results = get_media_dates(domain)
        elif search_type == 'certs':
            results = get_certificate_data(domain)
        else:
            return jsonify({'error': 'Invalid search type'}), 400
            
        app.logger.debug(f"Search results: {results}")
        return jsonify(results)
            
    except Exception as e:
        app.logger.error(f"Error processing search request: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/about')
def about():
    try:
        # Read the markdown file
        md_path = os.path.join(app.root_path, 'templates', 'about.md')
        with open(md_path, 'r') as f:
            content = f.read()
            
        # Convert markdown to HTML
        html_content = markdowner.convert(content)
        
        return render_template('about.html', content=html_content)
    except Exception as e:
        app.logger.error(f"Error rendering about page: {str(e)}")
        return f"Error loading about page: {str(e)}", 500

@app.route('/faq')
def faq():
    try:
        # Read the markdown file
        md_path = os.path.join(app.root_path, 'templates', 'faq.md')
        with open(md_path, 'r') as f:
            content = f.read()
            
        # Convert markdown to HTML
        html_content = markdowner.convert(content)
        
        return render_template('faq.html', content=html_content)
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

if __name__ == '__main__':
    app.run(debug=True, port=5000) 