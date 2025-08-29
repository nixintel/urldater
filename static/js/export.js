// Export functions
async function prepareForExport() {
    // Store current state of DataTables
    const headersTable = $('#headers-table').DataTable();
    const currentPage = headersTable.page();
    const currentLength = headersTable.page.len();
    
    // Set to show all entries
    headersTable.page.len(-1).draw();
    
    // Hide pagination and length controls
    const clone = document.getElementById('results').cloneNode(true);
    const paginationControls = clone.querySelectorAll('.dataTables_paginate, .dataTables_length, .dataTables_filter');
    paginationControls.forEach(control => {
        control.style.display = 'none';
    });
    
    // Remove export buttons
    const exportButtons = clone.querySelector('.mb-4.export-buttons');
    if (exportButtons) {
        exportButtons.remove();
    }
    
    return {
        clone,
        restore: () => {
            // Restore original state
            headersTable.page.len(currentLength).page(currentPage).draw();
        }
    };
}

async function exportAsPNG() {
    const exportSpinner = document.getElementById('export-spinner');
    
    try {
        exportSpinner.style.display = 'inline-block';
        
        // Get the URL for the filename
        const url = document.getElementById('url').value;
        const domain = url.replace(/^https?:\/\//, '').split('/')[0];
        const timestamp = new Date().toISOString().slice(0,10).replace(/-/g,'');
        const filename = `${domain}_${timestamp}_results.png`;

        // Prepare clone with all results visible
        const { clone, restore } = await prepareForExport();
        
        // Temporarily append clone to document for html2canvas
        clone.style.position = 'absolute';
        clone.style.left = '-9999px';
        document.body.appendChild(clone);
        
        // Wait a moment for the table to render fully
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Capture the clone as PNG
        const canvas = await html2canvas(clone, {
            scale: 2, // Higher quality
            useCORS: true,
            logging: false,
            backgroundColor: '#ffffff',
            windowWidth: 1920, // Force wider viewport
            width: clone.scrollWidth, // Capture full width
            height: clone.scrollHeight // Capture full height
        });
        
        // Remove the clone
        document.body.removeChild(clone);
        
        // Convert to blob and download
        canvas.toBlob((blob) => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        });
        
    } catch (error) {
        console.error('Error exporting as PNG:', error);
        alert('Error saving as PNG. Please try again.');
    } finally {
        restore(); // Restore original table state
        exportSpinner.style.display = 'none';
    }
}

async function exportAsPDF() {
    const exportSpinner = document.getElementById('export-spinner');
    
    try {
        exportSpinner.style.display = 'inline-block';
        
        // Get the URL for the filename
        const url = document.getElementById('url').value;
        const domain = url.replace(/^https?:\/\//, '').split('/')[0];
        const timestamp = new Date().toISOString().slice(0,10).replace(/-/g,'');
        const filename = `${domain}_${timestamp}_results.pdf`;

        // Prepare clone with all results visible
        const { clone, restore } = await prepareForExport();
        
        // Temporarily append clone to document for html2canvas
        clone.style.position = 'absolute';
        clone.style.left = '-9999px';
        document.body.appendChild(clone);
        
        // Wait a moment for the table to render fully
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Capture the clone as canvas
        const canvas = await html2canvas(clone, {
            scale: 2,
            useCORS: true,
            logging: false,
            backgroundColor: '#ffffff',
            windowWidth: 1920, // Force wider viewport
            width: clone.scrollWidth, // Capture full width
            height: clone.scrollHeight // Capture full height
        });
        
        // Remove the clone
        document.body.removeChild(clone);
        
        // Convert canvas to PDF
        const { jsPDF } = window.jspdf;
        
        // Calculate PDF dimensions to fit the content
        const imgWidth = 595; // A4 width in points (72 DPI)
        const imgHeight = (canvas.height * imgWidth) / canvas.width;
        
        const pdf = new jsPDF({
            orientation: imgHeight > imgWidth ? 'portrait' : 'landscape',
            unit: 'pt',
            format: [Math.max(imgWidth, imgHeight), Math.min(imgWidth, imgHeight)]
        });
        
        // Add the canvas as image to PDF with proper scaling
        pdf.addImage(
            canvas.toDataURL('image/png'),
            'PNG',
            0,
            0,
            imgWidth,
            imgHeight,
            '',
            'FAST'
        );
        
        // Save the PDF
        pdf.save(filename);
        
    } catch (error) {
        console.error('Error exporting as PDF:', error);
        alert('Error saving as PDF. Please try again.');
    } finally {
        restore(); // Restore original table state
        exportSpinner.style.display = 'none';
    }
}
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
        const response = await fetch(`/urldater/export/${type}`, {
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
        const response = await fetch('/urldater/export/all', {
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