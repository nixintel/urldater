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
        data = request.get_json()
        logging.debug(f"Received data: {data}")
        
        if not data or 'url' not in data:
            logging.error("No URL provided")
            return jsonify({'error': 'No URL provided'}), 400
        
        url = data['url']
        if not validators.url(url):
            logging.error(f"Invalid URL format: {url}")
            return jsonify({'error': 'Invalid URL format'}), 400
        
        domain = extract_main_domain(url)
        results = []
        
        # Handle different search types
        if data.get('domain_age_only'):
            results = get_domain_info(url)
        elif data.get('headers_only'):
            results = await get_media_dates(url)
        elif data.get('certs_only'):
            cert_data = get_certificate_data(domain)
            if cert_data:
                results = [cert_data]
        
        logging.debug(f"Final results: {results}")
        return jsonify(results)
    
    except Exception as e:
        logging.error(f"Error in analyze route: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/export/<export_type>', methods=['POST'])
def export(export_type):
    try:
        data = request.json
        domain = data.get('domain', 'unknown')
        timestamp = datetime.now().strftime('%d-%m-%Y-%H%M%S')
        
        if export_type == 'all':
            # Create a ZIP file containing both CSVs
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w') as zf:
                # Export RDAP data
                if 'rdap_data' in data:
                    rdap_df = pd.DataFrame(data['rdap_data'])
                    rdap_csv = io.StringIO()
                    rdap_df.to_csv(rdap_csv, index=False)
                    rdap_filename = f"{domain}_rdap_{timestamp}.csv"
                    zf.writestr(rdap_filename, rdap_csv.getvalue())

                # Export Headers data
                if 'headers_data' in data:
                    headers_df = pd.DataFrame(data['headers_data'])
                    headers_csv = io.StringIO()
                    headers_df.to_csv(headers_csv, index=False)
                    headers_filename = f"{domain}_headers_{timestamp}.csv"
                    zf.writestr(headers_filename, headers_csv.getvalue())

            memory_file.seek(0)
            return send_file(
                memory_file,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{domain}_all_{timestamp}.zip"
            )
        else:
            # Export single table
            df = pd.DataFrame(data['table_data'])
            output = io.StringIO()
            df.to_csv(output, index=False)
            
            filename = f"{domain}_{export_type}_{timestamp}.csv"
            
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name=filename
            )
    except Exception as e:
        logging.error(f"Error in export route: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/export/all', methods=['POST'])
def export_all():
    try:
        data = request.json
        domain = data.get('domain', 'unknown')
        timestamp = datetime.now().strftime('%d-%m-%Y-%H%M%S')
        
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            # Export RDAP data
            if 'rdap_data' in data:
                rdap_df = pd.DataFrame(data['rdap_data'])
                rdap_csv = io.StringIO()
                rdap_df.to_csv(rdap_csv, index=False)
                rdap_filename = f"{domain}_rdap_{timestamp}.csv"
                zf.writestr(rdap_filename, rdap_csv.getvalue())

            # Export Certificate data
            if 'cert_data' in data:
                cert_df = pd.DataFrame(data['cert_data'])
                cert_csv = io.StringIO()
                cert_df.to_csv(cert_csv, index=False)
                cert_filename = f"{domain}_certs_{timestamp}.csv"
                zf.writestr(cert_filename, cert_csv.getvalue())

            # Export Headers data
            if 'headers_data' in data:
                headers_df = pd.DataFrame(data['headers_data'])
                headers_csv = io.StringIO()
                headers_df.to_csv(headers_csv, index=False)
                headers_filename = f"{domain}_headers_{timestamp}.csv"
                zf.writestr(headers_filename, headers_csv.getvalue())

        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{domain}_all_{timestamp}.zip"
        )
    except Exception as e:
        logging.error(f"Error in export route: {str(e)}", exc_info=True)
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