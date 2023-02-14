var slideIndex = 1;
sessionStorage.setItem("slidePosition", 0)

showSlide(slideIndex);

function changeSlide(n) {
    console.log(n)
    showSlide(slideIndex += n);
}

$('.next').on('click', function () {
    // move to next slide but keep track of start of partaining training
    var slidePosition = parseInt(sessionStorage.getItem("slidePosition"))
    sessionStorage.setItem("slidePosition", slidePosition-1)
    changeSlide(1);
})

function showSlide(n) {
    var i;
    var slides = document.getElementsByClassName("eachQuiz");
    if (n > slides.length) {
        alertBox("<strong>Congratulations</strong> You have come to the end of the training.")
        sessionStorage.clear()
        $('form').submit()
    }
    if (n < 1) { slideIndex = slides.length }
    for (i = 0; i < slides.length; i++) {
        slides[i].style.display = "none";
    }
    slides[slideIndex - 1].style.display = "block";
}

$("input[type=radio]").on("click", function () {
    // check if answer is correct and proceed, else take back to training
    let id = $(this).attr("name")
    let value = $(this).val();
    var slidePosition = parseInt(sessionStorage.getItem("slidePosition"))

    sessionStorage.setItem("slidePosition", 0)

    if (sessionStorage.getItem(id) == value) {
      alertBox("<strong>Yay!</strong> You chose the correct answer.", "success")
      changeSlide(1)
    } else {
      alertBox("<strong>Oops!</strong> You chose a wrong answer, kindly go through the training again.", "danger")
      changeSlide(slidePosition)
    }
})

function alertBox(message, _class) {
    var alert = document.getElementById("alert");
    alert.classList.add("alert-" + _class)
    alert.innerHTML = message
    alert.style.display = "block"
    setTimeout(function() {
        alert.style.display = "none"
    }, 3000);
};
