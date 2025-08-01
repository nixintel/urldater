// Debug configuration
const DEBUG = false;

// Store original console methods
const originalConsole = {
    log: console.log,
    error: console.error,
    warn: console.warn,
    info: console.info
};

// Function to suppress all console output
function suppressConsole() {
    console.log = function() {};
    console.error = function() {};
    console.warn = function() {};
    console.info = function() {};
}

// Function to restore original console behavior
function restoreConsole() {
    console.log = originalConsole.log;
    console.error = originalConsole.error;
    console.warn = originalConsole.warn;
    console.info = originalConsole.info;
}

// Debug logging function
function debugLog(...args) {
    if (DEBUG) {
        originalConsole.log(...args);
    }
}

// Debug error logging function
function debugError(...args) {
    if (DEBUG) {
        originalConsole.error(...args);
    }
}

// Debug warning logging function
function debugWarn(...args) {
    if (DEBUG) {
        originalConsole.warn(...args);
    }
}

// Suppress console output if not in debug mode
if (!DEBUG) {
    suppressConsole();
}