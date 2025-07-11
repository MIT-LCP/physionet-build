# Static Assets Licensing and Sources

This directory contains third-party static assets required for the PhysioNet homepage and UI. All assets are free and open-source, and are hosted locally to comply with project requirements.

## Fonts

### Inter
- **Source:** https://github.com/rsms/inter
- **License:** SIL Open Font License (OFL)
- **Files:** `fonts/inter-regular.ttf`, `fonts/inter-bold.ttf`, `fonts/inter-medium.ttf`, `fonts/inter-light.ttf`, `fonts/inter-italic.ttf`, `fonts/inter-local.css`

## Icons

### Bootstrap Icons
- **Source:** https://github.com/twbs/icons
- **License:** MIT
- **Files:** `bootstrap-icons/bootstrap-icons.css`, `bootstrap-icons/bootstrap-icons.woff2`, `bootstrap-icons/bootstrap-icons.woff`, `bootstrap-icons/bootstrap-icons.json`

## JavaScript & CSS Libraries

### Swiper.js
- **Source:** https://github.com/nolimits4web/swiper
- **License:** MIT
- **Files:** `swiper/swiper-bundle.min.js`, `swiper/swiper-bundle.js`, `swiper/swiper-bundle.min.css`, `swiper/swiper-bundle.css`

## Updating Assets
- Download the latest version from the official source above.
- Place minified and unminified versions in the appropriate subdirectory.
- Update references in Django templates as needed.

## Notes
- All images and other static assets in this directory are either original, open-source, or otherwise cleared for use.
- If you add new third-party assets, document their source and license here. 