$('.author_invitation_response_form').each(function() {
    var response_select = $(this).find('select[name$="-response"]');
    var affiliation_label = $(this).find('label[for$="-affiliation"]');
    var affiliation_input = $(this).find('input[name$="-affiliation"]');
    var affiliation_country_label = $(this).find('label[for$="-affiliation_country"]');
    var affiliation_country_input = $(this).find('select[name$="-affiliation_country"]');
    function update_response() {
        if (this.value === '0') { // decline invitation
            affiliation_label.hide();
            affiliation_input.hide();
            affiliation_input.attr('required', false);
            affiliation_country_label.hide();
            affiliation_country_input.hide();
            affiliation_country_input.attr('required', false);
        }
        else {
            affiliation_label.show();
            affiliation_input.show();
            affiliation_input.attr('required', true);
            affiliation_country_label.show();
            affiliation_country_input.show();
            affiliation_country_input.attr('required', true);
        }
    }
    response_select.each(update_response);
    response_select.change(update_response);
});
