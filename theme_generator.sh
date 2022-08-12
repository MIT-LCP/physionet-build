#! /bin/bash
# purpose : to write the theme file : theme.scss
# Author : Rutvik Solanki
# Date : 10/10/2019

echo 'Creating theme.scss file'
echo '$theme-colors: (' > physionet-django/static/bootstrap/scss/theme.scss
echo '"dark": #'"${DARK}," >> physionet-django/static/bootstrap/scss/theme.scss
echo '"primary": #'"${PRIMARY}," >> physionet-django/static/bootstrap/scss/theme.scss
echo ');' >> physionet-django/static/bootstrap/scss/theme.scss
echo "" >> physionet-django/static/bootstrap/scss/theme.scss
echo '@import "bootstrap";' >> physionet-django/static/bootstrap/scss/theme.scss