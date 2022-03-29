function sortTable(n, table_name) {
  // Switch the icon and reset the others
  id_name = "icon_" + n + "_" + table_name;
  current_icon = document.getElementById(id_name).className;
  if ((current_icon == "fas fa-sort") || (current_icon == "fas fa-sort-down")) {
    document.getElementById(id_name).className = "fas fa-sort-up";
  } else if (current_icon == "fas fa-sort-up") {
    document.getElementById(id_name).className = "fas fa-sort-down";
  }
  if ((table_name == "responset") || (table_name == "finalt")) {
    var valid_ids = [0,1,2,3,6];
  } else {
    var valid_ids = [0,1,2,3,4];
  }
  for (var i=0; i<valid_ids.length; i++) {
    if (valid_ids[i] != n) {
      id_name = "icon_" + valid_ids[i] + "_" + table_name;
      document.getElementById(id_name).className = "fas fa-sort";
    }
  }
  // Sort the contents
  var table, rows, switching, i, x, y, should_switch, dir, switch_count = 0;
  table = document.getElementById(table_name);
  switching = true;
  dir = "asc";
  while (switching) {
    switching = false;
    rows = table.rows;
    for (i=1; i<(rows.length - 1); i++) {
      should_switch = false;
      x = rows[i].getElementsByTagName("TD")[n];
      y = rows[i+1].getElementsByTagName("TD")[n];
      if ((n == 4) || (n == 6)) {
        x_sort = Date.parse(x.innerHTML);
        y_sort = Date.parse(y.innerHTML);
      } else {
        x_sort = x.innerHTML.toLowerCase();
        y_sort = y.innerHTML.toLowerCase();
      }
      if ((dir == "asc") && (x_sort > y_sort)) {
        should_switch = true;
        break;
      } else if ((dir == "desc") && (x_sort < y_sort)) {
        should_switch = true;
        break;
      }
    }
    if (should_switch) {
      rows[i].parentNode.insertBefore(rows[i+1], rows[i]);
      switching = true;
      switch_count++;
    } else if ((switch_count == 0) && (dir == "asc")) {
      dir = "desc";
      switching = true;
    }
  }
}
