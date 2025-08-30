// Cache management for URL Dater results
const CACHE_KEY = 'urldater_results';
const CACHE_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours in milliseconds

export function saveResults(url, searchType, data) {
    const cacheData = {
        url,
        searchType,
        data,
        timestamp: Date.now()
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(cacheData));
}

export function loadResults() {
    const cached = localStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const cacheData = JSON.parse(cached);
    
    // Check if cache has expired
    if (Date.now() - cacheData.timestamp > CACHE_EXPIRY) {
        localStorage.removeItem(CACHE_KEY);
        return null;
    }

    return cacheData;
}

export function clearCache() {
    localStorage.removeItem(CACHE_KEY);
}
