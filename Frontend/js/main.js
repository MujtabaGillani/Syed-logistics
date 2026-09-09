(function ($) {
    "use strict";

    // Spinner
    var spinner = function () {
        setTimeout(function () {
            if ($('#spinner').length > 0) {
                $('#spinner').removeClass('show');
            }
        }, 1);
    };
    spinner();
    
    
    // Animation is optional; a missing library must never stop login handling.
    if (typeof WOW !== 'undefined') {
        new WOW().init();
    }


    // Sticky Navbar
    $(window).scroll(function () {
        if ($(this).scrollTop() > 300) {
            $('.sticky-top').css('top', '0px');
        } else {
            $('.sticky-top').css('top', '-100px');
        }
    });
    
    
    // Dropdown on mouse hover
    const $dropdown = $(".dropdown");
    const $dropdownToggle = $(".dropdown-toggle");
    const $dropdownMenu = $(".dropdown-menu");
    const showClass = "show";
    
    $(window).on("load resize", function() {
        if (this.matchMedia("(min-width: 992px)").matches) {
            $dropdown.hover(
            function() {
                const $this = $(this);
                $this.addClass(showClass);
                $this.find($dropdownToggle).attr("aria-expanded", "true");
                $this.find($dropdownMenu).addClass(showClass);
            },
            function() {
                const $this = $(this);
                $this.removeClass(showClass);
                $this.find($dropdownToggle).attr("aria-expanded", "false");
                $this.find($dropdownMenu).removeClass(showClass);
            }
            );
        } else {
            $dropdown.off("mouseenter mouseleave");
        }
    });
    
    
    // Back to top button
    $(window).scroll(function () {
        if ($(this).scrollTop() > 300) {
            $('.back-to-top').fadeIn('slow');
        } else {
            $('.back-to-top').fadeOut('slow');
        }
    });
    $('.back-to-top').click(function () {
        $('html, body').animate({scrollTop: 0}, 1500, 'easeInOutExpo');
        return false;
    });


    // Dashboard authentication modals
    const loginElement = document.getElementById('loginModal');
    const signupElement = document.getElementById('signupModal');

    if (loginElement && signupElement && !window.syedAuthInitialized) {
        const loginModal = bootstrap.Modal.getInstance(loginElement) || new bootstrap.Modal(loginElement);
        const signupModal = bootstrap.Modal.getInstance(signupElement) || new bootstrap.Modal(signupElement);

        document.querySelectorAll('.js-dashboard-login').forEach(function (link) {
            link.addEventListener('click', function (event) { event.preventDefault(); });
        });

        document.querySelectorAll('[data-auth-switch]').forEach(function (button) {
            button.addEventListener('click', function () {
                const showSignup = button.dataset.authSwitch === 'signup';
                const currentElement = showSignup ? loginElement : signupElement;
                const nextModal = showSignup ? signupModal : loginModal;
                bootstrap.Modal.getInstance(currentElement).hide();
                currentElement.addEventListener('hidden.bs.modal', function showNext() {
                    nextModal.show();
                }, { once: true });
            });
        });

        document.querySelectorAll('.password-toggle').forEach(function (button) {
            button.addEventListener('click', function () {
                const input = button.parentElement.querySelector('input');
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                button.setAttribute('aria-pressed', show ? 'true' : 'false');
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

        async function submitAuth(form, url, messageElement) {
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
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                    },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (!response.ok) {
                    Object.entries(data.errors || {}).forEach(function (entry) {
                        const input = form.elements[entry[0]];
                        if (!input) return;
                        input.classList.add('is-invalid');
                        const feedback = input.closest('.col-md-6, .col-12')?.querySelector('.invalid-feedback');
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
            const data = await submitAuth(event.currentTarget, event.currentTarget.action, document.getElementById('loginMessage'));
            if (data && data.redirect) {
                const requested = new URLSearchParams(window.location.search).get('next');
                window.location.assign(requested && requested.startsWith('/') && !requested.startsWith('//') ? requested : data.redirect);
            }
        });

        document.getElementById('signupForm').addEventListener('submit', async function (event) {
            event.preventDefault();
            const data = await submitAuth(event.currentTarget, event.currentTarget.action, document.getElementById('signupMessage'));
            if (data && data.message) event.currentTarget.reset();
        });

        if (new URLSearchParams(window.location.search).has('next')) loginModal.show();
    }


    // Facts counter
    $('[data-toggle="counter-up"]').counterUp({
        delay: 10,
        time: 2000
    });


    // Header carousel
    $(".header-carousel").owlCarousel({
        autoplay: false,
        smartSpeed: 1500,
        items: 1,
        dots: false,
        loop: true,
        nav : true,
        navText : [
            '<i class="bi bi-chevron-left"></i>',
            '<i class="bi bi-chevron-right"></i>'
        ]
    });


    // Testimonials carousel - Commented out to prevent conflicts with dynamic loading
    // $(".testimonial-carousel").owlCarousel({
    //     autoplay: false,
    //     smartSpeed: 1000,
    //     center: true,
    //     dots: true,
    //     loop: true,
    //     responsive: {
    //         0:{
    //             items:1
    //         },
    //         768:{
    //             items:2
    //         },
    //         992:{
    //             items:3
    //         }
    //     }
    // });

    // Service previews run continuously to keep the service grid lively.
    const serviceVideos = document.querySelectorAll('.service-preview');
    const featureVideos = document.querySelectorAll('.feature-preview, .content-preview');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!reduceMotion.matches) {
        serviceVideos.forEach(function (video) {
            video.play().catch(function () {});
        });
    }

    // The feature panel is a single large video, so it can safely play while in view.
    if (featureVideos.length && !reduceMotion.matches && 'IntersectionObserver' in window) {
        const featureVideoObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                const video = entry.target;
                if (entry.isIntersecting) {
                    video.play().catch(function () {});
                } else {
                    video.pause();
                }
            });
        }, { threshold: 0.35 });
        featureVideos.forEach(function (video) { featureVideoObserver.observe(video); });
    }
    
})(jQuery);

