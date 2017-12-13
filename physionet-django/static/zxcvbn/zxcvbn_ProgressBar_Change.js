$(document).ready(function()
{
	var name = document.getElementById("helper").getAttribute("data-name");
	var last = document.getElementById("helper").getAttribute("data-last");
	var middle = document.getElementById("helper").getAttribute("data-middle");
	var url = document.getElementById("helper").getAttribute("data-url");
	var phone = document.getElementById("helper").getAttribute("data-phone");
	var email = document.getElementById("helper").getAttribute("data-email");
	$("#StrengthProgressBar").zxcvbnProgressBar({
		passwordInput: "#id_new_password1", 
		userInputs: [name, last, middle, url, phone, email]
	});
});
