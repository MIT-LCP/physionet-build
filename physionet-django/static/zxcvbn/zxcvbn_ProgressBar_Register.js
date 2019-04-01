$("#id_password1").keyup(function()
{
	// NOTE: Keep list of forbidden words in sync with
	// zxcvbn_ProgressBar_Change.js and ComplexityValidator in
	// validators.py

	var t = ($("#id_email").val() + ' ' +
	         $("#id_first_names").val() + ' ' +
	         $("#id_last_name").val() + ' ' +
	         $("#id_username").val() + ' physio physionet');

	$("#StrengthProgressBar").zxcvbnProgressBar({
		passwordInput: "#id_password1",
		userInputs: t.match(/\d+|[^\W\d_]+/g)
	});
});

