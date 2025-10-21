// Data handling functions
export function displayDomainResults(data) {
    const tbody = document.getElementById('domain-results');
    tbody.innerHTML = '';
    
    if (!data || !data.length) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3" class="text-muted">
                <div class="alert alert-info mb-0">
                    <i class="bi bi-info-circle me-2"></i>
                    No domain registration information available.
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Check if the response contains an error
    if (data[0].error) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3">
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>RDAP Service Notice:</strong> ${data[0].error}
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Destroy existing DataTable if it exists
    if ($.fn.DataTable.isDataTable('#domain-table')) {
        $('#domain-table').DataTable().destroy();
    }

    // Display the data
    data.forEach(item => {
        // Get the appropriate date field based on type
        const dateStr = item.type === 'Registered' ? 
            (item.registered || item.last_modified) : 
            (item.updated || item.last_modified);
        
        // Parse the date string into a timestamp for sorting
        const [date, time] = dateStr.split(' ');
        const [day, month, year] = date.split('-');
        const timestamp = new Date(`${year}-${month}-${day} ${time}`).getTime();
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${item.type}</td>
            <td><a href="${item.url}" target="_blank">${item.url}</a></td>
            <td data-order="${timestamp}">${dateStr}</td>
        `;
        tbody.appendChild(row);
    });

    // Initialize DataTable with sorting
    $('#domain-table').DataTable({
        order: [[2, 'asc']],
        columnDefs: [{
            targets: 2,
            type: 'num'
        }],
        language: {
            paginate: {
                previous: "Previous",
                next: "Next"
            }
        },
        pagingType: "simple",
        pageLength: 10,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]]
    });
}

export function displayHeadersResults(data) {
    const tbody = document.getElementById('headers-results');
    const filterValue = document.getElementById('type-filter').value;
    tbody.innerHTML = '';
    
    if (!data || !data.length) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3">
                <div class="alert alert-info mb-0">
                    <i class="bi bi-info-circle me-2"></i>
                    <strong>Headers Service Notice:</strong> No last-modified headers found.
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Filter out info/error messages to get only valid results
    const validResults = data.filter(item => 
        item.type && 
        item.type !== 'Info' && 
        item.type !== 'Error' && 
        !item.error
    );

    // If no valid results, show the first info/error message
    if (validResults.length === 0) {
        // Don't show the table headers for info/error messages
        const table = document.getElementById('headers-table');
        if (table) {
            const thead = table.querySelector('thead');
            if (thead) thead.style.display = 'none';
        }

        const row = document.createElement('tr');
        const alertClass = data[0].type === 'Info' ? 'alert-info' : 'alert-warning';
        const icon = data[0].type === 'Info' ? 'bi-info-circle' : 'bi-exclamation-triangle-fill';
        row.innerHTML = `
            <td colspan="3">
                <div class="alert ${alertClass} mb-0">
                    <i class="bi ${icon} me-2"></i>
                    <strong>Headers Service Notice:</strong> ${data[0].error || data[0].message}
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    // Show table headers for valid results
    const table = document.getElementById('headers-table');
    if (table) {
        const thead = table.querySelector('thead');
        if (thead) thead.style.display = '';
    }

    // Store the valid results for filtering
    window.headerResults = validResults;

    // Destroy existing DataTable if it exists
    if ($.fn.DataTable.isDataTable('#headers-table')) {
        $('#headers-table').DataTable().destroy();
    }

    let filteredResults = [...validResults];
    if (filterValue !== 'all') {
        filteredResults = filteredResults.filter(item => 
            item.type.toLowerCase() === filterValue.toLowerCase()
        );
    }

    // Display the data
    filteredResults.forEach(item => {
        try {
            let timestamp = 0;
            let formattedDate = 'N/A';
            
            // Check if last_modified exists and is properly formatted
            if (item.last_modified && typeof item.last_modified === 'string') {
                // Parse the date string into a timestamp for sorting
                const [date, time] = item.last_modified.split(' ');
                if (date && time) {
                    const [day, month, year] = date.split('-');
                    if (day && month && year) {
                        timestamp = new Date(`${year}-${month}-${day} ${time}`).getTime();
                        formattedDate = item.last_modified;
                    }
                }
            }
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.type || 'Unknown'}</td>
                <td><a href="${item.url || '#'}" target="_blank">${item.url || 'No URL available'}</a></td>
                <td data-order="${timestamp}">${formattedDate}</td>
            `;
            tbody.appendChild(row);
        } catch (error) {
            console.error('Error processing header item:', error);
            const row = document.createElement('tr');
            row.innerHTML = `
                <td colspan="3" class="text-warning">
                    <div class="alert alert-warning mb-0">
                        <i class="bi bi-exclamation-triangle-fill me-2"></i>
                        Error processing this item
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        }
    });

    // Initialize DataTable with sorting
    $('#headers-table').DataTable({
        order: [[2, 'asc']],
        columnDefs: [{
            targets: 2,
            type: 'num'
        }],
        language: {
            paginate: {
                previous: "Previous",
                next: "Next"
            }
        },
        pagingType: "simple",
        pageLength: 10,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]]
    });
}

export function displayCertificateResults(data) {
    const tbody = document.getElementById('ssl-certificate-results');
    tbody.innerHTML = '';  // Clear existing results
    
    // Default error message
    const defaultErrorMessage = 'Unable to connect to crt.sh to retrieve certificate history. The site may be offline.';
    
    // Handle no data case
    if (!data) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="5" class="text-warning">
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>Certificate Service Notice:</strong> ${defaultErrorMessage}
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    if (!Array.isArray(data)) {
        data = [data];  // Convert single object to array
    }
    
    try {
        // Check if the response contains an error message
        if (data[0] && (data[0].status === 'Service Unavailable' || data[0].error || data[0].message)) {
            const errorMessage = data[0].message || data[0].error || defaultErrorMessage;
            const row = document.createElement('tr');
            row.innerHTML = `
                <td colspan="5" class="text-warning">
                    <div class="alert alert-warning mb-0">
                        <i class="bi bi-exclamation-triangle-fill me-2"></i>
                        <strong>Certificate Service Notice:</strong> ${errorMessage}
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        } else if (data[0] && data[0].type === 'SSL Certificate') {
            // Valid certificate data
            data.forEach(item => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${item.type}</td>
                    <td>${item['Common Name'] || 'N/A'}</td>
                    <td>${item['First Seen'] || 'N/A'}</td>
                    <td>${item['Valid From'] || 'N/A'}</td>
                    <td>${item['Source'] ? `<a href="${item['Source']}" target="_blank">View Certificate</a>` : 'N/A'}</td>
                `;
                tbody.appendChild(row);
            });
        } else {
            // Unexpected data format
            throw new Error('Invalid certificate data format');
        }
    } catch (error) {
        console.error('Error displaying certificate results:', error);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="5" class="text-warning">
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>Certificate Service Notice:</strong> ${defaultErrorMessage}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    }
    
    document.getElementById('ssl-certificate').style.display = 'block';
}

export function filterHeadersResults() {
    displayHeadersResults(window.headerResults);
} 