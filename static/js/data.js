// Data handling functions
function displayDomainResults(data) {
    const tbody = document.getElementById('domain-results');
    tbody.innerHTML = '';
    
    if (!data || !data.length) return;

    // Check if the response contains an error
    if (data[0].error) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="3" class="text-danger">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                ${data[0].error}
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

function displayHeadersResults(data) {
    const tbody = document.getElementById('headers-results');
    const filterValue = document.getElementById('type-filter').value;
    tbody.innerHTML = '';
    
    if (!data || !data.length) return;

    // Store the data for filtering
    window.headerResults = data;

    // Destroy existing DataTable if it exists
    if ($.fn.DataTable.isDataTable('#headers-table')) {
        $('#headers-table').DataTable().destroy();
    }

    let filteredResults = [...data];
    if (filterValue !== 'all') {
        filteredResults = filteredResults.filter(item => 
            item.type.toLowerCase() === filterValue.toLowerCase()
        );
    }

    // Display the data
    filteredResults.forEach(item => {
        // Parse the date string into a timestamp for sorting
        const [date, time] = item.last_modified.split(' ');
        const [day, month, year] = date.split('-');
        const timestamp = new Date(`${year}-${month}-${day} ${time}`).getTime();
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${item.type}</td>
            <td><a href="${item.url}" target="_blank">${item.url}</a></td>
            <td data-order="${timestamp}">${item.last_modified}</td>
        `;
        tbody.appendChild(row);
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

function displayCertificateResults(data) {
    const tbody = document.getElementById('ssl-certificate-results');
    tbody.innerHTML = '';  // Clear existing results
    
    // Handle no data case
    if (!data) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="5" class="text-warning">
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>Certificate Service Notice:</strong> Unable to connect to crt.sh to retrieve certificate history. The site may be offline.
                </div>
            </td>
        `;
        tbody.appendChild(row);
        return;
    }

    if (!Array.isArray(data)) {
        data = [data];  // Convert single object to array
    }
    
    // Check if the response contains an error message
    if (data[0].status === 'Service Unavailable' || data[0].error) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="5" class="text-warning">
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>Certificate Service Notice:</strong> ${data[0].message || data[0].error}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    } else {
        data.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${item.type}</td>
                <td>${item['Common Name']}</td>
                <td>${item['First Seen']}</td>
                <td>${item['Valid From']}</td>
                <td><a href="${item['Source']}" target="_blank">View Certificate</a></td>
            `;
            tbody.appendChild(row);
        });
    }
    
    document.getElementById('ssl-certificate').style.display = 'block';
}

function filterHeadersResults() {
    displayHeadersResults(window.headerResults);
} 