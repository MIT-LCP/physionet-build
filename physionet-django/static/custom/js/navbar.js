'use strict';

(function() {
    const dom = {
        nav: document.querySelector('.nav'),
        hamburger: document.querySelector('.nav__hamburger'),
        navWrapper: document.querySelector('.nav-wrapper'),
        expandableLinks: document.querySelectorAll('.nav-link--expandable'),
        searchOpenButton: document.querySelector('.nav__search__open'),
        searchCloseButton: document.querySelector('.nav__search__close')
    };

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

    dom.searchOpenButton.addEventListener('click', () => {
        dom.nav.classList.add('nav--search');
    });
    dom.searchCloseButton.addEventListener('click', () => {
        dom.nav.classList.remove('nav--search');
    });

    dom.hamburger.addEventListener('click', (ev) => {
        ev.stopPropagation();
        dom.navWrapper.classList.toggle('nav-wrapper--mobile-open');
    });
})();
