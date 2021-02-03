(function($) {
  "use strict"; // Start of use strict
  // Configure tooltips for collapsed side navigation
  $('.navbar-sidenav [data-toggle="tooltip"]').tooltip({
    template: '<div class="tooltip navbar-sidenav-tooltip" role="tooltip" style="pointer-events: none;"><div class="arrow"></div><div class="tooltip-inner"></div></div>'
  })
  // Toggle the side navigation
  $("#sidenavToggler").click(function(e) {
    e.preventDefault();
    $("body").toggleClass("sidenav-toggled");
    $(".navbar-sidenav .nav-link-collapse").addClass("collapsed");
    $(".navbar-sidenav .sidenav-second-level, .navbar-sidenav .sidenav-third-level").removeClass("show");
  });
  // Force the toggled class to be removed when a collapsible nav link is clicked
  $(".navbar-sidenav .nav-link-collapse").click(function(e) {
    e.preventDefault();
    $("body").removeClass("sidenav-toggled");
  });
  // Scroll to top button appear
  $(document).scroll(function() {
    var scrollDistance = $(this).scrollTop();
    if (scrollDistance > 100) {
      $('.scroll-to-top').fadeIn();
    } else {
      $('.scroll-to-top').fadeOut();
    }
  });
  // Configure tooltips globally
  $('[data-toggle="tooltip"]').tooltip()
  // Smooth scrolling using jQuery easing
  $(document).on('click', 'a.scroll-to-top', function(event) {
    var $anchor = $(this);
    $('html, body').stop().animate({
      scrollTop: ($($anchor.attr('href')).offset().top)
    }, 1000, 'easeInOutExpo');
    event.preventDefault();
  });
})(jQuery); // End of use strict

// Define the chart (try to make dynamic)
var cred_chart = d3_cred_chart()
  .width(0.845 * window.innerWidth)
  .height(0.7 * window.innerHeight)
  .x_label("Date")
  .y_label("Pending Applications");
// Define the canvas
var svg = d3.select("#cred_tracker").append("svg")
  .datum(data)
  .call(cred_chart);
// Create the figure
function d3_cred_chart() {
  // Actually edit the chart
  function chart(selection){
    selection.each(function(input_data) {
      // Set the margins
      var margin = {top: 20, right: 80, bottom: 80, left: 100},
      inner_width = width - margin.left - margin.right,
      inner_height = height - margin.top - margin.bottom;
      // Parse the input dates
      var parse_time = d3.time.format("%d-%b-%y").parse;
      input_data[0].x.forEach(function(d,i){
        input_data[0].x[i] = parse_time(d);
      });
      // Set the x-axis scale
      var x_scale = d3.time.scale()
        .range([0, inner_width])
        .domain([d3.min(input_data, function(d) { return d3.min(d.x); }),
                  d3.max(input_data, function(d) { return d3.max(d.x); })]);
      // Set the y-axis scale
      var y_scale = d3.scale.linear()
        .range([inner_height, 0])
        .domain([0,
                  d3.max(input_data, function(d) { return 1.1*d3.max(d.y); })]);
      // Define the x-axis
      var x_axis = d3.svg.axis()
        .scale(x_scale)
        .orient("bottom")
        .tickFormat(d3.time.format("%d-%b-%y"));
      // Define the y-axis
      var y_axis = d3.svg.axis()
        .scale(y_scale)
        .orient("left");
      // Set the x-axis grid
      var x_grid = d3.svg.axis()
        .scale(x_scale)
        .orient("bottom")
        .tickSize(-inner_height)
        .tickFormat("");
      // Set the y-axis grid
      var y_grid = d3.svg.axis()
        .scale(y_scale)
        .orient("left")
        .tickSize(-inner_width)
        .tickFormat("");
      // Draw the actual line
      var draw_line = d3.svg.line()
        .interpolate("basis")
        .x(function(d) { return x_scale(d[0]); })
        .y(function(d) { return y_scale(d[1]); });
      // Create the SVG object
      var svg = d3.select(this)
        .attr("width", width)
        .attr("height", height)
        .append("g")
        .attr("transform", "translate(" + margin.left + "," + margin.top + ")");
      // Set the inner padding for the x-axis
      svg.append("g")
        .attr("class", "x grid")
        .attr("transform", "translate(0," + inner_height + ")")
        .call(x_grid);
      // Set the inner padding for the y-axis
      svg.append("g")
        .attr("class", "y grid")
        .call(y_grid);
      // Set the x-label
      svg.append("g")
        .attr("class", "x axis")
        .attr("transform", "translate(0," + inner_height + ")")
        .call(x_axis)
        .selectAll("text")
          .style("text-anchor", "middle")
          .attr("dx", "-2.5em")
          .attr("dy", "0.7em")
          .attr("transform", function(d) {
              return "rotate(-45)"
            })
      // Set the y-label
      svg.append("g")
        .attr("class", "y axis")
        .call(y_axis)
        .append("text")
        .attr("transform", "translate(0," + inner_height/2 + ")rotate(-90)")
        .attr("dy", "-4em")
        .attr('text-anchor', 'middle')
        .text(y_label);
      // Get the line data
      var data_lines = svg.selectAll(".d3_cred_chart_line")
        .data(input_data.map(function(d) { return d3.zip(d.x, d.y); }))
        .enter().append("g")
        .attr("class", "d3_cred_chart_line");
      // Draw the line and set the color
      data_lines.append("path")
        .attr("class", "line")
        .attr("d", function(d){ return draw_line(d); })
        .attr("stroke", "red");
    });
  };
  // Set the canvas width
  chart.width = function(value) {
      if (!arguments.length) {
        return width;
      };
      width = value;
      return chart;
  };
  // Set the canvas height
  chart.height = function(value) {
    if (!arguments.length) {
      return height;
    };
    height = value;
    return chart;
  };
  // Set the x-label
  chart.x_label = function(value) {
    if (!arguments.length) {
      return x_label;
    };
    x_label = value;
    return chart;
  };
  // Set the y-label
  chart.y_label = function(value) {
    if (!arguments.length) {
      return y_label;
    };
    y_label = value;
    return chart;
  };
  // Render the figure
  return chart;
};
