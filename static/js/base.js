/* ==========================================================
   Connect — base.js
   Global JS for base.html (theme, dropdown, friend requests)
   ========================================================== */

// ---------- Theme toggle ----------
document.addEventListener('DOMContentLoaded', () => {
    const stored = localStorage.getItem('connect-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', stored);

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('connect-theme', next);
        });
    }

    // ---------- Profile dropdown ----------
    const avatarBtn = document.getElementById('avatarBtn');
    const dropdown = document.getElementById('dropdownMenu');
    if (avatarBtn && dropdown) {
        avatarBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('open');
        });
        document.addEventListener('click', () => dropdown.classList.remove('open'));
    }

    // ---------- Friend request buttons ----------
    // Every button with class .js-friend-action will trigger this.
    document.querySelectorAll('.js-friend-action').forEach(btn => {
        btn.addEventListener('click', async () => {
            const url = btn.dataset.url;
            const csrf = getCookie('csrftoken');
            if (!url) return;

            btn.disabled = true;
            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrf },
                });
                const data = await res.json();
                if (data.ok) {
                    // Reload to refresh the sidebar + panel
                    window.location.reload();
                } else {
                    alert(data.error || 'Action failed.');
                    btn.disabled = false;
                }
            } catch (err) {
                console.error(err);
                alert('Network error.');
                btn.disabled = false;
            }
        });
    });
});

// ---------- Cookie helper (no Django template tags) ----------
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

window.getCookie = getCookie;