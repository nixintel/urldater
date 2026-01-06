from urllib.parse import urlparse
import subprocess
import json
import logging
import asyncio
from datetime import datetime, timezone

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())  # Allow parent logger to handle output

def log_prefix(func_name):
    """Create a consistent log prefix"""
    return f"[RDAP] {func_name}:"

def format_datetime(dt):
    """Format datetime to DD-MM-YYYY HH:mm:ss Z"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime('%d-%m-%Y %H:%M:%S %Z')

async def get_domain_info_async(domain_or_url):
    """Async version of get_domain_info using asyncio subprocess
    
    Args:
        domain_or_url: Either a plain domain (e.g., 'example.com') or a full URL
    """
    prefix = log_prefix("get_domain_info_async")
    logger.info(f"{prefix} Starting function")
    
    try:
        # Check if input is a URL or plain domain
        if domain_or_url.startswith(('http://', 'https://')):
            # It's a URL, parse it
            parsed_url = urlparse(domain_or_url)
            domain = parsed_url.netloc
        else:
            # It's already a plain domain
            domain = domain_or_url
        
        logger.info(f"{prefix} Looking up info for domain: {domain}")
        logger.info(f"{prefix} Executing command: rdap --json {domain}")
        
        # Run the rdap command asynchronously
        import time
        start_time = time.time()
        try:
            # Use asyncio.create_subprocess_exec for non-blocking execution
            process = await asyncio.create_subprocess_exec(
                'rdap', '--json', domain,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            elapsed_time = time.time() - start_time
            logger.info(f"{prefix} RDAP query completed in {elapsed_time:.2f}s")
            
            if process.returncode != 0:
                # Log detailed error information
                logger.error(f"{prefix} RDAP lookup failed with return code: {process.returncode}")
                if stdout:
                    logger.error(f"{prefix} stdout: {stdout.decode()[:500]}")
                if stderr:
                    logger.error(f"{prefix} stderr: {stderr.decode()[:500]}")
                
                # Return specific error to frontend
                error_details = stderr.decode()[:200] if stderr else 'Unknown error'
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': f'RDAP lookup failed: {process.returncode} - {error_details}',
                    'details': 'This TLD may not support RDAP queries, or the RDAP server is unavailable'
                }]
            
            # Convert bytes to string
            result_stdout = stdout.decode()
            
            # Try to parse as JSON first
            try:
                json.loads(result_stdout)  # Just testing if it's valid JSON
            except json.JSONDecodeError as json_err:
                logger.error(f"{prefix} RDAP output is not valid JSON")
                logger.error(f"{prefix} JSON parse error: {json_err}")
                logger.error(f"{prefix} Output preview: {result_stdout[:200]}")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': f'Invalid JSON response from RDAP server: {json_err.msg} at position {json_err.pos}'
                }]
        except Exception as e:
            logger.error(f"{prefix} Error running subprocess: {str(e)}")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': f'Failed to execute RDAP command: {str(e)}'
            }]
        
        # Log truncated output for debugging
        if result_stdout:
            truncated = result_stdout[:5] + "..." if len(result_stdout) > 200 else result_stdout
            logger.debug(f"{prefix} RDAP output preview: {truncated}")
        
        if not result_stdout.strip():
            logger.error(f"{prefix} OpenRDAP returned empty output")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': 'No RDAP data could be found for this domain. Check this TLD supports RDAP queries.'
            }]
        
        try:
            # Check for HTML or error page content
            if "<!DOCTYPE html>" in result_stdout or "<html" in result_stdout:
                logger.error(f"{prefix} Received HTML response instead of RDAP data")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid response format received from RDAP server'
                }]
            
            # Split the output on the known headers
            parts = result_stdout.split("RDAP from Registry:")
            if len(parts) > 1:
                json_text = parts[1].strip()  # Take the part after "RDAP from Registry:"
            else:
                json_text = parts[0].strip()  # If no header, take the whole text
                
            # Validate JSON structure before parsing
            if not json_text.startswith('{'):
                logger.error(f"{prefix} Invalid JSON format received")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid JSON format received from RDAP server'
                }]
                
            # Further split if there's a "RDAP from Registrar:" section
            if "RDAP from Registrar:" in json_text:
                json_text = json_text.split("RDAP from Registrar:")[0].strip()
            
            # Parse the JSON output
            rdap_data = json.loads(json_text)
            logger.debug(f"{prefix} Successfully parsed RDAP data with keys: {list(rdap_data.keys())}")
            
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
                logger.debug(f"{prefix} Processing {len(events)} events")
                
                for event in events:
                    event_action = event.get('eventAction', '')
                    event_date = event.get('eventDate', '')
                    
                    if event_action and event_date:
                        try:
                            event_date = event_date.split('.')[0].replace('Z', '+00:00')
                            parsed_date = datetime.fromisoformat(event_date)
                            formatted_date = format_datetime(parsed_date)
                            
                            if event_action == 'registration':
                                entry = {
                                    'type': 'Registered',
                                    'url': rdap_url,
                                    'registered': formatted_date,
                                    'last_modified': formatted_date,
                                    '_registered_dt': parsed_date
                                }
                                logger.info(f"{prefix} Found registration date: {formatted_date}")
                                domain_info.append(entry)
                            elif event_action == 'last changed':
                                entry = {
                                    'type': 'Updated',
                                    'url': rdap_url,
                                    'updated': formatted_date,
                                    'last_modified': formatted_date,
                                    '_updated_dt': parsed_date
                                }
                                logger.info(f"{prefix} Found last modified date: {formatted_date}")
                                domain_info.append(entry)
                        except ValueError as e:
                            logger.error(f"{prefix} Error parsing date {event_date}: {e}")
            else:
                logger.warning(f"{prefix} No events found in RDAP data. Available keys: {list(rdap_data.keys())}")
            
            return domain_info
            
        except json.JSONDecodeError as e:
            logger.error(f"{prefix} Failed to parse JSON: {e}")
            logger.error(f"{prefix} JSON error at line {e.lineno}, column {e.colno}")
            logger.error(f"{prefix} Error message: {e.msg}")
            # Log only the first part of the problematic output
            if result_stdout:
                preview = result_stdout[:200] + "..." if len(result_stdout) > 200 else result_stdout
                logger.error(f"{prefix} Invalid JSON content: {preview}")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': f'Failed to parse RDAP response: {e.msg}',
                'details': 'The RDAP server returned invalid or malformed JSON data'
            }]
            
    except Exception as e:
        logger.error(f"{prefix} Error in get_domain_info_async: {str(e.__class__.__name__)}: {str(e)}")
        return []


def get_domain_info(domain_or_url):
    """Synchronous wrapper for backward compatibility
    
    Args:
        domain_or_url: Either a plain domain (e.g., 'example.com') or a full URL
    """
    prefix = log_prefix("get_domain_info")
    logger.info(f"{prefix} Starting function")
    try:
        # Check if input is a URL or plain domain
        if domain_or_url.startswith(('http://', 'https://')):
            # It's a URL, parse it
            parsed_url = urlparse(domain_or_url)
            domain = parsed_url.netloc
        else:
            # It's already a plain domain
            domain = domain_or_url
        
        logger.info(f"{prefix} Looking up info for domain: {domain}")
        logger.info(f"{prefix} Executing command: rdap --json {domain}")
        
        # Run the rdap command with improved output capture
        import time
        start_time = time.time()
        try:
            result = subprocess.run(
                ['rdap', '--json', domain],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            elapsed_time = time.time() - start_time
            logger.info(f"{prefix} RDAP query completed in {elapsed_time:.2f}s")
            
            # Try to parse as JSON first
            try:
                json.loads(result.stdout)  # Just testing if it's valid JSON
            except json.JSONDecodeError as json_err:
                logger.error(f"{prefix} RDAP output is not valid JSON")
                logger.error(f"{prefix} JSON parse error: {json_err}")
                logger.error(f"{prefix} Output preview: {result.stdout[:200]}")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': f'Invalid JSON response from RDAP server: {json_err.msg} at position {json_err.pos}'
                }]
        except subprocess.CalledProcessError as e:
            # Log detailed error information
            logger.error(f"{prefix} RDAP lookup failed with return code: {e.returncode}")
            if e.stdout:
                logger.error(f"{prefix} stdout: {e.stdout[:500]}")
            if e.stderr:
                logger.error(f"{prefix} stderr: {e.stderr[:500]}")
            
            # Return specific error to frontend
            error_details = e.stderr[:200] if e.stderr else 'Unknown error'
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': f'RDAP lookup failed: {e.returncode} - {error_details}',
                'details': 'This TLD may not support RDAP queries, or the RDAP server is unavailable'
            }]
        
        # Log truncated output for debugging
        if result.stdout:
            truncated = result.stdout[:5] + "..." if len(result.stdout) > 200 else result.stdout
            logger.debug(f"{prefix} RDAP output preview: {truncated}")
        
        if not result.stdout.strip():
            logger.error(f"{prefix} OpenRDAP returned empty output")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': 'No RDAP data could be found for this domain. Check this TLD supports RDAP queries.'
            }]
        
        try:
            # Check for HTML or error page content
            if "<!DOCTYPE html>" in result.stdout or "<html" in result.stdout:
                logger.error(f"{prefix} Received HTML response instead of RDAP data")
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
                logger.error(f"{prefix} Invalid JSON format received")
                return [{
                    'type': 'Error',
                    'url': f"https://rdap.org/domain/{domain}",
                    'last_modified': 'N/A',
                    'error': 'Invalid JSON format received from RDAP server'
                }]
                
            # Further split if there's a "RDAP from Registrar:" section
            if "RDAP from Registrar:" in json_text:
                json_text = json_text.split("RDAP from Registrar:")[0].strip()
            
            # Parse the JSON output
            rdap_data = json.loads(json_text)
            logger.debug(f"{prefix} Successfully parsed RDAP data with keys: {list(rdap_data.keys())}")
            
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
                logger.debug(f"{prefix} Processing {len(events)} events")
                
                for event in events:
                    event_action = event.get('eventAction', '')
                    event_date = event.get('eventDate', '')
                    
                    if event_action and event_date:
                        try:
                            event_date = event_date.split('.')[0].replace('Z', '+00:00')
                            parsed_date = datetime.fromisoformat(event_date)
                            formatted_date = format_datetime(parsed_date)
                            
                            if event_action == 'registration':
                                entry = {
                                    'type': 'Registered',
                                    'url': rdap_url,
                                    'registered': formatted_date,
                                    'last_modified': formatted_date,
                                    '_registered_dt': parsed_date
                                }
                                logger.info(f"{prefix} Found registration date: {formatted_date}")
                                domain_info.append(entry)
                            elif event_action == 'last changed':
                                entry = {
                                    'type': 'Updated',
                                    'url': rdap_url,
                                    'updated': formatted_date,
                                    'last_modified': formatted_date,
                                    '_updated_dt': parsed_date
                                }
                                logger.info(f"{prefix} Found last modified date: {formatted_date}")
                                domain_info.append(entry)
                        except ValueError as e:
                            logger.error(f"{prefix} Error parsing date {event_date}: {e}")
            else:
                logger.warning(f"{prefix} No events found in RDAP data. Available keys: {list(rdap_data.keys())}")
            
            return domain_info
            
        except json.JSONDecodeError as e:
            logger.error(f"{prefix} Failed to parse JSON: {e}")
            logger.error(f"{prefix} JSON error at line {e.lineno}, column {e.colno}")
            logger.error(f"{prefix} Error message: {e.msg}")
            # Log only the first part of the problematic output
            if result.stdout:
                preview = result.stdout[:200] + "..." if len(result.stdout) > 200 else result.stdout
                logger.error(f"{prefix} Invalid JSON content: {preview}")
            return [{
                'type': 'Error',
                'url': f"https://rdap.org/domain/{domain}",
                'last_modified': 'N/A',
                'error': f'Failed to parse RDAP response: {e.msg}',
                'details': 'The RDAP server returned invalid or malformed JSON data'
            }]
            
    except Exception as e:
        logger.error(f"{prefix} Error in get_domain_info: {str(e.__class__.__name__)}: {str(e)}")
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