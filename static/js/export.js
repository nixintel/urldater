// Export functions
async function exportTable(type) {
    const url = document.getElementById('url').value;
    const domain = url.replace(/^https?:\/\//, '').split('/')[0];
    let tableData;
    
    if (type === 'rdap') {
        tableData = Array.from(document.getElementById('domain-results').children).map(row => {
            // Extract only the type, URL, and time columns
            const type = row.children[0].textContent;
            const url = row.children[1].firstChild.href;
            const time = row.children[2].textContent;
            
            return {
                type: type,
                url: url,
                time: time
            };
        });
    } else if (type === 'certs') {
        tableData = Array.from(document.getElementById('ssl-certificate-results').children).map(row => ({
            type: row.children[0].textContent,
            common_name: row.children[1].textContent,
            first_seen: row.children[2].textContent,
            valid_from: row.children[3].textContent,
            source: row.children[4].firstChild.href
        }));
    } else {
        tableData = Array.from(document.getElementById('headers-results').children).map(row => ({
            type: row.children[0].textContent,
            url: row.children[1].firstChild.href,
            last_modified: row.children[2].textContent
        }));
    }

    try {
        const response = await fetch(`/export/${type}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                domain: domain,
                table_data: tableData
            })
        });
        
        if (!response.ok) throw new Error('Export failed');
        
        // Get the filename from the Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = '';
        if (contentDisposition && contentDisposition.includes('filename=')) {
            filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
        } else {
            // Fallback filename format
            const timestamp = new Date().toISOString().slice(0,10).replace(/-/g,'');
            filename = `${domain}_${timestamp}_${type}.csv`;
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Export error:', error);
        alert('Error exporting data');
    }
}

async function exportAll() {
    const url = document.getElementById('url').value;
    const domain = url.replace(/^https?:\/\//, '').split('/')[0];
    
    let data = {
        domain: domain,
        rdap_data: [],
        headers_data: [],
        cert_data: []
    };
    
    // Collect all available data based on what's displayed
    if (document.getElementById('domain-info').style.display !== 'none') {
        data.rdap_data = Array.from(document.getElementById('domain-results').children).map(row => {
            // Extract only the type, URL, and time columns
            const type = row.children[0].textContent;
            const url = row.children[1].firstChild.href;
            const time = row.children[2].textContent;
            
            return {
                type: type,
                url: url,
                time: time
            };
        });
    }
    
    if (document.getElementById('headers-info').style.display !== 'none') {
        data.headers_data = Array.from(document.getElementById('headers-results').children).map(row => ({
            type: row.children[0].textContent,
            url: row.children[1].firstChild.href,
            last_modified: row.children[2].textContent
        }));
    }
    
    if (document.getElementById('ssl-certificate').style.display !== 'none') {
        data.cert_data = Array.from(document.getElementById('ssl-certificate-results').children).map(row => ({
            type: row.children[0].textContent,
            common_name: row.children[1].textContent,
            first_seen: row.children[2].textContent,
            valid_from: row.children[3].textContent,
            source: row.children[4].firstChild.href
        }));
    }

    try {
        const response = await fetch('/export/all', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) throw new Error('Export failed');
        
        // Get the filename from the Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = '';
        if (contentDisposition && contentDisposition.includes('filename=')) {
            filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
        } else {
            // Fallback filename format
            const timestamp = new Date().toISOString().slice(0,10).replace(/-/g,'');
            filename = `${domain}_${timestamp}_all.zip`;
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (error) {
        console.error('Export error:', error);
        alert('Error exporting data');
    }
} 