from urllib.parse import urlparse
import argparse
import logging
import asyncio
import aiohttp
import json
from datetime import datetime, timezone

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())  # Allow parent logger to handle output

def log_prefix(func_name):
    """Create a consistent log prefix for easier debugging"""
    return f"[CERTS] {func_name}:"

def extract_main_domain(url):
    """Extract the main domain from a URL, ignoring subdomains."""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    domain_parts = parsed.netloc.split('.')
    
    # Handle cases like co.uk, com.au, etc. Think this is all of them? TODO: check this.
    if len(domain_parts) > 2 and domain_parts[-2] in ['co', 'com', 'org', 'net']:
        return '.'.join(domain_parts[-3:])
    return '.'.join(domain_parts[-2:])

async def get_certificate_json(domain):
    """Get certificate data from crt.sh JSON API."""
    prefix = log_prefix("get_certificate_json")
    logger.debug(f"{prefix} Fetching JSON data for domain: {domain}")
    
    url = f"https://crt.sh/?q={domain}&output=json"
    logger.debug(f"{prefix} Connecting to {url}...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                
                if response.status != 200:
                    logger.error(f"{prefix} Error response from crt.sh: {response.status}")
                    return {
                        'type': 'SSL Certificate',
                        'error': f'HTTP {response.status}',
                        'status': 'Error',
                        'message': 'Failed to retrieve certificate data from crt.sh'
                    }
                
                try:
                    certs = await response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"{prefix} Failed to parse JSON response: {e}")
                    return {
                        'type': 'SSL Certificate',
                        'error': 'Invalid JSON response',
                        'status': 'Error',
                        'message': 'Invalid response format from crt.sh'
                    }
                
                if not certs:
                    logger.warning(f"{prefix} No certificates found")
                    return {
                        'type': 'SSL Certificate',
                        'error': 'No Certificates Found',
                        'status': 'Not Found',
                        'message': 'No SSL certificates found for this domain'
                    }
                
                # Sort by entry_timestamp to get the oldest certificate
                certs.sort(key=lambda x: x['entry_timestamp'])
                oldest_cert = certs[0]
                
                # Convert dates to the standard format: DD-MM-YYYY HH:MM:SS UTC
                entry_date = datetime.fromisoformat(oldest_cert['entry_timestamp'].replace('Z', '+00:00'))
                valid_from = datetime.fromisoformat(oldest_cert['not_before'].replace('Z', '+00:00'))
                
                cert_data = {
                    'type': 'SSL Certificate',
                    'Common Name': oldest_cert['common_name'],
                    'First Seen': entry_date.strftime('%d-%m-%Y %H:%M:%S UTC'),
                    'Valid From': valid_from.strftime('%d-%m-%Y %H:%M:%S UTC'),
                    'Source': f"https://crt.sh/?id={oldest_cert['id']}"
                }
                
                logger.info(f"{prefix} Successfully retrieved certificate data: {cert_data}")
                return cert_data
                
    except aiohttp.ClientError as e:
        logger.error(f"{prefix} Connection error: {e}")
        return {
            'type': 'SSL Certificate',
            'error': 'Connection Error',
            'status': 'Error',
            'message': 'Failed to connect to crt.sh'
        }
    except Exception as e:
        logger.error(f"{prefix} Unexpected error: {e}")
        return {
            'type': 'SSL Certificate',
            'error': str(e),
            'status': 'Error',
            'message': 'An unexpected error occurred while retrieving certificate data'
        }

async def check_crtsh_status():
    """
    Check if crt.sh is responding and not showing a server error.
    Returns tuple of (is_up, error_message)
    """
    prefix = log_prefix("check_crtsh_status")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://crt.sh") as response:
                if response.status != 200:
                    return False, {
                        'type': 'SSL Certificate',
                        'error': f'HTTP {response.status}',
                        'status': 'Service Unavailable',
                        'message': 'The certificate service is currently unavailable. Please try again later.'
                    }
                return True, None
    except Exception as e:
        logger.error(f"{prefix} Error checking crt.sh status: {e}")
        return False, {
            'type': 'SSL Certificate',
            'error': 'Service unavailable',
            'status': 'Service Unavailable',
            'message': 'Unable to connect to the certificate service. Please try again later.'
        }

async def get_first_certificate(domain):
    """
    Connect to crt.sh and attempt to retrieve certificate information.
    Returns tuple of (success, result), where result is either the data or error message.
    Crt.sh is frequently down and gives 50x errors so we retry a few times.
    """
    prefix = log_prefix("get_first_certificate")
    logger.debug(f"{prefix} Starting search for domain: {domain}")
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                # Add exponential backoff between attempts
                backoff = 2 ** attempt
                logger.debug(f"{prefix} Retry attempt {attempt + 1}/{max_retries}, waiting {backoff} seconds")
                await asyncio.sleep(backoff)
            
            cert_data = await get_certificate_json(domain)
            
            # Check if we got an error response
            if cert_data.get('error'):
                if attempt == max_retries - 1:
                    logger.error(f"{prefix} Failed after {max_retries} attempts: {cert_data['error']}")
                    return False, cert_data
                continue
            
            logger.info(f"{prefix} Successfully retrieved certificate data for {domain}")
            return True, cert_data
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"{prefix} {error_msg}")
            
            if attempt == max_retries - 1:
                return False, {
                    'type': 'SSL Certificate',
                    'error': error_msg,
                    'status': 'Error',
                    'message': 'An error occurred while retrieving certificate data. Please try again later.'
                }
    
    # This should never be reached due to the return in the loop
    return False, {
        'type': 'SSL Certificate',
        'error': f"Failed after {max_retries} attempts",
        'status': 'Error',
        'message': 'Unable to retrieve certificate data from crt.sh'
    }

def get_certificate_data(domain):
    """
    Synchronous wrapper for get_first_certificate (deprecated).
    Use get_first_certificate instead for async operations.
    This is leftover from the original HTMLscraping method
    """
    prefix = log_prefix("get_certificate_data")
    logger.warning(f"{prefix} This function is deprecated. Use get_first_certificate instead.")
    try:
        loop = asyncio.get_event_loop()
        success, result = loop.run_until_complete(get_first_certificate(domain))
        return result if success else None
    except Exception as e:
        logger.error(f"{prefix} Error getting certificate data: {str(e)}")
        return None

async def main():
    parser = argparse.ArgumentParser(description='Get the first SSL certificate for a domain from crt.sh')
    parser.add_argument('url', help='The URL or domain to check (e.g., example.com or https://example.com)')
    args = parser.parse_args()

    # Extract the main domain
    domain = extract_main_domain(args.url)
    logging.info(f"Extracted domain: {domain}")
    
    # Get certificate info
    logging.info(f"Attempting to fetch certificate information from crt.sh...")
    success, result = await get_first_certificate(domain)
    
    if success:
        print("\nCertificate found:")
        print(f"Common Name: {result['Common Name']}")
        print(f"First Seen: {result['First Seen']}")
        print(f"Valid From: {result['Valid From']}")
        print(f"Source: {result['Source']}")
    else:
        print("Failed!")
        print(f"Error: {result}")

if __name__ == "__main__":
    asyncio.run(main()) 