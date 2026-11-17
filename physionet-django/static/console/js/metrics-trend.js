/* Tables remain available without JavaScript. Missing medians break the line. */
document.querySelectorAll('[data-metrics-chart]').forEach(function (container) {
  const data = JSON.parse(document.getElementById(container.dataset.metricsChart).textContent);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  const legendColumns = data.series.length > 3 ? 2 : 3;
  const showLegend = data.legend !== false;
  const legendRows = showLegend ? Math.ceil(data.series.length / legendColumns) : 1;
  svg.setAttribute('viewBox', '0 0 900 ' + (300 + (legendRows - 1) * 26));
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
  const stacked = data.type === 'stacked-bar' || data.type === 'stacked-bar-line';
  function isBar(series) { return stacked && series.type !== 'line'; }
  const totals = data.labels.map(function (_, i) {
    return data.series.reduce(function (total, series) {
      return total + (isBar(series) ? (series.values[i] || 0) : 0);
    }, 0);
  });
  const rawMaximum = Math.max(1, ...values, ...(stacked ? totals : []));
  const targetStep = rawMaximum / 4;
  const magnitude = Math.pow(10, Math.floor(Math.log10(targetStep)));
  const fraction = targetStep / magnitude;
  const factor = fraction < 1.5 ? 1 : fraction < 3.5 ? 2 : fraction < 7.5 ? 5 : 10;
  const step = (stacked || data.integer) ? Math.max(1, factor * magnitude) : factor * magnitude;
  const maximum = Math.ceil(rawMaximum / step) * step;
  const partial = data.partial || [];
  function coverage(i) {
    return partial[i] ? ' (partial ' + (data.period_unit || 'month') +
      (data.partial_through ? ', through ' + data.partial_through : '') + ')' : '';
  }
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
  function marker(shape, cx, cy, color, focusable) {
    const attrs = {fill: color};
    if (focusable) attrs.tabindex = 0;
    if (shape === 'square') return add('rect', {...attrs, x: cx - 4, y: cy - 4, width: 8, height: 8});
    if (shape === 'triangle') return add('polygon', {...attrs,
      points: cx + ',' + (cy - 5) + ' ' + (cx - 5) + ',' + (cy + 4) + ' ' + (cx + 5) + ',' + (cy + 4)});
    if (shape === 'diamond') return add('polygon', {...attrs,
      points: cx + ',' + (cy - 5) + ' ' + (cx - 5) + ',' + cy + ' ' + cx + ',' + (cy + 5) + ' ' + (cx + 5) + ',' + cy});
    return add('circle', {...attrs, cx: cx, cy: cy, r: 4});
  }
  data.series.forEach(function (series, index) {
    const color = series.color || colors[index % colors.length];
    const bar = isBar(series);
    let previous = null;
    series.values.forEach(function (value, i) {
      if (value === null) { previous = null; return; }
      if (!bar && previous !== null) {
        const attrs = {x1: x(previous), y1: y(series.values[previous]), x2: x(i), y2: y(value),
          stroke: color, 'stroke-width': 3};
        add('line', attrs);
      }
      let point;
      if (bar) {
        const top = bases[i] + value;
        if (value === 0) return;
        point = add('rect', {x: x(i) - barWidth / 2, y: y(top), width: barWidth,
          height: y(bases[i]) - y(top), fill: color, tabindex: 0});
        bases[i] = top;
      } else {
        point = marker(series.marker, x(i), y(value), color, true);
      }
      const title = document.createElementNS(ns, 'title');
      title.textContent = data.labels[i] + ' — ' + series.name + ': ' + value + coverage(i);
      point.appendChild(title);
      previous = i;
    });
    if (!showLegend) return;
    const legendX = 65 + (index % legendColumns) * (780 / legendColumns);
    const legendOffset = Math.floor(index / legendColumns) * 26;
    if (bar) {
      add('rect', {x: legendX, y: 277 + legendOffset, width: 16, height: 16, rx: 2, fill: color, 'aria-hidden': 'true'});
    } else {
      add('line', {x1: legendX, x2: legendX + 16, y1: 285 + legendOffset, y2: 285 + legendOffset, stroke: color, 'stroke-width': 3});
      marker(series.marker, legendX + 8, 285 + legendOffset, color, false);
    }
    add('text', {x: legendX + 24, y: 290 + legendOffset, fill: '#1f2937', 'font-size': 14, 'font-weight': 500}, series.name);
  });
  container.appendChild(svg);
});
