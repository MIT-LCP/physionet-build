$(document).ready(function()
{
	$('input[type=text]').change(function() {
		$("#StrengthProgressBar").zxcvbnProgressBar({
			passwordInput: "#id_password", 
			userInputs: [$("#id_email").val(), $("#id_first_name").val(), 
				$("#id_middle_names").val(), $("#id_last_name").val()]
		});
	});
});