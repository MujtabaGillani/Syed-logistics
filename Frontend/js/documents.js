/* Invoice & salary-slip engine for the Syed Logistic dashboard.
 *
 * Exposes `window.Docs`:
 *   - calcInvoice / calcSlip  : the same arithmetic the API applies (live preview)
 *   - render(kind, data, co)  : printable A4 HTML (.doc-page) for 'invoice' | 'salary_slip'
 *   - mountPreview(stage)     : scales the A4 page to fit its column
 *   - downloadPdf / pdfBlob   : client-side PDF of exactly what the preview shows
 *   - openShare(...)          : WhatsApp share dialog (PDF file and/or share link)
 *   - editCompany(onSaved)    : letterhead / bank details dialog
 * Requires js/finance.js (window.Finance) and Bootstrap's JS bundle. */
(function (window, document) {
    'use strict';

    var F = window.Finance;
    var H2P_URL = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js';
    var PAGE_WIDTH = 794; // A4 at 96dpi

    var PAYMENT_METHODS = {
        cash: 'Cash',
        bank: 'Bank Transfer',
        cheque: 'Cheque',
        online: 'Online (JazzCash / Easypaisa)'
    };
    var TRANSPORT_MODES = {
        road: 'Road Freight', air: 'Air Freight', sea: 'Sea Freight',
        rail: 'Rail Freight', courier: 'Courier', other: 'Other'
    };

    // ------------------------------------------------------------------ utils
    function num(v) {
        var n = parseFloat(v);
        return isFinite(n) ? n : 0;
    }

    // Round half-up to 2 places, matching Decimal.quantize(ROUND_HALF_UP).
    function round2(v) {
        var n = num(v);
        var sign = n < 0 ? -1 : 1;
        return sign * Math.round((Math.abs(n) + Number.EPSILON) * 100) / 100;
    }

    function esc(v) { return F.escapeHtml(v == null ? '' : v); }
    function nl2br(v) { return esc(v).replace(/\r?\n/g, '<br>'); }
    function money(v) { return F.money(round2(v)); }

    function parseISO(value) {
        if (!value) { return null; }
        var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
        if (!m) { return null; }
        return new Date(+m[1], +m[2] - 1, +m[3]);
    }

    function fmtDate(value) {
        var d = parseISO(value);
        if (!d) { return ''; }
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function isoDate(d) {
        var p = function (n) { return (n < 10 ? '0' : '') + n; };
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
    }

    function fmtQty(v) {
        var n = num(v);
        return n % 1 === 0 ? String(n) : n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    }

    function periodLabel(start, end) {
        var s = parseISO(start), e = parseISO(end);
        if (!s || !e) { return fmtDate(start) || fmtDate(end); }
        var lastDay = new Date(e.getFullYear(), e.getMonth() + 1, 0).getDate();
        if (s.getDate() === 1 && e.getDate() === lastDay
                && s.getMonth() === e.getMonth() && s.getFullYear() === e.getFullYear()) {
            return s.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
        }
        return fmtDate(start) + ' – ' + fmtDate(end);
    }

    // ----------------------------------------------------------- amount words
    var ONES = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten',
        'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen'];
    var TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];
    var SCALES = ['', 'Thousand', 'Million', 'Billion', 'Trillion'];

    function hundreds(n) {
        var out = [];
        if (n >= 100) { out.push(ONES[Math.floor(n / 100)] + ' Hundred'); n %= 100; }
        if (n >= 20) { out.push(TENS[Math.floor(n / 10)] + (n % 10 ? '-' + ONES[n % 10] : '')); }
        else if (n > 0) { out.push(ONES[n]); }
        return out.join(' ');
    }

    function intWords(n) {
        if (n === 0) { return 'Zero'; }
        var parts = [], i = 0;
        while (n > 0 && i < SCALES.length) {
            var chunk = n % 1000;
            if (chunk) { parts.unshift(hundreds(chunk) + (SCALES[i] ? ' ' + SCALES[i] : '')); }
            n = Math.floor(n / 1000);
            i++;
        }
        return parts.join(' ');
    }

    function amountInWords(value) {
        var n = Math.abs(round2(value));
        var rupees = Math.floor(n);
        var paisa = Math.round((n - rupees) * 100);
        var s = 'Rupees ' + intWords(rupees);
        if (paisa) { s += ' and ' + intWords(paisa) + ' Paisa'; }
        return s + ' Only';
    }

    // ------------------------------------------------------------ arithmetic
    function calcInvoice(d) {
        var subtotal = 0;
        (d.items || []).forEach(function (it) { subtotal += round2(num(it.quantity) * num(it.rate)); });
        subtotal = round2(subtotal);
        var taxable = subtotal - round2(d.discount) + round2(d.other_charges);
        var tax = round2(taxable * num(d.tax_percent) / 100);
        var total = round2(taxable + tax);
        var paid = round2(round2(d.advance_amount) + round2(d.amount_received));
        var balance = round2(total - paid);
        var status = (total > 0 && balance <= 0) ? 'paid' : (paid > 0 ? 'partial' : 'unpaid');
        return { subtotal: subtotal, tax_amount: tax, total_amount: total,
                 amount_paid: paid, balance_due: balance, payment_status: status };
    }

    function calcSlip(d) {
        var earn = 0, ded = 0;
        (d.lines || []).forEach(function (l) {
            if (l.kind === 'earning') { earn += round2(l.amount); } else { ded += round2(l.amount); }
        });
        var gross = round2(round2(d.basic_salary) + earn);
        var tax = num(d.tax_percent) > 0 ? round2(gross * num(d.tax_percent) / 100) : round2(d.tax_amount);
        var totalDed = round2(tax + ded);
        return { gross_earnings: gross, tax_amount: tax, total_deductions: totalDed,
                 net_pay: round2(gross - totalDed) };
    }

    // -------------------------------------------------------------- rendering
    var logoUrl = '/static/img/logo.svg';

    function brandName(name) {
        name = String(name || 'Syed Logistic').trim();
        var i = name.lastIndexOf(' ');
        if (i < 1) { return esc(name); }
        return esc(name.slice(0, i)) + ' <span>' + esc(name.slice(i + 1)) + '</span>';
    }

    // Letterhead used for a document: its own saved snapshot, else the company
    // passed in (e.g. the default company for older documents).
    function resolveCompany(data, company) {
        var snap = data && data.company_details;
        return (snap && snap.name) ? snap : (company || {});
    }

    // Snapshots carry `logo` ('' = no logo); API company objects carry
    // `logo_url`; anything older falls back to the website logo.
    function companyLogo(co) {
        if ('logo' in co) { return co.logo || ''; }
        if ('logo_url' in co) { return co.logo_url || ''; }
        return logoUrl;
    }

    function letterhead(co, title, metaRows, stamp) {
        var contact = [co.phone, co.email].filter(Boolean).map(esc).join(' &nbsp;·&nbsp; ');
        var tax = [co.ntn ? 'NTN: ' + esc(co.ntn) : '', co.strn ? 'STRN: ' + esc(co.strn) : '']
            .filter(Boolean).join(' &nbsp;·&nbsp; ');
        return '<div class="doc-head">'
            + '<div class="doc-brand">' + (companyLogo(co) ? '<img src="' + esc(companyLogo(co)) + '" alt="">' : '')
            + '<div><div class="doc-brand-name">' + brandName(co.name) + '</div>'
            + (co.tagline ? '<div class="doc-brand-tag">' + esc(co.tagline) + '</div>' : '')
            + '<div class="doc-brand-meta">'
            + (co.address ? esc(co.address) + '<br>' : '')
            + (contact ? contact + '<br>' : '')
            + (co.website ? esc(co.website) + '<br>' : '')
            + tax + '</div></div></div>'
            + '<div class="doc-title-block"><div class="doc-title">' + esc(title) + '</div>'
            + '<table class="doc-meta">' + metaRows.filter(function (r) { return r[1]; }).map(function (r) {
                return '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>';
            }).join('') + '</table>'
            + (stamp ? '<span class="doc-stamp ' + esc(stamp[0]) + '">' + esc(stamp[1]) + '</span>' : '')
            + '</div></div>';
    }

    function gridCells(cells, cls) {
        cells = cells.filter(function (c) { return c[1] !== '' && c[1] != null; });
        if (!cells.length) { return ''; }
        return '<div class="doc-grid ' + (cls || '') + '">' + cells.map(function (c) {
            return '<div><small>' + esc(c[0]) + '</small><b>' + esc(c[1]) + '</b></div>';
        }).join('') + '</div>';
    }

    function kvTable(rows) {
        rows = rows.filter(function (r) { return r[1]; });
        if (!rows.length) { return ''; }
        return '<table class="doc-kv">' + rows.map(function (r) {
            return '<tr><td>' + esc(r[0]) + '</td><td>' + esc(r[1]) + '</td></tr>';
        }).join('') + '</table>';
    }

    function footer(co, text) {
        var bits = [co.phone, co.email, co.website].filter(Boolean).map(esc).join(' &nbsp;·&nbsp; ');
        return '<div class="doc-foot"><span>' + esc(text) + '</span><span>' + bits + '</span></div>';
    }

    function renderInvoice(d, co) {
        var t = calcInvoice(d);
        var statusLabel = { paid: 'Paid', partial: 'Partially paid', unpaid: 'Unpaid' }[t.payment_status];

        var head = letterhead(co, 'INVOICE', [
            ['Invoice No.', d.invoice_number || 'Draft'],
            ['Invoice Date', fmtDate(d.invoice_date)],
            ['Due Date', fmtDate(d.due_date)],
            ['Reference', d.reference_number]
        ], [t.payment_status, statusLabel]);

        var billLines = [d.bill_to_company, d.bill_to_phone ? 'Phone: ' + d.bill_to_phone : '',
            d.bill_to_email, d.bill_to_cnic ? 'CNIC / NTN: ' + d.bill_to_cnic : ''].filter(Boolean);
        var bill = '<div class="doc-box"><div class="doc-box-title">Bill To</div>'
            + '<div class="doc-box-name">' + (esc(d.bill_to_name) || '&mdash;') + '</div>'
            + billLines.map(function (l) { return '<div class="doc-box-line">' + esc(l) + '</div>'; }).join('')
            + (d.bill_to_address ? '<div class="doc-box-line">' + nl2br(d.bill_to_address) + '</div>' : '')
            + '</div>';
        var hasShip = d.ship_to_name || d.ship_to_address || d.ship_to_phone;
        var ship = '<div class="doc-box"><div class="doc-box-title">Ship To / Consignee</div>'
            + (hasShip
                ? '<div class="doc-box-name">' + (esc(d.ship_to_name) || esc(d.bill_to_name)) + '</div>'
                  + (d.ship_to_phone ? '<div class="doc-box-line">Phone: ' + esc(d.ship_to_phone) + '</div>' : '')
                  + (d.ship_to_address ? '<div class="doc-box-line">' + nl2br(d.ship_to_address) + '</div>' : '')
                : '<div class="doc-box-line">Same as billing address</div>')
            + '</div>';

        var route = (d.origin || d.destination)
            ? (d.origin || '—') + '  →  ' + (d.destination || '—') : '';
        var shipment = gridCells([
            ['Bilty / AWB / CN No.', d.tracking_number],
            ['Mode', TRANSPORT_MODES[d.transport_mode] || ''],
            ['Service', d.service_type],
            ['Route', route],
            ['Vehicle / Container', d.vehicle_number],
            ['Packages', d.packages ? fmtQty(d.packages) : ''],
            ['Weight', num(d.total_weight_kg) ? fmtQty(d.total_weight_kg) + ' kg' : ''],
            ['Volume', num(d.volume_cbm) ? fmtQty(d.volume_cbm) + ' CBM' : ''],
            ['Pickup Date', fmtDate(d.pickup_date)],
            ['Delivery Date', fmtDate(d.delivery_date)]
        ]);

        var items = (d.items || []).filter(function (it) { return it.description || num(it.rate); });
        var hasWeight = items.some(function (it) { return num(it.weight_kg); });
        var rows = items.map(function (it, i) {
            return '<tr><td>' + (i + 1) + '</td><td>' + esc(it.description) + '</td>'
                + (hasWeight ? '<td class="num">' + (num(it.weight_kg) ? fmtQty(it.weight_kg) : '') + '</td>' : '')
                + '<td class="num">' + fmtQty(it.quantity) + (it.unit ? ' ' + esc(it.unit) : '') + '</td>'
                + '<td class="num">' + money(it.rate) + '</td>'
                + '<td class="num">' + money(num(it.quantity) * num(it.rate)) + '</td></tr>';
        }).join('') || '<tr><td colspan="' + (hasWeight ? 6 : 5) + '" style="text-align:center;color:#9AA5B1">No items yet</td></tr>';
        var table = '<table class="doc-table"><thead><tr><th style="width:30px">#</th><th>Description</th>'
            + (hasWeight ? '<th class="num">Weight (kg)</th>' : '')
            + '<th class="num">Qty</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>'
            + '<tbody>' + rows + '</tbody>'
            + '<tfoot><tr><td colspan="' + (hasWeight ? 5 : 4) + '">Subtotal</td><td class="num">'
            + money(t.subtotal) + '</td></tr></tfoot></table>';

        // Totals + payment schedule (advance date, agreed date for the rest).
        var tr = function (label, value, cls, sub) {
            return '<tr' + (cls ? ' class="' + cls + '"' : '') + '><td>' + esc(label)
                + (sub ? '<small>' + esc(sub) + '</small>' : '') + '</td><td>' + value + '</td></tr>';
        };
        var totals = '<table class="doc-totals">'
            + tr('Subtotal', money(t.subtotal))
            + (num(d.discount) ? tr('Discount', '- ' + money(d.discount)) : '')
            + (num(d.other_charges) ? tr(d.other_charges_label || 'Other charges', money(d.other_charges)) : '')
            + (num(d.tax_percent) ? tr('Tax (' + fmtQty(d.tax_percent) + '%)', money(t.tax_amount)) : '')
            + tr('Total Amount', money(t.total_amount), 'grand')
            + (num(d.advance_amount) ? tr('Advance Paid', money(d.advance_amount), 'paid',
                d.advance_date ? 'on ' + fmtDate(d.advance_date) : '') : '')
            + (num(d.amount_received) ? tr('Amount Received', money(d.amount_received), 'paid',
                d.received_date ? 'on ' + fmtDate(d.received_date) : '') : '')
            + tr('Balance Due', money(t.balance_due), 'balance',
                t.balance_due > 0 && d.balance_due_date ? 'to be paid by ' + fmtDate(d.balance_due_date) : '')
            + '</table>';

        var schedule = [];
        if (num(d.advance_amount)) {
            schedule.push('<div>&#10003; Advance of <b>' + money(d.advance_amount) + '</b> received'
                + (d.advance_date ? ' on <b>' + esc(fmtDate(d.advance_date)) + '</b>' : '') + '.</div>');
        }
        if (num(d.amount_received)) {
            schedule.push('<div>&#10003; Payment of <b>' + money(d.amount_received) + '</b> received'
                + (d.received_date ? ' on <b>' + esc(fmtDate(d.received_date)) + '</b>' : '') + '.</div>');
        }
        if (t.balance_due > 0 && (schedule.length || d.balance_due_date)) {
            schedule.push('<div>&#9203; Remaining <b>' + money(t.balance_due) + '</b> '
                + (d.balance_due_date ? 'to be paid by <b>' + esc(fmtDate(d.balance_due_date)) + '</b> (as agreed).'
                                      : 'is pending.') + '</div>');
        } else if (t.payment_status === 'paid') {
            schedule.push('<div>&#10003; Paid in full. Thank you!</div>');
        }
        var scheduleHtml = schedule.length
            ? '<div class="doc-schedule"><div class="doc-section-title">Payment schedule</div>' + schedule.join('') + '</div>'
            : '';

        var paymentKv = kvTable([
            ['Payment method', PAYMENT_METHODS[d.payment_method] || ''],
            ['Bank', d.payment_bank_name],
            ['Account title', d.payment_account_title],
            ['Account / IBAN', d.payment_account_number],
            ['Transaction ID', d.transaction_reference]
        ]);
        var bankKv = kvTable([
            ['Bank', co.bank_name],
            ['Account title', co.bank_account_title],
            ['Account no.', co.bank_account_number],
            ['IBAN', co.bank_iban]
        ]);
        var left = '<div class="doc-stack">'
            + '<div><div class="doc-section-title">Amount in words</div><div class="doc-words">'
            + esc(amountInWords(t.total_amount)) + '</div></div>'
            + (paymentKv ? '<div><div class="doc-section-title">Payment details</div>' + paymentKv + '</div>' : '')
            + (bankKv ? '<div><div class="doc-section-title">Pay to (our bank details)</div>' + bankKv + '</div>' : '')
            + (d.notes ? '<div><div class="doc-section-title">Notes</div><div class="doc-note">' + nl2br(d.notes) + '</div></div>' : '')
            + (d.terms ? '<div><div class="doc-section-title">Terms &amp; conditions</div><div class="doc-note">' + nl2br(d.terms) + '</div></div>' : '')
            + '</div>';

        return '<div class="doc-page"><div class="doc-topbar"></div><div class="doc-body">'
            + head + '<div class="doc-rule"></div>'
            + '<div class="doc-parties">' + bill + ship + '</div>'
            + shipment + table
            + '<div class="doc-bottom">' + left + '<div class="doc-avoid">' + totals + scheduleHtml + '</div></div>'
            + '<div class="doc-sign"><div>Customer signature</div><div>For ' + esc(co.name || 'Syed Logistic')
            + ' &mdash; Authorised signature</div></div>'
            + '</div>' + footer(co, 'This is a computer-generated invoice.') + '</div>';
    }

    function renderSlip(d, co) {
        var t = calcSlip(d);
        var paid = d.payment_status !== 'pending';
        var head = letterhead(co, 'SALARY SLIP', [
            ['Slip No.', d.slip_number || 'Draft'],
            ['Pay Period', periodLabel(d.pay_period_start, d.pay_period_end)],
            ['Pay Date', fmtDate(d.pay_date)]
        ], paid ? ['paid', 'Paid'] : ['pending', 'Pending']);

        var employee = gridCells([
            ['Employee Name', d.employee_name || '—'],
            ['Employee Code', d.employee_code],
            ['Designation', d.designation],
            ['Department', d.department],
            ['CNIC', d.cnic],
            ['Phone', d.phone_number],
            ['Email', d.email],
            ['Joining Date', fmtDate(d.joining_date)],
            ['Address', d.address]
        ], 'tight');
        var period = gridCells([
            ['Period', fmtDate(d.pay_period_start) + ' – ' + fmtDate(d.pay_period_end)],
            ['Working Days', d.working_days != null && d.working_days !== '' ? fmtQty(d.working_days) : ''],
            ['Days Present', d.days_present != null && d.days_present !== '' ? fmtQty(d.days_present) : ''],
            ['Leaves', d.leaves != null && d.leaves !== '' ? fmtQty(d.leaves) : '']
        ]);

        var row = function (label, value) {
            return '<tr><td>' + esc(label) + '</td><td class="num">' + money(value) + '</td></tr>';
        };
        var earnings = row('Basic Salary', d.basic_salary);
        var deductions = t.tax_amount
            ? row('Income Tax' + (num(d.tax_percent) ? ' (' + fmtQty(d.tax_percent) + '%)' : ''), t.tax_amount) : '';
        (d.lines || []).forEach(function (l) {
            if (!l.label && !num(l.amount)) { return; }
            if (l.kind === 'earning') { earnings += row(l.label || 'Allowance', l.amount); }
            else { deductions += row(l.label || 'Deduction', l.amount); }
        });
        if (!deductions) { deductions = '<tr><td colspan="2" style="color:#9AA5B1">No deductions</td></tr>'; }

        var pay = '<div class="doc-pay">'
            + '<table class="doc-table"><thead><tr><th>Earnings</th><th class="num">Amount</th></tr></thead>'
            + '<tbody>' + earnings + '</tbody><tfoot><tr><td>Gross Earnings</td><td class="num">'
            + money(t.gross_earnings) + '</td></tr></tfoot></table>'
            + '<table class="doc-table"><thead><tr><th>Deductions</th><th class="num">Amount</th></tr></thead>'
            + '<tbody>' + deductions + '</tbody><tfoot><tr><td>Total Deductions</td><td class="num">'
            + money(t.total_deductions) + '</td></tr></tfoot></table></div>';

        var net = '<div class="doc-net doc-avoid"><div><small>Net Pay</small><strong>' + money(t.net_pay)
            + '</strong></div><div class="doc-net-words">' + esc(amountInWords(t.net_pay)) + '</div></div>';

        var paymentKv = kvTable([
            ['Status', paid ? 'Paid' : 'Pending'],
            ['Payment method', PAYMENT_METHODS[d.payment_method] || ''],
            ['Bank', d.bank_name],
            ['Account title', d.bank_account_title],
            ['Account / IBAN', d.bank_account_number],
            ['Transaction ID', d.transaction_id],
            ['Paid on', paid ? fmtDate(d.pay_date) : '']
        ]);

        return '<div class="doc-page"><div class="doc-topbar"></div><div class="doc-body">'
            + head + '<div class="doc-rule"></div>'
            + '<div class="doc-section-title">Employee details</div>' + employee + period
            + pay + net
            + '<div class="doc-bottom" style="grid-template-columns:1fr 1fr">'
            + '<div><div class="doc-section-title">Payment details</div>' + paymentKv + '</div>'
            + '<div>' + (d.notes ? '<div class="doc-section-title">Notes</div><div class="doc-note">' + nl2br(d.notes) + '</div>' : '') + '</div>'
            + '</div>'
            + '<div class="doc-sign"><div>Employee signature</div><div>For ' + esc(co.name || 'Syed Logistic')
            + ' &mdash; Authorised signature</div></div>'
            + '</div>' + footer(co, 'This is a computer-generated salary slip.') + '</div>';
    }

    function render(kind, data, company) {
        var co = resolveCompany(data, company);
        return kind === 'invoice' ? renderInvoice(data, co) : renderSlip(data, co);
    }

    // ------------------------------------------------------- preview scaling
    function mountPreview(stage) {
        var inner = document.createElement('div');
        inner.className = 'doc-scale';
        stage.innerHTML = '';
        stage.appendChild(inner);
        function fit() {
            var scale = Math.min(1, stage.clientWidth / PAGE_WIDTH) || 1;
            inner.style.transform = 'scale(' + scale + ')';
            stage.style.height = Math.ceil(inner.offsetHeight * scale) + 'px';
        }
        if (window.ResizeObserver) {
            var ro = new ResizeObserver(fit);
            ro.observe(stage);
            ro.observe(inner);
        } else {
            window.addEventListener('resize', fit);
        }
        return {
            update: function (html) { inner.innerHTML = html; fit(); },
            fit: fit
        };
    }

    // ------------------------------------------------------------------- PDF
    var libPromise = null;
    function loadPdfLib() {
        if (window.html2pdf) { return Promise.resolve(window.html2pdf); }
        if (!libPromise) {
            libPromise = new Promise(function (resolve, reject) {
                var s = document.createElement('script');
                s.src = H2P_URL;
                s.onload = function () { resolve(window.html2pdf); };
                s.onerror = function () { libPromise = null; reject(new Error('Could not load the PDF library.')); };
                document.head.appendChild(s);
            });
        }
        return libPromise;
    }

    function filename(kind, data) {
        var raw = kind === 'invoice'
            ? 'Invoice-' + (data.invoice_number || 'draft') + '-' + (data.bill_to_name || '')
            : 'Salary-Slip-' + (data.slip_number || 'draft') + '-' + (data.employee_name || '');
        return raw.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/-+$/, '') + '.pdf';
    }

    // html2pdf's worker is itself a thenable, so it must not be returned from a
    // .then() (the promise would adopt it) - `finish` runs save()/outputPdf().
    function withWorker(kind, data, company, finish) {
        return loadPdfLib().then(function (html2pdf) {
            return finish(html2pdf().set({
                margin: 0,
                filename: filename(kind, data),
                image: { type: 'jpeg', quality: 0.96 },
                html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff', scrollX: 0, scrollY: 0 },
                jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
                pagebreak: { mode: ['css', 'legacy'], avoid: ['tr', '.doc-avoid', '.doc-sign'] }
            }).from(render(kind, data, company), 'string'));
        });
    }

    function downloadPdf(kind, data, company) {
        return withWorker(kind, data, company, function (w) { return w.save(); });
    }

    function pdfBlob(kind, data, company) {
        return withWorker(kind, data, company, function (w) { return w.outputPdf('blob'); });
    }

    // -------------------------------------------------------------- WhatsApp
    // Pakistani numbers: 0300-1234567 / 3001234567 / +92 300 1234567 -> 923001234567
    function waPhone(phone) {
        var d = String(phone || '').replace(/\D/g, '');
        if (!d) { return ''; }
        if (d.indexOf('00') === 0) { d = d.slice(2); }
        if (d.charAt(0) === '0') { d = '92' + d.slice(1); }
        else if (d.length === 10 && d.charAt(0) === '3') { d = '92' + d; }
        return d;
    }

    function shareLink(kind, data) {
        if (!data || !data.share_token) { return ''; }
        return window.location.origin + (kind === 'invoice' ? '/share/invoice/' : '/share/salary-slip/')
            + data.share_token + '/';
    }

    function defaultMessage(kind, data, company) {
        var co = resolveCompany(data, company).name || 'Syed Logistic';
        var link = shareLink(kind, data);
        var lines;
        if (kind === 'invoice') {
            var t = calcInvoice(data);
            lines = ['Dear ' + (data.bill_to_name || 'Customer') + ',', '',
                'Please find your invoice ' + (data.invoice_number || '') + ' from ' + co + '.',
                'Invoice date: ' + fmtDate(data.invoice_date),
                'Total amount: ' + money(t.total_amount)];
            if (num(data.advance_amount)) {
                lines.push('Advance paid: ' + money(data.advance_amount)
                    + (data.advance_date ? ' (' + fmtDate(data.advance_date) + ')' : ''));
            }
            if (num(data.amount_received)) {
                lines.push('Amount received: ' + money(data.amount_received)
                    + (data.received_date ? ' (' + fmtDate(data.received_date) + ')' : ''));
            }
            lines.push(t.balance_due > 0
                ? 'Balance due: ' + money(t.balance_due)
                    + (data.balance_due_date ? ' - to be paid by ' + fmtDate(data.balance_due_date) : '')
                : 'Status: Paid in full');
        } else {
            var s = calcSlip(data);
            lines = ['Dear ' + (data.employee_name || '') + ',', '',
                'Your salary slip ' + (data.slip_number || '') + ' for '
                    + periodLabel(data.pay_period_start, data.pay_period_end) + ' from ' + co + '.',
                'Net pay: ' + money(s.net_pay),
                (data.payment_status === 'pending' ? 'Status: Pending' :
                    'Paid via ' + (PAYMENT_METHODS[data.payment_method] || 'cash')
                    + (data.transaction_id ? ' (Txn: ' + data.transaction_id + ')' : ''))];
        }
        if (link) { lines.push('', 'Download PDF: ' + link + '?download=1'); }
        lines.push('', 'Thank you,', co);
        return lines.join('\n');
    }

    // Bootstrap 5.0.0 (loaded by base.html) has no Modal.getOrCreateInstance.
    function modalFor(el) {
        return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
    }

    var shareModalEl = null;
    function ensureShareModal() {
        if (shareModalEl) { return shareModalEl; }
        var wrap = document.createElement('div');
        wrap.innerHTML =
            '<div class="modal fade" id="docShareModal" tabindex="-1" aria-hidden="true">'
            + '<div class="modal-dialog modal-dialog-centered"><div class="modal-content">'
            + '<div class="modal-header"><h5 class="modal-title"><i class="fab fa-whatsapp text-success me-2"></i>Share on WhatsApp</h5>'
            + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
            + '<div class="modal-body">'
            + '<label class="form-label" for="docSharePhone">WhatsApp number</label>'
            + '<input class="form-control mb-1" id="docSharePhone" placeholder="0300 1234567">'
            + '<div class="form-text mb-3">Leave empty to pick the contact inside WhatsApp.</div>'
            + '<label class="form-label" for="docShareMsg">Message</label>'
            + '<textarea class="form-control" id="docShareMsg" rows="9"></textarea>'
            + '<div class="small mt-2 text-muted" id="docShareStatus"></div>'
            + '</div>'
            + '<div class="modal-footer flex-column align-items-stretch gap-2">'
            + '<button type="button" class="btn btn-whatsapp" id="docShareFile"><i class="fa fa-file-pdf me-2"></i>Send PDF file to WhatsApp</button>'
            + '<button type="button" class="btn btn-outline-success" id="docShareChat"><i class="fab fa-whatsapp me-2"></i>Open WhatsApp chat with PDF link</button>'
            + '</div></div></div></div>';
        shareModalEl = wrap.firstChild;
        document.body.appendChild(shareModalEl);
        return shareModalEl;
    }

    function canShareFiles() {
        try {
            return !!(navigator.canShare && navigator.share
                && navigator.canShare({ files: [new File(['x'], 'x.pdf', { type: 'application/pdf' })] }));
        } catch (e) { return false; }
    }

    function saveBlob(blob, name) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    }

    /* opts: {kind, data, company, phone}. The PDF is generated as soon as the
     * dialog opens so the share button (a fresh click = user gesture) can hand
     * the file to the OS share sheet immediately. */
    function openShare(opts) {
        var el = ensureShareModal();
        var modal = modalFor(el);
        var phoneEl = el.querySelector('#docSharePhone');
        var msgEl = el.querySelector('#docShareMsg');
        var statusEl = el.querySelector('#docShareStatus');
        var fileBtn = el.querySelector('#docShareFile');
        var chatBtn = el.querySelector('#docShareChat');
        var name = filename(opts.kind, opts.data);

        phoneEl.value = opts.phone || '';
        msgEl.value = defaultMessage(opts.kind, opts.data, opts.company);
        var fileSharing = canShareFiles();
        fileBtn.style.display = fileSharing ? '' : 'none';
        fileBtn.disabled = true;
        statusEl.textContent = 'Preparing PDF…';

        var blobReady = pdfBlob(opts.kind, opts.data, opts.company).then(function (blob) {
            fileBtn.disabled = false;
            statusEl.textContent = 'PDF ready (' + Math.max(1, Math.round(blob.size / 1024)) + ' KB). '
                + (fileSharing
                    ? '"Send PDF file" attaches it directly - choose WhatsApp in the share menu.'
                    : 'This browser cannot attach files to WhatsApp directly: the chat opens with a download link for the customer and the PDF is saved on this device so you can attach it too.');
            return blob;
        }).catch(function (err) {
            statusEl.textContent = (err && err.message) || 'Could not create the PDF.';
            throw err;
        });

        fileBtn.onclick = function () {
            blobReady.then(function (blob) {
                var file = new File([blob], name, { type: 'application/pdf' });
                return navigator.share({ files: [file], title: name, text: msgEl.value });
            }).then(function () { modal.hide(); }).catch(function (err) {
                if (err && err.name === 'AbortError') { return; }
                statusEl.textContent = 'Direct file sharing is not available here - use "Open WhatsApp chat" instead.';
            });
        };
        chatBtn.onclick = function () {
            var phone = waPhone(phoneEl.value);
            window.open('https://wa.me/' + phone + '?text=' + encodeURIComponent(msgEl.value), '_blank', 'noopener');
            blobReady.then(function (blob) {
                saveBlob(blob, name);
                F.toast('PDF downloaded - attach it in the WhatsApp chat if needed.');
            }).catch(function () { /* status already shown */ });
            modal.hide();
        };
        modal.show();
    }

    // ------------------------------------------------------- company profile
    var companyCache = null;
    function loadCompany() {
        if (companyCache) { return Promise.resolve(companyCache); }
        return F.get('company-profile/').then(function (c) { companyCache = c || {}; return companyCache; });
    }

    var COMPANY_FIELDS = [
        ['name', 'Company name', 'col-md-6'], ['tagline', 'Tagline', 'col-md-6'],
        ['address', 'Address', 'col-12'],
        ['phone', 'Phone', 'col-md-4'], ['email', 'Email', 'col-md-4'], ['website', 'Website', 'col-md-4'],
        ['ntn', 'NTN', 'col-md-6'], ['strn', 'STRN', 'col-md-6'],
        ['bank_name', 'Bank name', 'col-md-6'], ['bank_account_title', 'Account title', 'col-md-6'],
        ['bank_account_number', 'Account number', 'col-md-6'], ['bank_iban', 'IBAN', 'col-md-6'],
        ['invoice_notes', 'Default invoice notes', 'col-12', 'textarea'],
        ['invoice_terms', 'Default terms & conditions', 'col-12', 'textarea']
    ];

    var companyModalEl = null;
    function editCompany(onSaved) {
        if (!companyModalEl) {
            var wrap = document.createElement('div');
            wrap.innerHTML = '<div class="modal fade" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">'
                + '<div class="modal-content"><form>'
                + '<div class="modal-header"><h5 class="modal-title"><i class="fa fa-building me-2"></i>Company details</h5>'
                + '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>'
                + '<div class="modal-body"><p class="text-muted small">Printed on the letterhead of every invoice and salary slip. Bank details appear on invoices as &ldquo;Pay to&rdquo;.</p><div class="row g-3">'
                + COMPANY_FIELDS.map(function (f) {
                    var input = f[3] === 'textarea'
                        ? '<textarea class="form-control" rows="3" name="' + f[0] + '"></textarea>'
                        : '<input class="form-control" name="' + f[0] + '"' + (f[0] === 'name' ? ' required' : '') + '>';
                    return '<div class="' + f[2] + '"><label class="form-label">' + f[1] + '</label>' + input + '</div>';
                }).join('')
                + '</div></div><div class="modal-footer"><button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>'
                + '<button type="submit" class="btn btn-primary">Save details</button></div></form></div></div></div>';
            companyModalEl = wrap.firstChild;
            document.body.appendChild(companyModalEl);
        }
        var form = companyModalEl.querySelector('form');
        var modal = modalFor(companyModalEl);
        loadCompany().then(function (c) {
            COMPANY_FIELDS.forEach(function (f) { form.elements[f[0]].value = c[f[0]] || ''; });
            modal.show();
        }).catch(function (err) { F.toast(F.errorText(err), 'danger'); });
        form.onsubmit = function (ev) {
            ev.preventDefault();
            var payload = {};
            COMPANY_FIELDS.forEach(function (f) { payload[f[0]] = form.elements[f[0]].value.trim(); });
            F.put('company-profile/', payload).then(function (c) {
                companyCache = c;
                modal.hide();
                F.toast('Company details saved.');
                if (onSaved) { onSaved(c); }
            }).catch(function (err) { F.toast(F.errorText(err), 'danger'); });
        };
    }

    // -------------------------------------------------- company / letterhead
    var DETAIL_FIELDS = [
        ['name', 'Company name *', 'col-md-6'], ['tagline', 'Tagline', 'col-md-6'],
        ['address', 'Address', 'col-12'],
        ['phone', 'Phone', 'col-md-4'], ['email', 'Email', 'col-md-4'], ['website', 'Website', 'col-md-4'],
        ['ntn', 'NTN', 'col-md-6'], ['strn', 'STRN', 'col-md-6']
    ];
    var BANK_FIELDS = [
        ['bank_name', 'Bank name', 'col-md-6'], ['bank_account_title', 'Account title', 'col-md-6'],
        ['bank_account_number', 'Account number', 'col-md-6'], ['bank_iban', 'IBAN', 'col-md-6']
    ];
    var ALL_DETAIL_KEYS = DETAIL_FIELDS.concat(BANK_FIELDS).map(function (f) { return f[0]; });

    function snapshotOf(company) {
        var d = {};
        ALL_DETAIL_KEYS.forEach(function (k) { d[k] = (company && company[k]) || ''; });
        d.logo = (company && company.logo_url) || '';
        return d;
    }

    /* Company picker + editable letterhead for the invoice / salary-slip forms.
     * opts: { showBank: bool, onChange(), onSwitch(prevCompany, nextCompany) }
     * The edited details are saved on the document itself; "Save to company"
     * also stores them on the company for future documents. */
    function companyPanel(root, opts) {
        opts = opts || {};
        var companies = [];
        var current = null;      // selected company object (null = new, unsaved)
        var logo = '';
        var fieldHtml = function (f) {
            return '<div class="' + f[2] + '"><label class="form-label">' + esc(f[1]) + '</label>'
                + '<input class="form-control" data-co="' + f[0] + '"></div>';
        };
        root.innerHTML = '<div class="doc-form-section doc-company">'
            + '<h6><span><i class="fa fa-building"></i>Company / letterhead</span>'
            + '<button type="button" class="btn btn-sm btn-outline-primary" data-act="new"><i class="fa fa-plus me-1"></i>New company</button></h6>'
            + '<div class="row g-3 align-items-end">'
            + '<div class="col-md-7"><label class="form-label">Issue as</label><select class="form-select" data-co-select></select></div>'
            + '<div class="col-md-5 d-flex gap-2">'
            + '<button type="button" class="btn btn-outline-primary flex-grow-1" data-act="save"><i class="fa fa-save me-1"></i>Save to company</button>'
            + '<button type="button" class="btn btn-outline-secondary" data-act="default" title="Make this the default company"><i class="fa fa-star"></i></button>'
            + '</div>'
            + '<div class="col-12"><div class="doc-logo-row">'
            + '<div class="doc-logo-box"><img data-co-logo alt="Logo"><span data-co-nologo>No logo</span></div>'
            + '<div><div class="d-flex flex-wrap gap-2">'
            + '<button type="button" class="btn btn-sm btn-outline-secondary" data-act="upload"><i class="fa fa-upload me-1"></i>Upload logo</button>'
            + '<button type="button" class="btn btn-sm btn-outline-danger" data-act="remove-logo"><i class="fa fa-times me-1"></i>Remove logo</button>'
            + '<button type="button" class="btn btn-sm btn-outline-secondary" data-act="toggle"><i class="fa fa-pen me-1"></i>Edit details</button>'
            + '</div><div class="form-text">PNG, JPG or WebP up to 2 MB. An uploaded logo is saved to the company.</div></div>'
            + '<input type="file" accept="image/png,image/jpeg,image/webp" data-co-file hidden>'
            + '</div></div>'
            + '<div class="col-12 doc-company-fields" data-co-fields hidden><div class="row g-3">'
            + DETAIL_FIELDS.map(fieldHtml).join('')
            + (opts.showBank
                ? '<div class="col-12"><div class="doc-subhead">Bank details (printed as &ldquo;Pay to&rdquo;)</div></div>'
                  + BANK_FIELDS.map(fieldHtml).join('')
                : BANK_FIELDS.map(function (f) { return '<input type="hidden" data-co="' + f[0] + '">'; }).join(''))
            + '</div></div>'
            + '<div class="col-12"><div class="doc-company-status" data-co-status></div></div>'
            + '</div></div>';

        var q = function (sel) { return root.querySelector(sel); };
        var select = q('[data-co-select]');
        var fileInput = q('[data-co-file]');
        var inputs = {};
        Array.prototype.forEach.call(root.querySelectorAll('[data-co]'), function (el) {
            inputs[el.getAttribute('data-co')] = el;
        });

        function changed() { status(); if (opts.onChange) { opts.onChange(); } }

        function details() {
            var d = {};
            ALL_DETAIL_KEYS.forEach(function (k) { d[k] = inputs[k].value.trim(); });
            d.logo = logo;
            return d;
        }

        function isDirty() {
            if (!current) { return true; }
            var saved = snapshotOf(current), now = details();
            return Object.keys(saved).some(function (k) { return (saved[k] || '') !== (now[k] || ''); });
        }

        function status() {
            var el = q('[data-co-status]');
            var name = inputs.name.value.trim() || 'Unnamed company';
            q('[data-act="default"]').style.display = current && !current.is_default ? '' : 'none';
            if (!current) {
                el.innerHTML = '<i class="fa fa-info-circle me-1"></i>New company <b>' + esc(name)
                    + '</b> - click <b>Save to company</b> to keep it for future documents.';
            } else if (isDirty()) {
                el.innerHTML = '<i class="fa fa-pen me-1"></i>Edited for this document only - click <b>Save to company</b> to update <b>'
                    + esc(current.name) + '</b> for future documents too.';
            } else {
                el.innerHTML = '<i class="fa fa-check-circle text-success me-1"></i><b>' + esc(current.name) + '</b>'
                    + (current.is_default ? ' (default company)' : '') + ' · ' + esc([current.phone, current.email].filter(Boolean).join(' · '));
            }
        }

        function showLogo() {
            var img = q('[data-co-logo]');
            img.style.display = logo ? '' : 'none';
            if (logo) { img.src = logo; }
            q('[data-co-nologo]').style.display = logo ? 'none' : '';
            q('[data-act="remove-logo"]').disabled = !logo;
        }

        function fill(d) {
            ALL_DETAIL_KEYS.forEach(function (k) { inputs[k].value = d[k] || ''; });
            logo = d.logo || '';
            showLogo();
        }

        function renderOptions() {
            select.innerHTML = companies.map(function (c) {
                return '<option value="' + c.id + '">' + esc(c.name) + (c.is_default ? ' (default)' : '') + '</option>';
            }).join('') + (current ? '' : '<option value="">New company (not saved yet)</option>');
            select.value = current ? String(current.id) : '';
        }

        function byId(id) {
            return companies.filter(function (c) { return String(c.id) === String(id); })[0] || null;
        }

        function upsert(c) {
            var i = companies.map(function (x) { return x.id; }).indexOf(c.id);
            if (i === -1) { companies.push(c); } else { companies[i] = c; }
            if (c.is_default) {
                companies.forEach(function (x) { if (x.id !== c.id) { x.is_default = false; } });
            }
            if (companyCache && companyCache.id === c.id) { companyCache = c; }
        }

        function select_(company, keepDetails) {
            var prev = current;
            current = company;
            renderOptions();
            if (!keepDetails) { fill(company ? snapshotOf(company) : {}); }
            if (opts.onSwitch && prev !== company) { opts.onSwitch(prev, company); }
            changed();
        }

        // Create (POST) or update (PUT) the selected company from the fields.
        function saveCompany() {
            var d = details();
            if (!d.name) {
                q('[data-co-fields]').hidden = false;
                inputs.name.focus();
                F.toast('Enter the company name first.', 'warning');
                return Promise.reject(null);
            }
            var payload = {};
            ALL_DETAIL_KEYS.forEach(function (k) { payload[k] = d[k]; });
            payload.use_site_logo = !!logo && logo === logoUrl;
            var op = current ? F.put('companies/' + current.id + '/', payload) : F.post('companies/', payload);
            return op.then(function (c) {
                // Logo removed on the form -> remove the uploaded one too.
                if (!logo && current && current.logo_url && current.logo_url !== logoUrl) {
                    return F.del('companies/' + c.id + '/logo/').then(function () { return F.get('companies/' + c.id + '/'); });
                }
                return c;
            }).then(function (c) {
                upsert(c);
                current = c;
                renderOptions();
                changed();
                return c;
            }).catch(function (err) {
                if (err) { F.toast(errorText(err), 'danger'); }
                throw null;
            });
        }

        select.addEventListener('change', function () {
            if (select.value) { select_(byId(select.value)); }
        });
        root.addEventListener('input', function (ev) {
            if (ev.target.hasAttribute('data-co')) { status(); }
        });
        root.addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-act]');
            if (!btn) { return; }
            var act = btn.getAttribute('data-act');
            if (act === 'toggle') {
                var box = q('[data-co-fields]');
                box.hidden = !box.hidden;
                btn.innerHTML = box.hidden ? '<i class="fa fa-pen me-1"></i>Edit details' : '<i class="fa fa-chevron-up me-1"></i>Hide details';
            } else if (act === 'new') {
                select_(null);
                q('[data-co-fields]').hidden = false;
                q('[data-act="toggle"]').innerHTML = '<i class="fa fa-chevron-up me-1"></i>Hide details';
                inputs.name.focus();
            } else if (act === 'save') {
                btn.disabled = true;
                saveCompany().then(function (c) { F.toast('Company "' + c.name + '" saved.'); })
                    .catch(function () {}).finally(function () { btn.disabled = false; });
            } else if (act === 'default' && current) {
                F.post('companies/' + current.id + '/make_default/', {}).then(function (c) {
                    upsert(c);
                    current = c;
                    renderOptions();
                    changed();
                    F.toast(c.name + ' is now the default company.');
                }).catch(function (err) { F.toast(errorText(err), 'danger'); });
            } else if (act === 'upload') {
                fileInput.click();
            } else if (act === 'remove-logo') {
                logo = '';
                showLogo();
                changed();
            }
        });
        fileInput.addEventListener('change', function () {
            var file = fileInput.files[0];
            fileInput.value = '';
            if (!file) { return; }
            if (file.size > 2 * 1024 * 1024) { F.toast('Logo must be 2 MB or smaller.', 'warning'); return; }
            var saved = current && !isDirty() ? Promise.resolve(current) : saveCompany();
            saved.then(function (c) {
                var fd = new FormData();
                fd.append('logo', file);
                return F.postForm('companies/' + c.id + '/logo/', fd);
            }).then(function (c) {
                upsert(c);
                current = c;
                logo = c.logo_url;
                showLogo();
                changed();
                F.toast('Logo uploaded.');
            }).catch(function (err) { if (err) { F.toast(errorText(err), 'danger'); } });
        });

        var ready = F.get('companies/').then(function (list) {
            companies = list || [];
            select_(companies.filter(function (c) { return c.is_default; })[0] || companies[0] || null);
        });

        return {
            ready: ready,
            details: details,
            companyId: function () { return current ? current.id : null; },
            company: function () { return current; },
            // Show a saved document's own letterhead (and its company, if it still exists).
            load: function (companyId, snap) {
                current = byId(companyId);
                renderOptions();
                if (snap && snap.name) { fill(snap); } else { fill(current ? snapshotOf(current) : {}); }
                changed();
            }
        };
    }

    // DRF errors can be nested (e.g. items[2].rate) - flatten to one line.
    function errorText(err) {
        var data = err && err.data;
        if (!data || typeof data !== 'object') { return F.errorText(err); }
        var out = [];
        (function walk(v, label) {
            if (v == null) { return; }
            if (Array.isArray(v)) {
                v.forEach(function (x, i) {
                    walk(x, typeof x === 'object' && x !== null && !Array.isArray(x)
                        ? (label ? label + ' #' + (i + 1) : 'Line ' + (i + 1)) : label);
                });
            } else if (typeof v === 'object') {
                Object.keys(v).forEach(function (k) {
                    var name = (k === 'non_field_errors' || k === 'detail') ? '' : k.replace(/_/g, ' ');
                    walk(v[k], [label, name].filter(Boolean).join(' › '));
                });
            } else {
                out.push((label ? label + ': ' : '') + v);
            }
        })(data, '');
        return out.join(' | ') || F.errorText(err);
    }

    window.Docs = {
        errorText: errorText,
        PAYMENT_METHODS: PAYMENT_METHODS,
        TRANSPORT_MODES: TRANSPORT_MODES,
        setLogo: function (url) { logoUrl = url; },
        num: num,
        round2: round2,
        money: money,
        fmtDate: fmtDate,
        isoDate: isoDate,
        periodLabel: periodLabel,
        amountInWords: amountInWords,
        calcInvoice: calcInvoice,
        calcSlip: calcSlip,
        render: render,
        mountPreview: mountPreview,
        filename: filename,
        downloadPdf: downloadPdf,
        pdfBlob: pdfBlob,
        shareLink: shareLink,
        openShare: openShare,
        loadCompany: loadCompany,
        companyPanel: companyPanel,
        editCompany: editCompany
    };
})(window, document);
