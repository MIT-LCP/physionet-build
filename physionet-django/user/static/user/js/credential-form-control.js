course_category_input = document.getElementById("id_course_category");

function controlCourses() {
  // Control the course name/number selection based on course category
  course_name_input = document.getElementById("id_course_name");
  course_number_input = document.getElementById("id_course_number");
  if (course_category_input.value == "0") {
    course_name_input.selectedIndex = 0;
    course_name_input.disabled = true;
    course_name_input.hidden = true;
    course_name_input.required = false;
    $('label[for="course_name"]').hide();

    course_number_input.selectedIndex = 0;
    course_number_input.disabled = true;
    course_number_input.hidden = true;
    course_number_input.required = false;
    $('label[for="course_number"]').hide();
  }
  else {
    course_name_input.disabled = false;
    course_name_input.hidden = false;
    course_name_input.required = true;
    $('label[for="course_name"]').show ();

    course_number_input.disabled = false;
    course_number_input.hidden = false;
    course_number_input.required = true;
    $('label[for="course_number"]').show ();
  }
}

course_category_input.onload = controlCourses();
course_category_input.onchange = controlCourses;


researcher_category_input = document.getElementById("id_researcher_category");

function controlReference() {
  // Make the reference category 'supervisor' if the
  // 'researcher_category' is student/postdoc
  reference_category_input = document.getElementById("id_reference_category");
  if (["0", "1"].includes(researcher_category_input.value)){
    reference_category_input.selectedIndex = 1;
  }
}

researcher_category_input.onload = controlReference();
researcher_category_input.onchange = controlReference;
