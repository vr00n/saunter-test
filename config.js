// Configuration for the application
const config = {
    // Backend URL configuration
    backend: {
        // Default to relative URL for same-origin requests
        url: '',
        // Override for specific environments
        overrides: {
            'localhost': 'http://localhost:8000',
            '127.0.0.1': 'http://localhost:8000',
            'vr00n.github.io': 'https://saunter-test.onrender.com'
        }
    }
};

// Get the current hostname
const hostname = window.location.hostname;

// Override backend URL if we have a specific configuration for this hostname
if (config.backend.overrides[hostname]) {
    config.backend.url = config.backend.overrides[hostname];
} 
