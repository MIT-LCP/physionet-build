'use strict';

(function() {
    const dom = {
        nav: document.querySelector('.nav'),
        hamburger: document.querySelector('.nav__hamburger'),
        hamburgerMenu: document.querySelector('.nav__mobile'),
        navWrapper: document.querySelector('.nav-wrapper'),
        expandableLinks: document.querySelectorAll('.nav-link--expandable'),
        searchOpenButton: document.querySelector('.nav__search__open'),
        searchCloseButton: document.querySelector('.nav__search__close')
    };

    if (HTMLElement.prototype.hasOwnProperty("popover")) {
        dom.hamburgerMenu.addEventListener('toggle', (ev) => {
            // Update button to reflect popover state
            if (ev.newState === 'open') {
                dom.navWrapper.classList.add('nav-wrapper--mobile-open');
            } else {
                dom.navWrapper.classList.remove('nav-wrapper--mobile-open');
            }
        });
    } else {
        // Backward compatibility for browsers that don't support popover

        dom.expandableLinks.forEach((link) => {
            link.addEventListener('click', (ev) => {
                ev.stopPropagation();
                ev.target.classList.toggle('nav-link--expanded');
            });
        });

        // clickaway
        document.addEventListener('click', (ev) => {
            dom.expandableLinks.forEach((link) => {
                link.classList.remove('nav-link--expanded');
            });
            dom.navWrapper.classList.remove('nav-wrapper--mobile-open');
        });

        dom.hamburger.addEventListener('click', (ev) => {
            ev.stopPropagation();
            dom.navWrapper.classList.toggle('nav-wrapper--mobile-open');
        });
    }

    dom.searchOpenButton.addEventListener('click', () => {
        dom.nav.classList.add('nav--search');
    });
    dom.searchCloseButton.addEventListener('click', () => {
        dom.nav.classList.remove('nav--search');
    });
})();
