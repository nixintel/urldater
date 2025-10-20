// Main application logic
import { createTimeline } from './timeline.js';
import { saveResults, loadResults, clearCache } from './cache.js';
import { displayDomainResults, displayHeadersResults, displayCertificateResults } from './data.js';

// Wait for DOM and modules to load
window.addEventListener('load', function() {
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
    
    // Form submission handler
    const handleSubmit = async function(event) {
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
            
            // Convert technical errors into user-friendly messages
            let userMessage = 'An error occurred while analyzing the URL. ';
            
            if (error.message.includes('split')) {
                userMessage += 'There was an issue processing the date information from the server.';
            } else if (error.message.includes('undefined')) {
                userMessage += 'Some required data was missing from the server response.';
            } else if (error.message.includes('HTTP error')) {
                userMessage += 'The server encountered an error. Please try again later.';
            } else {
                userMessage += error.message;
            }
            
            errorDiv.textContent = userMessage;
            errorDiv.classList.remove('d-none');
        } finally {
            spinner.style.display = 'none';
        }
    };

    // Initialize global variables
    window.domainResults = [];
    window.certResults = [];
    window.headerResults = [];
    window.headersPagination = { currentPage: 1, perPage: 10 };
    window.currentTimeline = null;

    // Function to reset page to clean state
    function resetToCleanState() {
        debugLog('Resetting to clean state');
        
        // Clear all result containers
        document.getElementById('domain-results').innerHTML = '';
        document.getElementById('headers-results').innerHTML = '';
        document.getElementById('ssl-certificate-results').innerHTML = '';
        
        // Hide all result sections
        document.getElementById('domain-info').style.display = 'none';
        document.getElementById('headers-info').style.display = 'none';
        document.getElementById('ssl-certificate').style.display = 'none';
        document.getElementById('timeline').style.display = 'none';
        
        // Clear the analyzed URL
        document.getElementById('analyzed-url').textContent = '';
        
        // Clear form
        document.getElementById('url').value = '';
        
        // Clear cached results
        clearCache();
        
        // Reset global variables
        window.domainResults = [];
        window.certResults = [];
        window.headerResults = [];
        window.currentTimeline = null;
        
        // Destroy any existing DataTables
        if ($.fn.DataTable.isDataTable('#domain-table')) {
            $('#domain-table').DataTable().destroy();
        }
        if ($.fn.DataTable.isDataTable('#headers-table')) {
            $('#headers-table').DataTable().destroy();
        }
        
        // Hide the New Search button
        const newSearchBtn = document.getElementById('newSearchBtn');
        if (newSearchBtn) {
            newSearchBtn.style.display = 'none';
        }
        
        debugLog('Clean state reset complete');
    }
    
    // Make resetToCleanState globally accessible
    window.resetToCleanState = resetToCleanState;

    // Check for cached results - only load if explicitly requested
    const cached = loadResults();
    const urlParams = new URLSearchParams(window.location.search);
    const loadCached = urlParams.get('loadCached') === 'true';
    
    if (cached && loadCached) {
        debugLog('Loading cached results');
        urlInput.value = cached.url;
        document.querySelector(`input[name="searchType"][value="${cached.searchType}"]`).checked = true;
        displayResults(cached.data, cached.searchType);
    } else {
        // Show clean landing page
        debugLog('Showing clean landing page');
        resetToCleanState();
    }

    // Attach submit handler
    searchForm.addEventListener('submit', handleSubmit);
    
    // Handle Home navigation - clear cached results when navigating to home
    const homeLink = document.querySelector('a[href="/"]');
    if (homeLink) {
        homeLink.addEventListener('click', function(e) {
            debugLog('Home link clicked - clearing cached results');
            clearCache();
            // The page will reload and show clean state
        });
    }

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
        
        // Show the New Search button when results are displayed
        const newSearchBtn = document.getElementById('newSearchBtn');
        if (newSearchBtn) {
            newSearchBtn.style.display = 'inline-block';
        }
        
        results.style.display = 'block';
    }
});