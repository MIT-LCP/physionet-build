//Requires zxcvbn.js and Bootstrap
(function ($) {

	$.fn.zxcvbnProgressBar = function (options, ) {
		//init settings
		var settings = $.extend({
			passwordInput: '#id_password',
			userInputs: [],
			ratings: ["Very weak", "Weak", "OK", "Strong", "Very strong"],
			//all progress bar classes removed before adding score specific css class
			allProgressBarClasses: "bg-danger bg-warning bg-success progress-bar-striped active",
			//bootstrap css classes (0-4 corresponds with zxcvbn score)
			progressBarClass0: "progress-bar progress-bar-striped progress-bar-animated bg-danger active",
			progressBarClass1: "progress-bar progress-bar-striped progress-bar-animated bg-danger active",
			progressBarClass2: "progress-bar progress-bar-striped progress-bar-animated bg-warning active",
			progressBarClass3: "progress-bar progress-bar-striped progress-bar-animated bg-success",
			progressBarClass4: "progress-bar progress-bar-striped progress-bar-animated bg-success",
		}, options);
		return this.each(function () {
			settings.progressBar = this;
			//init progress bar display
			UpdateProgressBar();
			//Update progress bar on each keypress of password input
			$(settings.passwordInput).keyup(function (event) {
				UpdateProgressBar();
			});
		});

		function UpdateProgressBar() {
			var progressBar = settings.progressBar;
			var password = $(settings.passwordInput).val();
			if (password) {
				var result = zxcvbn(password, settings.userInputs);
				//result.score: 0, 1, 2, 3 or 4 - if crack time is less than 10**2, 10**4, 10**6, 10**8, Infinity.
				var scorePercentage = (result.score + 1) * 20;
				$(progressBar).css('width', scorePercentage + '%');

				if (result.score == 0) {
					//weak
					$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass0);
					$(progressBar).html(settings.ratings[0]);
				}
				else if (result.score == 1) {
					//normal
					$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass1);
					$(progressBar).html(settings.ratings[1]);
				}
				else if (result.score == 2) {
					//medium
					$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass2);
					$(progressBar).html(settings.ratings[2]);
				}
				else if (result.score == 3) {
					//strong
					$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass3);
					$(progressBar).html(settings.ratings[3]);
				}
				else if (result.score == 4) {
					//very strong
					$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass4);
					$(progressBar).html(settings.ratings[4]);
				}
			}
			else {
				$(progressBar).css('width', '0%');
				$(progressBar).removeClass(settings.allProgressBarClasses).addClass(settings.progressBarClass0);
				$(progressBar).html('');
			}
		}
	};
})(jQuery);
