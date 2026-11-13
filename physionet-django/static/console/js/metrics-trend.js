/* Tables remain available without JavaScript. Missing medians break the line. */
document.querySelectorAll('[data-metrics-chart]').forEach(function (container) {
  const data = JSON.parse(document.getElementById(container.dataset.metricsChart).textContent);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 900 300');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', container.dataset.label);
  svg.style.width = '100%';
  const colors = ['#005a9c', '#9b3d00', '#287535'];
  function add(tag, attrs, text) {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(function (entry) { node.setAttribute(entry[0], entry[1]); });
    if (text !== undefined) node.textContent = text;
    svg.appendChild(node);
    return node;
  }
  const values = data.series.flatMap(function (s) { return s.values.filter(function (v) { return v !== null; }); });
  const maximum = Math.max(1, ...values);
  function x(i) { return 65 + i * 780 / Math.max(1, data.labels.length - 1); }
  function y(v) { return 240 - v * 190 / maximum; }
  for (let i = 0; i <= 4; i++) {
    const value = maximum * i / 4;
    add('line', {x1: 65, y1: y(value), x2: 845, y2: y(value), stroke: '#ddd'});
    add('text', {x: 55, y: y(value) + 4, 'text-anchor': 'end', 'font-size': 12}, Number(value.toFixed(2)));
  }
  data.labels.forEach(function (label, i) {
    if (i % Math.max(1, Math.ceil(data.labels.length / 6)) === 0 || i === data.labels.length - 1) {
      add('text', {x: x(i), y: 265, 'text-anchor': 'middle', 'font-size': 12}, label);
    }
  });
  data.series.forEach(function (series, index) {
    const color = colors[index % colors.length];
    let previous = null;
    series.values.forEach(function (value, i) {
      if (value === null) { previous = null; return; }
      if (previous !== null) add('line', {x1: x(previous), y1: y(series.values[previous]), x2: x(i), y2: y(value), stroke: color, 'stroke-width': 2});
      const point = add('circle', {cx: x(i), cy: y(value), r: 4, fill: color, tabindex: 0});
      const title = document.createElementNS(ns, 'title');
      title.textContent = data.labels[i] + ' — ' + series.name + ': ' + value;
      point.appendChild(title);
      previous = i;
    });
    add('text', {x: 65 + index * 260, y: 290, fill: color, 'font-size': 13}, series.name);
  });
  container.appendChild(svg);
});
