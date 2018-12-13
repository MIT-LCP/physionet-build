$(document).ready(function()
{
	var name = document.getElementById("helper").getAttribute("data-name");
	var last = document.getElementById("helper").getAttribute("data-last");
	var url = document.getElementById("helper").getAttribute("data-url");
	var email = document.getElementById("helper").getAttribute("data-email");
	$("#StrengthProgressBar").zxcvbnProgressBar({
		passwordInput: "#id_new_password1",
		userInputs: [name, last, url, email]
	});
});
