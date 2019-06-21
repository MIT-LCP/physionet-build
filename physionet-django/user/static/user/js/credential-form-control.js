course_category_input = document.getElementById("id_application-course_category");

function controlCourses() {
  // Control the course name/number selection based on course category
  course_name_input = document.getElementById("id_application-course_info");
  if (course_category_input.value == "0") {
    course_name_input.selectedIndex = 0;
    course_name_input.disabled = true;
    course_name_input.hidden = true;
    course_name_input.required = false;
    $('label[for="course_info"]').hide();
  }
  else {
    course_name_input.disabled = false;
    course_name_input.hidden = false;
    course_name_input.required = true;
    $('label[for="course_info"]').show ();
  }
}

course_category_input.onload = controlCourses();
course_category_input.onchange = controlCourses;


researcher_category_input = document.getElementById("id_application-researcher_category");

function controlReference() {
  // Make the reference category 'supervisor' if the
  // 'researcher_category' is student/postdoc
  reference_category_input = document.getElementById("id_application-reference_category");
  if (["0", "1"].includes(researcher_category_input.value)){
    reference_category_input.selectedIndex = 1;
  }
}

researcher_category_input.onload = controlReference();
researcher_category_input.onchange = controlReference;
