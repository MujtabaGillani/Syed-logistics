/* Shared helpers for the Syed Logistic finance / management pages.
 * Exposes a small `Finance` namespace used by the dashboard, customers,
 * vouchers and expenses pages. Kept dependency-free (only the browser fetch
 * API + Bootstrap which base.html already loads). */
(function (window) {
    'use strict';

    var API = '/api/finance/';

    function getCookie(name) {
        var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return match ? decodeURIComponent(match.pop()) : '';
    }

    function buildUrl(path, params) {
        var url = path.charAt(0) === '/' ? path : API + path;
        if (params) {
            var qs = Object.keys(params)
                .filter(function (k) { return params[k] !== '' && params[k] != null; })
                .map(function (k) {
                    return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
                })
                .join('&');
            if (qs) { url += (url.indexOf('?') === -1 ? '?' : '&') + qs; }
        }
        return url;
    }

    // Generic JSON request. `method` defaults to GET. `body` is sent as JSON.
    function request(path, options) {
        options = options || {};
        var headers = { 'X-CSRFToken': getCookie('csrftoken') };
        var init = { method: options.method || 'GET', headers: headers };

        if (options.form) {
            // FormData -> let the browser set the multipart boundary.
            init.body = options.form;
        } else if (options.body !== undefined) {
            headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(options.body);
        }

        return fetch(buildUrl(path, options.params), init).then(function (res) {
            if (res.status === 204) { return null; }
            return res.json().then(function (data) {
                if (!res.ok) {
                    var err = new Error('Request failed');
                    err.status = res.status;
                    err.data = data;
                    throw err;
                }
                return data;
            }).catch(function (e) {
                if (e.status) { throw e; }
                if (!res.ok) {
                    var err2 = new Error('Request failed');
                    err2.status = res.status;
                    throw err2;
                }
                return null;
            });
        });
    }

    // Format a number/decimal-string as Pakistani Rupees.
    function money(value) {
        var n = Number(value || 0);
        var sign = n < 0 ? '-' : '';
        return sign + 'Rs ' + Math.abs(n).toLocaleString('en-PK', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    function date(value) {
        if (!value) { return '—'; }
        var d = new Date(value);
        if (isNaN(d.getTime())) { return value; }
        return d.toLocaleDateString('en-GB', {
            year: 'numeric', month: 'short', day: '2-digit'
        });
    }

    function escapeHtml(str) {
        if (str == null) { return ''; }
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Lightweight toast (top-right). Falls back gracefully if Bootstrap toast
    // styles are unavailable.
    function toast(message, type) {
        type = type || 'success';
        var wrap = document.getElementById('fin-toast-wrap');
        if (!wrap) {
            wrap = document.createElement('div');
            wrap.id = 'fin-toast-wrap';
            wrap.style.cssText = 'position:fixed;top:20px;right:20px;z-index:2000;max-width:360px;';
            document.body.appendChild(wrap);
        }
        var el = document.createElement('div');
        var bg = type === 'danger' ? '#dc3545' : (type === 'warning' ? '#ffc107' : '#198754');
        var fg = type === 'warning' ? '#212529' : '#fff';
        el.style.cssText = 'background:' + bg + ';color:' + fg + ';padding:14px 18px;border-radius:6px;'
            + 'margin-bottom:10px;box-shadow:0 4px 12px rgba(0,0,0,.15);font-size:.95rem;';
        el.innerHTML = escapeHtml(message);
        wrap.appendChild(el);
        setTimeout(function () {
            el.style.transition = 'opacity .4s';
            el.style.opacity = '0';
            setTimeout(function () { el.remove(); }, 400);
        }, 3200);
    }

    // Turn a DRF validation error payload into a readable string.
    function errorText(err) {
        if (err && err.data) {
            if (err.data.detail) { return err.data.detail; }
            try {
                return Object.keys(err.data).map(function (k) {
                    var v = err.data[k];
                    return k + ': ' + (Array.isArray(v) ? v.join(', ') : v);
                }).join(' | ');
            } catch (e) { /* fall through */ }
        }
        return 'Something went wrong. Please try again.';
    }

    // Trigger a file download from a GET endpoint (exports).
    function download(path, params) {
        var url = buildUrl(path, params);
        var a = document.createElement('a');
        a.href = url;
        a.rel = 'noopener';
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    window.Finance = {
        API: API,
        download: download,
        get: function (path, params) { return request(path, { params: params }); },
        post: function (path, body) { return request(path, { method: 'POST', body: body }); },
        put: function (path, body) { return request(path, { method: 'PUT', body: body }); },
        patch: function (path, body) { return request(path, { method: 'PATCH', body: body }); },
        del: function (path) { return request(path, { method: 'DELETE' }); },
        postForm: function (path, form) { return request(path, { method: 'POST', form: form }); },
        putForm: function (path, form) { return request(path, { method: 'PUT', form: form }); },
        money: money,
        date: date,
        escapeHtml: escapeHtml,
        toast: toast,
        errorText: errorText,
        getCookie: getCookie
    };
})(window);
