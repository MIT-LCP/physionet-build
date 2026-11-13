/* Tables remain available without JavaScript. Missing medians break the line. */
document.querySelectorAll('[data-metrics-chart]').forEach(function (container) {
  const data = JSON.parse(document.getElementById(container.dataset.metricsChart).textContent);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 900 300');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', container.dataset.label);
  svg.style.width = '100%';
  const colors = ['#2563eb', '#ea580c', '#15803d'];
  function add(tag, attrs, text) {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(function (entry) { node.setAttribute(entry[0], entry[1]); });
    if (text !== undefined) node.textContent = text;
    svg.appendChild(node);
    return node;
  }
  const values = data.series.flatMap(function (s) { return s.values.filter(function (v) { return v !== null; }); });
  const stacked = data.type === 'stacked-bar';
  const totals = data.labels.map(function (_, i) {
    return data.series.reduce(function (total, series) { return total + (series.values[i] || 0); }, 0);
  });
  const rawMaximum = Math.max(1, ...(stacked ? totals : values));
  const targetStep = rawMaximum / 4;
  const magnitude = Math.pow(10, Math.floor(Math.log10(targetStep)));
  const fraction = targetStep / magnitude;
  const factor = fraction < 1.5 ? 1 : fraction < 3.5 ? 2 : fraction < 7.5 ? 5 : 10;
  const step = stacked ? Math.max(1, factor * magnitude) : factor * magnitude;
  const maximum = Math.ceil(rawMaximum / step) * step;
  const partial = data.partial || [];
  function coverage(i) { return partial[i] ? ' (partial month)' : ''; }
  const slotWidth = 780 / Math.max(1, data.labels.length);
  const barWidth = Math.min(44, slotWidth * 0.7);
  const bases = data.labels.map(function () { return 0; });
  function x(i) {
    return stacked ? 65 + (i + 0.5) * slotWidth : 65 + i * 780 / Math.max(1, data.labels.length - 1);
  }
  function y(v) { return 240 - v * 190 / maximum; }
  for (let i = 0; i <= Math.round(maximum / step); i++) {
    const value = step * i;
    add('line', {x1: 65, y1: y(value), x2: 845, y2: y(value), stroke: '#ddd'});
    add('text', {x: 55, y: y(value) + 4, 'text-anchor': 'end', 'font-size': 12}, Number(value.toPrecision(6)).toLocaleString('en-US'));
  }
  data.labels.forEach(function (label, i) {
    if (i % Math.max(1, Math.ceil(data.labels.length / 6)) === 0 || i === data.labels.length - 1) {
      add('text', {x: x(i), y: 265, 'text-anchor': 'middle', 'font-size': 12}, label + (partial[i] ? '*' : ''));
    }
  });
  data.series.forEach(function (series, index) {
    const color = colors[index % colors.length];
    let previous = null;
    series.values.forEach(function (value, i) {
      if (value === null) { previous = null; return; }
      if (!stacked && previous !== null) add('line', {x1: x(previous), y1: y(series.values[previous]), x2: x(i), y2: y(value), stroke: color, 'stroke-width': 3, 'stroke-dasharray': partial[i] || partial[previous] ? '5 4' : 'none'});
      let point;
      if (stacked) {
        const top = bases[i] + value;
        if (value === 0) return;
        point = add('rect', {x: x(i) - barWidth / 2, y: y(top), width: barWidth,
          height: y(bases[i]) - y(top), fill: color, tabindex: 0});
        bases[i] = top;
      } else {
        point = add('circle', {cx: x(i), cy: y(value), r: 4, fill: color, tabindex: 0});
      }
      point.setAttribute('opacity', partial[i] ? 0.5 : 1);
      const title = document.createElementNS(ns, 'title');
      title.textContent = data.labels[i] + ' — ' + series.name + ': ' + value + coverage(i);
      point.appendChild(title);
      previous = i;
    });
    const legendX = 65 + index * 260;
    add('rect', {x: legendX, y: 277, width: 16, height: 16, rx: 2, fill: color, 'aria-hidden': 'true'});
    add('text', {x: legendX + 24, y: 290, fill: '#1f2937', 'font-size': 14, 'font-weight': 500}, series.name);
  });
  container.appendChild(svg);
});
