access_policy_input = document.getElementById("id_access_policy");

function controlDUA() {
  // Control the DUA selection based on access policy
  dua_input = document.getElementById("id_data_use_agreement");
  if (access_policy_input.value == "0") {
    dua_input.selectedIndex = 0;
    dua_input.disabled = true;
    dua_input.hidden = true;
    dua_input.required = false;
    $('label[for="data_use_agreement"]').hide();
  }
  else {
    dua_input.disabled = false;
    dua_input.hidden = false;
    dua_input.required = true;
    $('label[for="data_use_agreement"]').show ();
  }
}
access_policy_input.onload = controlDUA();
access_policy_input.onchange = controlDUA;
