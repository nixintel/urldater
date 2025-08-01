from urllib.parse import urlparse
import subprocess
import json
import logging
import asyncio
from datetime import datetime, timezone

def format_datetime(dt):
    """Format datetime to DD-MM-YYYY HH:mm:ss Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%d-%m-%Y %H:%M:%S %Z')

def get_domain_info(url):
    logging.info("Starting get_domain_info function")
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        
        logging.info(f"Looking up RDAP info for domain: {domain}")
        
        # Run the rdap command with improved output capture
        try:
            result = subprocess.run(
                ['rdap', '--json', domain],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            
            # Try to parse as JSON first
            try:
                json.loads(result.stdout)  # Just testing if it's valid JSON
            except json.JSONDecodeError:
                logging.error(f"RDAP output is not valid JSON: {result.stdout[:100]}")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid JSON response from RDAP server'
                }]
        except subprocess.CalledProcessError as e:
            logging.error(f"RDAP lookup failed: {e.output}")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': 'No RDAP data could be found for this domain. Check this TLD supports RDAP queries.'
            }]
        
        # Log the raw output for debugging
        logging.debug(f"Raw RDAP output: {result.stdout}")
        
        if not result.stdout.strip():
            logging.error("OpenRDAP returned empty output")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': 'No RDAP data could be found for this domain. Check this TLD supports RDAP queries.'
            }]
        
        try:
            # Check for HTML or error page content
            if "<!DOCTYPE html>" in result.stdout or "<html" in result.stdout:
                logging.error("Received HTML response instead of RDAP data")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid response format received from RDAP server'
                }]
            
            # Split the output on the known headers
            parts = result.stdout.split("RDAP from Registry:")
            if len(parts) > 1:
                json_text = parts[1].strip()  # Take the part after "RDAP from Registry:"
            else:
                json_text = parts[0].strip()  # If no header, take the whole text
                
            # Validate JSON structure before parsing
            if not json_text.startswith('{'):
                logging.error(f"Invalid JSON format received: {json_text[:100]}")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid JSON format received from RDAP server'
                }]
                
            # Further split if there's a "RDAP from Registrar:" section
            if "RDAP from Registrar:" in json_text:
                json_text = json_text.split("RDAP from Registrar:")[0].strip()
            
            logging.debug(f"Cleaned JSON text: {json_text}")
            
            # Parse the JSON output
            rdap_data = json.loads(json_text)
            logging.debug(f"Successfully parsed RDAP JSON data")
            
            # Get the RDAP URL from links
            rdap_url = None
            if 'links' in rdap_data:
                for link in rdap_data['links']:
                    if link.get('rel') == 'related' and link.get('type') == 'application/rdap+json':
                        rdap_url = link.get('value')
                        break
            
            if not rdap_url:
                rdap_url = f"https://rdap.org/domain/{domain}"  # fallback URL
            
            domain_info = []
            
            if 'events' in rdap_data:
                events = rdap_data['events']
                logging.debug(f"Found {len(events)} events")
                
                for event in events:
                    event_action = event.get('eventAction', '')
                    event_date = event.get('eventDate', '')
                    
                    logging.debug(f"Processing event - Action: {event_action}, Date: {event_date}")
                    
                    if event_action and event_date:
                        try:
                            event_date = event_date.split('.')[0].replace('Z', '+00:00')
                            parsed_date = datetime.fromisoformat(event_date)
                            formatted_date = format_datetime(parsed_date)
                            
                            if event_action == 'registration':
                                entry = {
                                    'type': 'Registered',
                                    'url': rdap_url,  # Using RDAP URL instead of domain tools
                                    'registered': formatted_date,
                                    'last_modified': formatted_date,
                                    '_registered_dt': parsed_date
                                }
                                logging.debug(f"Adding registration entry: {entry}")
                                domain_info.append(entry)
                            elif event_action == 'last changed':
                                entry = {
                                    'type': 'Updated',
                                    'url': rdap_url,  # Using RDAP URL instead of domain tools
                                    'updated': formatted_date,
                                    'last_modified': formatted_date,
                                    '_updated_dt': parsed_date
                                }
                                logging.debug(f"Adding last changed entry: {entry}")
                                domain_info.append(entry)
                        except ValueError as e:
                            logging.error(f"Error parsing date {event_date}: {e}")
            else:
                logging.warning("No events found in RDAP data")
                logging.debug(f"Available keys in RDAP data: {list(rdap_data.keys())}")
            
            return domain_info
            
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON: {e}")
            logging.error(f"Raw output causing error: {result.stdout}")
            return []
            
    except Exception as e:
        logging.error(f"Error in get_domain_info: {e}")
        logging.error(f"Full error: {str(e.__class__.__name__)}: {str(e)}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return []

if __name__ == "__main__":
    # Set up logging when running as main script
    logging.basicConfig(level=logging.DEBUG)
    
    # Run the script independently
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"Looking up RDAP info for: {url}")
        results = get_domain_info(url)
        if results:
            print("\nProcessed Results:")
            for result in results:
                # Remove the datetime object before printing
                if '_last_modified_dt' in result:
                    result = result.copy()
                    del result['_last_modified_dt']
                print(result)
        else:
            print("No results found") 