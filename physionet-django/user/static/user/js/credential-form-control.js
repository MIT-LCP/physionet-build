course_category_input = document.getElementById("id_application-course_category");

researcher_category_input = document.getElementById("id_application-researcher_category");

function controlReference() {
  // Make the reference category 'supervisor' if the
  // 'researcher_category' is student/postdoc
  reference_category_input = document.getElementById("id_application-reference_category");
  if (["0", "1", "7"].includes(researcher_category_input.value)){
    reference_category_input.selectedIndex = 1;
  }
}

researcher_category_input.onload = controlReference();
researcher_category_input.onchange = controlReference;
