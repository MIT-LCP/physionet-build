$("#id_new_password1").keyup(function()
{
	// NOTE: Keep list of forbidden words in sync with
	// zxcvbn_ProgressBar_Register.js and ComplexityValidator in
	// validators.py

	var name = document.getElementById("helper").getAttribute("data-name");
	var last = document.getElementById("helper").getAttribute("data-last");
	var email = document.getElementById("helper").getAttribute("data-email");
	var user = document.getElementById("helper").getAttribute("data-username");
	var t = (email + ' ' + name + ' ' + last + ' ' + user +
	         ' physio physionet');

	$("#StrengthProgressBar").zxcvbnProgressBar({
		passwordInput: "#id_new_password1",
		userInputs: t.match(/\d+|[^\W\d_]+/g)
	});
});
