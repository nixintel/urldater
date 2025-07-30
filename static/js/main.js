// Main application logic
document.addEventListener('DOMContentLoaded', function() {
    // Set copyright year
    document.getElementById('copyright-year').textContent = new Date().getFullYear();

    // Initialize all tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    console.log('Page loaded');
    
    // Get DOM elements
    const searchForm = document.getElementById('searchForm');
    const spinner = document.getElementById('spinner');
    const results = document.getElementById('results');
    const errorDiv = document.getElementById('error');

    // Initialize DataTables
    let domainTable = null;
    let headersTable = null;

    if (!searchForm) {
        console.error('Search form not found!');
        return;
    }

    console.log('Form found:', searchForm);

    // Initialize global variables
    window.domainResults = [];
    window.certResults = [];
    window.headerResults = [];
    window.headersPagination = { currentPage: 1, perPage: 10 };
    window.currentTimeline = null;

    window.timeline = null;
    window.timelineItems = new vis.DataSet();
    
    // Add event listeners for checkboxes
    document.getElementById('showRdap').addEventListener('change', updateTimelineVisibility);
    document.getElementById('showCerts').addEventListener('change', updateTimelineVisibility);
    document.getElementById('showHeaders').addEventListener('change', updateTimelineVisibility);
    
    // Form submission handler
    searchForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        console.log('Form submitted');
        
        const urlInput = document.getElementById('url');
        const url = urlInput.value;
        const searchType = document.querySelector('input[name="searchType"]:checked').value;
        
        // Set the analyzed URL in the results title
        document.getElementById('analyzed-url').textContent = url;
        
        console.log('URL:', url);
        console.log('Search Type:', searchType);
        
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
        
        // Clear timeline if it exists
        if (window.timeline) {
            window.timelineItems.clear();
        }

        try {
            console.log('Sending request...');
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

            console.log('Response received:', response.status);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('Data received:', data);
            
            // Create timeline and update checkboxes
            createTimeline(data);
            
            // Show results based on search type
            if (searchType === 'all') {
                if (data.rdap && data.rdap.length > 0) {
                    document.getElementById('domain-info').style.display = 'block';
                    displayDomainResults(data.rdap);
                }
                if (data.headers && data.headers.length > 0) {
                    document.getElementById('headers-info').style.display = 'block';
                    displayHeadersResults(data.headers);
                }
                if (data.certs) {
                    document.getElementById('ssl-certificate').style.display = 'block';
                    displayCertificateResults(data.certs);
                }
            } else if (searchType === 'rdap' && data) {
                document.getElementById('domain-info').style.display = 'block';
                displayDomainResults(data);
            } else if (searchType === 'headers' && data) {
                document.getElementById('headers-info').style.display = 'block';
                displayHeadersResults(data);
            } else if (searchType === 'certs' && data) {
                document.getElementById('ssl-certificate').style.display = 'block';
                displayCertificateResults(data);
            }
            
            results.style.display = 'block';
            
        } catch (error) {
            console.error('Error:', error);
            errorDiv.textContent = error.message;
            errorDiv.classList.remove('d-none');
        } finally {
            spinner.style.display = 'none';
        }
    });
}); 