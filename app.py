print("Starting Flask app...")

from flask import Flask, render_template, request, jsonify, send_file
import validators
import logging
import pandas as pd
import io
from datetime import datetime, timezone
import zipfile

from headers import get_media_dates
from rdap import get_domain_info
from certs import get_first_certificate, extract_main_domain, get_certificate_data

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

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
                rdap_results = get_domain_info(url)
                if rdap_results:
                    all_results['rdap'] = rdap_results
                
                # Get Headers data
                headers_results = await get_media_dates(url)
                if headers_results:
                    all_results['headers'] = headers_results
                
                # Get Certificate data
                success, cert_data = get_first_certificate(domain)
                if success and cert_data:
                    all_results['certs'] = [cert_data]
                else:
                    logging.warning(f"Certificate data fetch failed: {cert_data}")
                
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

if __name__ == '__main__':
    app.run(debug=True, port=5000) 