function loadLicense() {
  // Reload the license input whenever the selected access policy
  // changes to update the available licenses
  console.log(load_url)
  $.ajax({
          type: "GET",
          url: load_url,
          data: {'access_policy':access_policy_input.value},
          success: function reloadSection(result){
              $("#id_license").replaceWith(result);
          },
  });
}
