// Theme Toggle Logic
const themeToggle = document.getElementById('theme-toggle');
const root = document.documentElement;

// Check local storage for saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
root.setAttribute('data-theme', savedTheme);

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        let currentTheme = root.getAttribute('data-theme');
        let newTheme = currentTheme === 'light' ? 'dark' : 'light';
        root.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    });
}