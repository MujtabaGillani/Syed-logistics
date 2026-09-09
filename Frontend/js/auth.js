(function () {
    'use strict';

    const loginElement = document.getElementById('loginModal');
    const signupElement = document.getElementById('signupModal');
    if (!loginElement || !signupElement || !window.bootstrap) return;

    const loginModal = bootstrap.Modal.getInstance(loginElement) || new bootstrap.Modal(loginElement);
    const signupModal = bootstrap.Modal.getInstance(signupElement) || new bootstrap.Modal(signupElement);
    window.syedAuthInitialized = true;

    document.querySelectorAll('.js-dashboard-login').forEach(function (link) {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            loginModal.show();
        });
    });

    document.querySelectorAll('[data-auth-switch]').forEach(function (button) {
        button.addEventListener('click', function () {
            const showSignup = button.dataset.authSwitch === 'signup';
            const currentElement = showSignup ? loginElement : signupElement;
            const nextModal = showSignup ? signupModal : loginModal;
            bootstrap.Modal.getInstance(currentElement).hide();
            currentElement.addEventListener('hidden.bs.modal', function () {
                nextModal.show();
            }, { once: true });
        });
    });

    document.querySelectorAll('.password-toggle').forEach(function (button) {
        button.addEventListener('click', function () {
            const input = button.parentElement.querySelector('input');
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.setAttribute('aria-pressed', String(show));
            button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            button.querySelector('i').className = show ? 'fa fa-eye-slash' : 'fa fa-eye';
        });
    });

    function showMessage(element, message, type) {
        element.textContent = message;
        element.className = 'alert auth-message alert-' + type;
    }

    function clearErrors(form) {
        form.querySelectorAll('.is-invalid').forEach(function (field) {
            field.classList.remove('is-invalid');
        });
    }

    async function submitAuth(form, messageElement) {
        clearErrors(form);
        messageElement.classList.add('d-none');
        const submit = form.querySelector('[type="submit"]');
        const originalText = submit.textContent;
        submit.disabled = true;
        submit.textContent = 'Please wait...';

        try {
            const formData = new FormData(form);
            const payload = Object.fromEntries(formData.entries());
            delete payload.csrfmiddlewaretoken;
            const response = await fetch(form.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': formData.get('csrfmiddlewaretoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!response.ok) {
                Object.entries(data.errors || {}).forEach(function (entry) {
                    const input = form.elements[entry[0]];
                    if (!input) return;
                    input.classList.add('is-invalid');
                    const column = input.closest('.col-md-6, .col-12');
                    const feedback = column ? column.querySelector('.invalid-feedback') : null;
                    if (feedback) feedback.textContent = entry[1];
                });
                showMessage(messageElement, data.message || 'Unable to complete the request.', 'danger');
                return null;
            }
            showMessage(messageElement, data.message, 'success');
            return data;
        } catch (error) {
            showMessage(messageElement, 'The server could not be reached. Please try again.', 'danger');
            return null;
        } finally {
            submit.disabled = false;
            submit.textContent = originalText;
        }
    }

    document.getElementById('loginForm').addEventListener('submit', async function (event) {
        event.preventDefault();
        const data = await submitAuth(event.currentTarget, document.getElementById('loginMessage'));
        if (data && data.redirect) {
            const requested = new URLSearchParams(window.location.search).get('next');
            const destination = requested && requested.startsWith('/') && !requested.startsWith('//')
                ? requested : data.redirect;
            window.location.assign(destination);
        }
    });

    document.getElementById('signupForm').addEventListener('submit', async function (event) {
        event.preventDefault();
        const data = await submitAuth(event.currentTarget, document.getElementById('signupMessage'));
        if (data) event.currentTarget.reset();
    });

    if (new URLSearchParams(window.location.search).has('next')) loginModal.show();
}());
