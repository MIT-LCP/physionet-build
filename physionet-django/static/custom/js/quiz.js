

function changeSlide(n) {
    showSlide(slideIndex += n);
}

$('.next').on('click', function () {
    // move to next slide but keep track of start of partaining training
    let slidePosition = parseInt(sessionStorage.getItem("slidePosition"));
    sessionStorage.setItem("slidePosition", slidePosition - 1)
    changeSlide(1);
})

$('.previous').on('click', function () {
    // move to next slide but keep track of start of partaining training
    let slidePosition = parseInt(sessionStorage.getItem("slidePosition"));
    sessionStorage.setItem("slidePosition", slidePosition - 2);
    changeSlide(-1);
})

function showSlide(n) {

    let i;
    let slides = document.getElementsByClassName("eachQuiz");
    if (n > slides.length) {
        alertBox("<strong>Congratulations</strong> You have come to the end of this module.");
        sessionStorage.clear();

        let question_answers = {};
        document.querySelectorAll('.question input[type="radio"]:checked').forEach(function (eachQuiz) {
            let question_id = eachQuiz.getAttribute("name");
            let value = eachQuiz.value;
            question_answers[question_id] = parseInt(value);
        });

        $('[name="question_answers"]').val(JSON.stringify(question_answers));

        $('form').submit();
    }
    if (n < 1) { slideIndex = slides.length }
    for (i = 0; i < slides.length; i++) {
        slides[i].style.display = "none";
    }

    slides[slideIndex - 1].style.display = "block";
}
//
// $("input[type=radio]").on("click", function () {
//     // check if answer is correct and proceed, else take back to training
//     let id = $(this).attr("name")
//     let value = $(this).val();
//     var slidePosition = parseInt(sessionStorage.getItem("slidePosition"))
//
//     sessionStorage.setItem("slidePosition", 0)
//
//     if (sessionStorage.getItem(id) == value) {
//       alertBox("<strong>Yay!</strong> You chose the correct answer.", "success")
//       changeSlide(1)
//     } else {
//       alertBox("<strong>Oops!</strong> You chose a wrong answer, kindly go through the training again.", "danger")
//       changeSlide(slidePosition)
//     }
// })

$('.checkAnswer').on('click', function () {

    let question_id = $('input[type="radio"]:checked', $(this).parent()).attr("name");
    if (question_id == undefined) {
        alertBox("<strong>Oops!</strong> You did not choose an answer, kindly choose an answer.", "danger");
        return
    }
    let value = $('input[type="radio"]:checked', $(this).parent()).val();
    // let slidePosition = parseInt(sessionStorage.getItem("slidePosition"));

    sessionStorage.setItem("slidePosition", 0);

    if (sessionStorage.getItem(question_id) == value) {
        alertBox("<strong>Yay!</strong> You chose the correct answer.", "success");
        $('.next', $(this).parent().parent()).removeClass('disabled');
        // changeSlide(1);
    } else {
        alertBox("<strong>Oops!</strong> You chose a wrong answer, kindly go through the previous sections again.", "danger");
        // changeSlide(slidePosition);
        $('.next', $(this).parent().parent()).addClass('disabled');
    }
});

function alertBox(message, _class) {
    let alert = document.getElementById("alert");
    alert.className = "alert alert-" + _class;
    alert.innerHTML = message;
    alert.style.display = "block";
    setTimeout(function () {
        alert.style.display = "none";
    }, 3000);
};
