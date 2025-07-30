// Timeline functionality
function updateTimelineFilterVisibility(data) {
    const rdapCheckbox = document.getElementById('showRdap');
    const certsCheckbox = document.getElementById('showCerts');
    const headersCheckbox = document.getElementById('showHeaders');
    
    // Hide all checkboxes by default
    rdapCheckbox.parentElement.style.display = 'none';
    certsCheckbox.parentElement.style.display = 'none';
    headersCheckbox.parentElement.style.display = 'none';
    
    // Uncheck all checkboxes
    rdapCheckbox.checked = false;
    certsCheckbox.checked = false;
    headersCheckbox.checked = false;
    
    // Show and check only relevant checkboxes based on data
    if (data.rdap && data.rdap.length > 0) {
        rdapCheckbox.parentElement.style.display = 'block';
        rdapCheckbox.checked = true;
    }
    if (data.certs && data.certs.length > 0) {
        certsCheckbox.parentElement.style.display = 'block';
        certsCheckbox.checked = true;
    }
    if (data.headers && data.headers.length > 0) {
        headersCheckbox.parentElement.style.display = 'block';
        headersCheckbox.checked = true;
    }
    
    // For single module results (when data is an array)
    if (Array.isArray(data)) {
        if (data.length > 0) {
            if (data[0]['First Seen']) {
                certsCheckbox.parentElement.style.display = 'block';
                certsCheckbox.checked = true;
            } else if (data[0].type === 'Registered' || data[0].type === 'Updated') {
                rdapCheckbox.parentElement.style.display = 'block';
                rdapCheckbox.checked = true;
            } else if (data[0].type === 'favicon' || data[0].type === 'image') {
                headersCheckbox.parentElement.style.display = 'block';
                headersCheckbox.checked = true;
            }
        }
    }
}

function createTimeline(data) {
    console.log('Creating timeline with data:', data);
    
    const container = document.getElementById('visualization');
    const timelineContainer = document.getElementById('timeline');
    
    timelineItems.clear();
    let items = [];
    let hasData = false;

    let normalizedData = {
        headers: [],
        certs: [],
        rdap: []
    };

    console.log('Data type:', typeof data);
    console.log('Is array:', Array.isArray(data));

    // Normalize the data structure
    if (Array.isArray(data)) {
        // Check each item in the array
        data.forEach(item => {
            if (item['First Seen']) {
                // This is certificate data
                normalizedData.certs.push(item);
            } else if (item.type === 'favicon' || item.type === 'image') {
                normalizedData.headers.push(item);
            } else if (item.type === 'Registered' || item.type === 'Updated') {
                normalizedData.rdap.push(item);
            }
        });
    } else if (typeof data === 'object') {
        // Handle combined or single object results
        if (data.headers) normalizedData.headers = Array.isArray(data.headers) ? data.headers : [data.headers];
        if (data.certs) normalizedData.certs = Array.isArray(data.certs) ? data.certs : [data.certs];
        if (data.rdap) normalizedData.rdap = Array.isArray(data.rdap) ? data.rdap : [data.rdap];
        
        // Handle single object results
        if (data['First Seen']) {
            normalizedData.certs = [data];
        } else if (data.type === 'favicon' || data.type === 'image') {
            normalizedData.headers = [data];
        } else if (data.type === 'Registered' || data.type === 'Updated') {
            normalizedData.rdap = [data];
        }
    }

    console.log('Normalized data:', normalizedData);

    // Update checkbox visibility based on normalized data
    updateTimelineFilterVisibility(normalizedData);

    // Process certificate data first
    normalizedData.certs.forEach(item => {
        if (item['First Seen']) {
            console.log('Processing cert item:', item);
            let date = null;
            
            // Direct handling for certificate date format "DD-MM-YYYY"
            const dateStr = item['First Seen'];
            const dateRegex = /^(\d{2})-(\d{2})-(\d{4})$/;
            const match = dateStr.match(dateRegex);
            
            if (match) {
                const [_, day, month, year] = match;
                date = new Date(Date.UTC(
                    parseInt(year, 10),
                    parseInt(month, 10) - 1,
                    parseInt(day, 10),
                    0, 0, 0 // Use midnight UTC
                ));
                console.log('Parsed certificate date with UTC preservation:', date);
            }
            
            if (date && !isNaN(date.getTime())) {
                hasData = true;
                const timelineItem = {
                    id: items.length + 1,
                    content: 'First SSL certificate',
                    start: date,
                    className: 'timeline-cert',
                    group: 'certs',
                    title: `First SSL certificate<br>Common Name: ${item['Common Name']}<br>First Seen: ${item['First Seen']}`
                };
                console.log('Added certificate event to timeline with date:', date);
                items.push(timelineItem);
            } else {
                console.error('Failed to parse certificate date:', item['First Seen']);
            }
        }
    });

    // Process headers data
    normalizedData.headers.forEach(item => {
        if (item.last_modified) {
            console.log('Processing headers item:', item);
            let date = null;
            
            // Direct handling for headers date format "DD-MM-YYYY HH:MM:SS"
            const dateStr = item.last_modified;
            const dateRegex = /^(\d{2})-(\d{2})-(\d{4})\s(\d{2}):(\d{2}):(\d{2})(?:\s+([A-Z]+))?$/;
            const match = dateStr.match(dateRegex);
            
            if (match) {
                const [_, day, month, year, hours, minutes, seconds, timezone] = match;
                date = new Date(Date.UTC(
                    parseInt(year, 10),
                    parseInt(month, 10) - 1,
                    parseInt(day, 10),
                    parseInt(hours, 10),
                    parseInt(minutes, 10),
                    parseInt(seconds, 10)
                ));
                console.log('Parsed headers date with UTC preservation:', date);
            }
            
            if (date && !isNaN(date.getTime())) {
                hasData = true;
                items.push({
                    id: items.length + 1,
                    content: item.type === 'favicon' ? 'Favicon last modified' : 'Image last modified',
                    start: date,
                    className: item.type === 'favicon' ? 'timeline-favicon' : 'timeline-header',
                    group: 'headers',
                    title: `${item.type}<br>${item.last_modified}<br>${item.url}`
                });
                console.log('Added headers event to timeline with date:', date);
            } else {
                console.error('Failed to parse headers date:', item.last_modified);
            }
        }
    });

    // Process RDAP data
    normalizedData.rdap.forEach(item => {
        console.log('Processing RDAP item:', item);
        
        // Handle registration events
        if (item.type === 'Registered' && !item.error) {
            let date = null;
            
            // First try to use the _registered_dt field directly
            if (item._registered_dt) {
                console.log('Using _registered_dt field directly:', item._registered_dt);
                date = new Date(item._registered_dt);
                if (isNaN(date.getTime())) {
                    console.error('Invalid date from _registered_dt:', item._registered_dt);
                    date = null;
                }
            }
            
            // Fallback: If _registered_dt is missing or invalid, use the string but preserve timezone
            if (!date && (item.registered || item.last_modified)) {
                console.log('Falling back to string date:', item.registered || item.last_modified);
                
                // Direct handling for our specific format "DD-MM-YYYY HH:MM:SS UTC"
                const dateStr = item.registered || item.last_modified;
                const dateRegex = /^(\d{2})-(\d{2})-(\d{4})\s(\d{2}):(\d{2}):(\d{2})\s+UTC$/;
                const match = dateStr.match(dateRegex);
                
                if (match) {
                    const [_, day, month, year, hours, minutes, seconds] = match;
                    date = new Date(Date.UTC(
                        parseInt(year, 10),
                        parseInt(month, 10) - 1,
                        parseInt(day, 10),
                        parseInt(hours, 10),
                        parseInt(minutes, 10),
                        parseInt(seconds, 10)
                    ));
                    console.log('Parsed date from string with UTC preservation:', date);
                }
            }
            
            // Add to timeline if we have a valid date
            if (date && !isNaN(date.getTime())) {
                hasData = true;
                items.push({
                    id: items.length + 1,
                    content: 'Domain first registered',
                    start: date,
                    className: 'timeline-rdap',
                    group: 'rdap',
                    title: `Domain Registration<br>${item.registered || item.last_modified}`
                });
                console.log('Added registration event to timeline with date:', date);
            } else {
                console.error('Failed to get a valid date for registration event');
            }
        }
        
        // Handle update events
        if (item.type === 'Updated' && !item.error) {
            let date = null;
            
            // First try to use the _updated_dt field directly
            if (item._updated_dt) {
                console.log('Using _updated_dt field directly:', item._updated_dt);
                date = new Date(item._updated_dt);
                if (isNaN(date.getTime())) {
                    console.error('Invalid date from _updated_dt:', item._updated_dt);
                    date = null;
                }
            }
            
            // Fallback: If _updated_dt is missing or invalid, use the string but preserve timezone
            if (!date && (item.updated || item.last_modified)) {
                console.log('Falling back to string date:', item.updated || item.last_modified);
                
                // Direct handling for our specific format "DD-MM-YYYY HH:MM:SS UTC"
                const dateStr = item.updated || item.last_modified;
                const dateRegex = /^(\d{2})-(\d{2})-(\d{4})\s(\d{2}):(\d{2}):(\d{2})\s+UTC$/;
                const match = dateStr.match(dateRegex);
                
                if (match) {
                    const [_, day, month, year, hours, minutes, seconds] = match;
                    date = new Date(Date.UTC(
                        parseInt(year, 10),
                        parseInt(month, 10) - 1,
                        parseInt(day, 10),
                        parseInt(hours, 10),
                        parseInt(minutes, 10),
                        parseInt(seconds, 10)
                    ));
                    console.log('Parsed date from string with UTC preservation:', date);
                }
            }
            
            // Add to timeline if we have a valid date
            if (date && !isNaN(date.getTime())) {
                hasData = true;
                items.push({
                    id: items.length + 1,
                    content: 'Domain registration updated',
                    start: date,
                    className: 'timeline-rdap',
                    group: 'rdap',
                    title: `Domain Update<br>${item.updated || item.last_modified}`
                });
                console.log('Added update event to timeline with date:', date);
            } else {
                console.error('Failed to get a valid date for update event');
            }
        }
    });

    // Only create timeline if we have data
    if (hasData && items.length > 0) {
        console.log('Adding items to timeline:', JSON.stringify(items, null, 2));
        
        try {
            // Create a new DataSet with the items
            timelineItems = new vis.DataSet(items);
            
            const options = {
                height: '300px',
                showCurrentTime: false,
                showTooltips: true,
                horizontalScroll: true,
                zoomable: true,
                groupOrder: 'content',
                margin: { item: { horizontal: 10 }},
                orientation: 'top'
            };

            if (timeline === null) {
                timeline = new vis.Timeline(container, timelineItems, options);
            } else {
                timeline.setOptions(options);
                timeline.setItems(timelineItems);
            }

            // After setting items, ensure all events are visible
            timeline.fit({ animation: { duration: 1000, easingFunction: 'easeInOutQuad' }});
            
            timelineContainer.style.display = 'block';
        } catch (e) {
            console.error('Error creating timeline:', e);
        }
    } else {
        console.log('No data to display in timeline. hasData:', hasData, 'items.length:', items.length);
        timelineContainer.style.display = 'none';
    }
}

function updateTimelineVisibility() {
    const showRdap = document.getElementById('showRdap').checked;
    const showCerts = document.getElementById('showCerts').checked;
    const showHeaders = document.getElementById('showHeaders').checked;
    
    let visibleItems = [];
    
    timelineItems.forEach(item => {
        if ((item.group === 'rdap' && showRdap) ||
            (item.group === 'certs' && showCerts) ||
            (item.group === 'headers' && showHeaders)) {
            visibleItems.push(item);
        }
    });
    
    if (timeline) {
        timeline.setItems(new vis.DataSet(visibleItems));
    }
} 