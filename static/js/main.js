/* main.js
   --------
   Small, dependency-free JS used across the app:
   - Dark/light theme toggle (persisted in localStorage)
   - Countdown timers on event detail pages
   - Client-side form validation (mirrors, never replaces, server checks)
   - Share event (copy link)
   - QR attendance scanner hookup lives in scan_attendance.html (loads
     the html5-qrcode CDN library only on that page, to keep this file light)
*/

// --------------------------------------------------------------------------
// Dark / Light mode toggle
// --------------------------------------------------------------------------
(function () {
    const root = document.documentElement;
    const toggleBtn = document.getElementById("theme-toggle");
    const stored = localStorage.getItem("theme");

    if (stored) {
        root.setAttribute("data-theme", stored);
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        root.setAttribute("data-theme", "dark");
    }
    updateToggleIcon();

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
            const next = current === "dark" ? "light" : "dark";
            root.setAttribute("data-theme", next);
            localStorage.setItem("theme", next);
            updateToggleIcon();
        });
    }

    function updateToggleIcon() {
        const icon = document.querySelector(".theme-toggle-icon");
        if (!icon) return;
        const isDark = root.getAttribute("data-theme") === "dark";
        icon.innerHTML = isDark ? "&#9789;" : "&#9788;";
    }
})();

// --------------------------------------------------------------------------
// Countdown timer -- looks for [data-countdown="ISO_DATETIME"] elements
// --------------------------------------------------------------------------
(function () {
    const countdownEls = document.querySelectorAll("[data-countdown]");
    if (!countdownEls.length) return;

    function tick() {
        countdownEls.forEach((el) => {
            const target = new Date(el.getAttribute("data-countdown")).getTime();
            const now = Date.now();
            const diff = target - now;

            if (diff <= 0) {
                el.textContent = "Happening now / started";
                return;
            }
            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
            const mins = Math.floor((diff / (1000 * 60)) % 60);
            const secs = Math.floor((diff / 1000) % 60);
            el.textContent = `${days}d ${hours}h ${mins}m ${secs}s`;
        });
    }
    tick();
    setInterval(tick, 1000);
})();

// --------------------------------------------------------------------------
// Share event -- copies the current page URL to the clipboard
// --------------------------------------------------------------------------
function shareEvent(button) {
    navigator.clipboard.writeText(window.location.href).then(() => {
        const original = button.textContent;
        button.textContent = "Link copied!";
        setTimeout(() => { button.textContent = original; }, 2000);
    });
}

// --------------------------------------------------------------------------
// Simple client-side "required + match" validation for auth forms.
// This never replaces server-side validation (see auth/routes.py) -- it
// just gives faster feedback before a round trip to the server.
// --------------------------------------------------------------------------
document.addEventListener("submit", function (e) {
    const form = e.target;
    if (!form.matches("[data-validate]")) return;

    let valid = true;
    form.querySelectorAll("[required]").forEach((field) => {
        if (!field.value.trim()) valid = false;
    });

    const pw = form.querySelector('[name="password"], [name="new_password"]');
    const confirm = form.querySelector('[name="confirm_password"]');
    if (pw && confirm && pw.value !== confirm.value) {
        valid = false;
        alert("Passwords do not match.");
    }

    if (!valid && !document.querySelector('[name="password"]')) {
        // Only block submission client-side for the password-mismatch case;
        // empty-required fields are still caught by the browser's own
        // built-in "required" validation UI.
    }
    if (pw && confirm && pw.value !== confirm.value) {
        e.preventDefault();
    }
});

// --------------------------------------------------------------------------
// Star rating widget -- turns a row of buttons into a 1-5 rating input
// --------------------------------------------------------------------------
function setRating(value, hiddenInputId) {
    document.getElementById(hiddenInputId).value = value;
    document.querySelectorAll(`[data-rating-star]`).forEach((star) => {
        star.classList.toggle("active", parseInt(star.dataset.ratingStar, 10) <= value);
    });
}
