$(document).ready(function() {
    let dataTable = null;
    let currentData = null;

    $('#urlForm').on('submit', function(e) {
        e.preventDefault();
        
        const url = $('#urlInput').val();
        
        $('#loading').removeClass('d-none');
        $('#results').addClass('d-none');
        $('#error').addClass('d-none');
        
        if (dataTable) {
            dataTable.destroy();
        }

        $.ajax({
            url: '/analyze',
            method: 'POST',
            data: { url: url },
            success: function(response) {
                currentData = response.results;
                
                dataTable = $('#resultsTable').DataTable({
                    data: response.results,
                    columns: [
                        { data: 'type' },
                        { data: 'url' },
                        { 
                            data: 'last_modified',
                            render: function(data) {
                                return data ? new Date(data).toLocaleString() : 'N/A';
                            }
                        }
                    ],
                    order: [[2, 'asc']]
                });
                
                $('#results').removeClass('d-none');
            },
            error: function(xhr) {
                const error = xhr.responseJSON ? xhr.responseJSON.error : 'An error occurred';
                $('#error').text(error).removeClass('d-none');
            },
            complete: function() {
                $('#loading').addClass('d-none');
            }
        });
    });

    $('#exportBtn').on('click', function() {
        if (!currentData) return;

        $.ajax({
            url: '/export',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(currentData),
            xhrFields: {
                responseType: 'blob'
            },
            success: function(blob) {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'media_analysis.csv';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                a.remove();
            }
        });
    });
}); 