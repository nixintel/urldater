// Main application logic
import { createTimeline } from './timeline.js';
import { saveResults, loadResults } from './cache.js';

document.addEventListener('DOMContentLoaded', function() {
    // Set copyright year
    document.getElementById('copyright-year').textContent = new Date().getFullYear();

    // Initialize all tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    debugLog('Page loaded');
    
    // Get DOM elements
    const searchForm = document.getElementById('searchForm');
    const spinner = document.getElementById('spinner');
    const results = document.getElementById('results');
    const errorDiv = document.getElementById('error');
    const urlInput = document.getElementById('url');

    // Initialize DataTables
    let domainTable = null;
    let headersTable = null;

    if (!searchForm) {
        debugError('Search form not found!');
        return;
    }

    debugLog('Form found:', searchForm);

    // Initialize global variables
    window.domainResults = [];
    window.certResults = [];
    window.headerResults = [];
    window.headersPagination = { currentPage: 1, perPage: 10 };
    window.currentTimeline = null;

    // Check for cached results
    const cached = loadResults();
    if (cached) {
        urlInput.value = cached.url;
        document.querySelector(`input[name="searchType"][value="${cached.searchType}"]`).checked = true;
        displayResults(cached.data, cached.searchType);
    }

    // Form submission handler
    searchForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        debugLog('Form submitted');
        
        const url = urlInput.value;
        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        
        // Set the analyzed URL in the results title
        document.getElementById('analyzed-url').textContent = url;
        
        debugLog('URL:', url);
        debugLog('Search Type:', searchType);
        
        // Show spinner and hide previous results/errors
        spinner.style.display = 'block';
        if (results) results.style.display = 'none';
        if (errorDiv) errorDiv.classList.add('d-none');

        // Clean up existing DataTables instances
        if ($.fn.DataTable.isDataTable('#domain-table')) {
            $('#domain-table').DataTable().destroy();
        }
        if ($.fn.DataTable.isDataTable('#headers-table')) {
            $('#headers-table').DataTable().destroy();
        }
        
        // Clear all previous results and reset displays
        document.getElementById('domain-results').innerHTML = '';
        document.getElementById('headers-results').innerHTML = '';
        document.getElementById('ssl-certificate-results').innerHTML = '';
        document.getElementById('domain-info').style.display = 'none';
        document.getElementById('headers-info').style.display = 'none';
        document.getElementById('ssl-certificate').style.display = 'none';
        document.getElementById('timeline').style.display = 'none';

        try {
            debugLog('Sending request...');
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: url,
                    searchType: searchType
                })
            });

            debugLog('Response received:', response.status);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            debugLog('Data received:', data);
            
            // Save results to cache
            saveResults(url, searchType, data);
            
            // Display the results
            displayResults(data, searchType);
            
        } catch (error) {
            debugError('Error:', error);
            errorDiv.textContent = error.message;
            errorDiv.classList.remove('d-none');
        } finally {
            spinner.style.display = 'none';
        }
    });

    function displayResults(data, searchType) {
        // Create timeline and update checkboxes
        createTimeline(data);
        
        // Show results based on search type
        if (searchType === 'all') {
            // Always show all sections in 'all' mode
            document.getElementById('domain-info').style.display = 'block';
            document.getElementById('headers-info').style.display = 'block';
            document.getElementById('ssl-certificate').style.display = 'block';

            // Handle RDAP results
            if (data.rdap) {
                displayDomainResults(data.rdap);
            }

            // Handle Headers results
            if (data.headers) {
                displayHeadersResults(data.headers);
            }

            // Handle Certificate results
            if (data.certs && Array.isArray(data.certs) && data.certs.length > 0) {
                displayCertificateResults(data.certs);
            } else if (data.certs && data.certs.error) {
                // Handle error object from crt.sh
                displayCertificateResults([data.certs]);
            } else {
                // Handle case where certs data is missing or empty
                displayCertificateResults(null);
            }
        } else if (searchType === 'rdap' && data) {
            document.getElementById('domain-info').style.display = 'block';
            displayDomainResults(data);
        } else if (searchType === 'headers' && data) {
            document.getElementById('headers-info').style.display = 'block';
            displayHeadersResults(data);
        } else if (searchType === 'certs') {
            document.getElementById('ssl-certificate').style.display = 'block';
            // Handle both array and error object formats
            if (Array.isArray(data)) {
                displayCertificateResults(data);
            } else if (data && (data.error || data.status === 'Service Unavailable')) {
                // Handle error object format
                displayCertificateResults([data]);
            } else {
                displayCertificateResults(null);
            }
        }
        
        results.style.display = 'block';
    }
});