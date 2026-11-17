/* Tables remain available without JavaScript. Missing medians break the line. */
document.querySelectorAll('[data-metrics-chart]').forEach(function (container) {
  const original = JSON.parse(document.getElementById(container.dataset.metricsChart).textContent);
  const selected = original.series.map(function () { return true; });
  function render() {
    const previous = container.querySelector('svg');
    if (previous) previous.remove();
    const data = {...original, series: original.series.filter(function (_, i) { return selected[i]; })};
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    const legendColumns = data.series.length > 3 ? 2 : 3;
    const showLegend = data.legend !== false && !data.interactive_legend;
    const legendRows = showLegend ? Math.ceil(data.series.length / legendColumns) : 1;
    const plotHeight = data.plot_height || 190;
    const extraHeight = plotHeight - 190;
    svg.setAttribute('viewBox', '0 0 900 ' + (300 + extraHeight + (legendRows - 1) * 26));
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
    if (data.type === 'pie') {
      svg.setAttribute('viewBox', '0 0 900 330');
      const total = data.series.reduce(function (sum, series) { return sum + series.values[0]; }, 0);
      let angle = -Math.PI / 2;
      if (total === 0) add('text', {x: 450, y: 160, 'text-anchor': 'middle'}, 'No viewers in the selected period.');
      data.series.forEach(function (series, index) {
        const count = series.values[0];
        const color = series.color || colors[index % colors.length];
        if (count > 0) {
          const next = angle + count / total * Math.PI * 2;
          let slice;
          if (count === total) slice = add('circle', {cx: 180, cy: 155, r: 115, fill: color, tabindex: 0});
          else {
            const x1 = 180 + 115 * Math.cos(angle), y1 = 155 + 115 * Math.sin(angle);
            const x2 = 180 + 115 * Math.cos(next), y2 = 155 + 115 * Math.sin(next);
            slice = add('path', {d: 'M180,155 L' + x1 + ',' + y1 + ' A115,115 0 ' +
              (next - angle > Math.PI ? 1 : 0) + ',1 ' + x2 + ',' + y2 + ' Z', fill: color, tabindex: 0});
          }
          const title = document.createElementNS(ns, 'title');
          title.textContent = series.name + ': ' + count.toLocaleString('en-US') + ' (' +
            (count * 100 / total).toFixed(2) + '%)';
          slice.appendChild(title);
          angle = next;
        }
        const shortName = series.name.startsWith('New accounts') ? 'New accounts' :
          series.name.startsWith('Existing accounts') ? 'Existing accounts' : 'Account creation date unavailable';
        add('rect', {x: 350, y: 75 + index * 65, width: 16, height: 16, fill: color});
        add('text', {x: 380, y: 88 + index * 65, 'font-size': 16}, shortName);
        add('text', {x: 380, y: 110 + index * 65, 'font-size': 14}, count.toLocaleString('en-US') +
          ' (' + (total ? count * 100 / total : 0).toFixed(2) + '%)');
      });
      container.prepend(svg);
      return;
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
    function y(v) { return 240 + extraHeight - v * plotHeight / maximum; }
    for (let i = 0; i <= Math.round(maximum / step); i++) {
      const value = step * i;
      add('line', {x1: 65, y1: y(value), x2: 845, y2: y(value), stroke: '#ddd'});
      add('text', {x: 55, y: y(value) + 4, 'text-anchor': 'end', 'font-size': 12}, Number(value.toPrecision(6)).toLocaleString('en-US'));
    }
    data.labels.forEach(function (label, i) {
      if (i % Math.max(1, Math.ceil(data.labels.length / 6)) === 0 || i === data.labels.length - 1 || partial[i]) {
        const tick = add('text', {x: x(i), y: 265 + extraHeight, 'text-anchor': 'middle', 'font-size': 12}, label);
        if (partial[i]) {
          const star = document.createElementNS(ns, 'tspan');
          star.setAttribute('fill', '#b45309');
          star.setAttribute('font-weight', '700');
          star.setAttribute('font-size', '16');
          star.textContent = '*';
          tick.appendChild(star);
        }
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
      if (shape === 'triangle-down') return add('polygon', {...attrs,
        points: cx + ',' + (cy + 5) + ' ' + (cx - 5) + ',' + (cy - 4) + ' ' + (cx + 5) + ',' + (cy - 4)});
      if (shape === 'hexagon') return add('polygon', {...attrs,
        points: [[-5, 0], [-2.5, -4], [2.5, -4], [5, 0], [2.5, 4], [-2.5, 4]]
          .map(function (p) { return (cx + p[0]) + ',' + (cy + p[1]); }).join(' ')});
      if (shape === 'pentagon' || shape === 'star') {
        const steps = shape === 'star' ? 10 : 5;
        const points = Array.from({length: steps}, function (_, i) {
          const angle = -Math.PI / 2 + i * 2 * Math.PI / steps;
          const radius = shape === 'star' && i % 2 ? 2.5 : 5;
          return (cx + Math.cos(angle) * radius) + ',' + (cy + Math.sin(angle) * radius);
        }).join(' ');
        return add('polygon', {...attrs, points: points});
      }
      if (shape === 'plus' || shape === 'cross') {
        const d = shape === 'plus' ? 'M-5,0 H5 M0,-5 V5' : 'M-4,-4 L4,4 M-4,4 L4,-4';
        return add('path', {...attrs, d: d, transform: 'translate(' + cx + ' ' + cy + ')',
          fill: 'none', stroke: color, 'stroke-width': 2.5});
      }
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
            stroke: color, 'stroke-width': data.line_width || 3};
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
      const legendOffset = extraHeight + Math.floor(index / legendColumns) * 26;
      if (bar) {
        add('rect', {x: legendX, y: 277 + legendOffset, width: 16, height: 16, rx: 2, fill: color, 'aria-hidden': 'true'});
      } else {
        add('line', {x1: legendX, x2: legendX + 16, y1: 285 + legendOffset, y2: 285 + legendOffset, stroke: color, 'stroke-width': 3});
        marker(series.marker, legendX + 8, 285 + legendOffset, color, false);
      }
      add('text', {x: legendX + 24, y: 290 + legendOffset, fill: '#1f2937', 'font-size': 14, 'font-weight': 500}, series.name);
    });
    container.prepend(svg);
  }
  if (original.interactive_legend) {
    const status = document.createElement('p');
    status.className = 'small text-muted';
    status.setAttribute('role', 'status');
    status.hidden = true;
    status.textContent = 'No series selected. Select an item below to show its trend.';
    container.appendChild(status);
    const toolbar = document.createElement('div');
    toolbar.className = 'metrics-series-toolbar';
    const selectAll = document.createElement('button');
    const deselectAll = document.createElement('button');
    selectAll.type = deselectAll.type = 'button';
    selectAll.className = deselectAll.className = 'btn btn-sm btn-outline-secondary';
    selectAll.textContent = 'Select all';
    deselectAll.textContent = 'Deselect all';
    const summary = document.createElement('span');
    summary.className = 'small text-muted';
    summary.setAttribute('aria-live', 'polite');
    toolbar.append(selectAll, deselectAll, summary);
    container.appendChild(toolbar);
    const inputs = [];
    function updateControls() {
      const count = selected.filter(Boolean).length;
      summary.textContent = count + ' of ' + selected.length + ' shown';
      selectAll.disabled = count === selected.length;
      deselectAll.disabled = count === 0;
      status.hidden = count > 0;
    }
    function setAll(visible) {
      inputs.forEach(function (checkbox, index) {
        checkbox.checked = selected[index] = visible;
        checkbox.closest('label').classList.toggle('metrics-series-hidden', !visible);
      });
      updateControls();
      render();
    }
    selectAll.addEventListener('click', function () { setAll(true); });
    deselectAll.addEventListener('click', function () { setAll(false); });
    const legend = document.createElement('fieldset');
    legend.className = 'metrics-series-controls';
    const heading = document.createElement('legend');
    heading.className = 'sr-only';
    heading.textContent = original.legend_title || 'Visible researcher categories';
    legend.appendChild(heading);
    const symbols = {circle: '●', square: '■', triangle: '▲', diamond: '◆',
      plus: '✚', cross: '×', 'triangle-down': '▼', hexagon: '⬢', pentagon: '⬟', star: '★'};
    original.series.forEach(function (series, index) {
      const label = document.createElement('label');
      label.className = 'metrics-series-option';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = true;
      inputs.push(checkbox);
      checkbox.id = container.dataset.metricsChart + '-series-' + index;
      const swatch = document.createElement('span');
      swatch.className = 'metrics-series-symbol';
      swatch.style.color = series.color || '#2563eb';
      swatch.setAttribute('aria-hidden', 'true');
      swatch.textContent = symbols[series.marker] || '●';
      label.appendChild(checkbox);
      label.appendChild(swatch);
      const name = document.createElement('span');
      name.className = 'metrics-series-name';
      name.textContent = series.name;
      label.appendChild(name);
      label.title = series.period_count.toLocaleString('en-US') + ' unique viewers across the selected period';
      checkbox.addEventListener('change', function () {
        selected[index] = checkbox.checked;
        label.classList.toggle('metrics-series-hidden', !checkbox.checked);
        updateControls();
        render();
      });
      legend.appendChild(label);
    });
    container.appendChild(legend);
    updateControls();
  }
  render();
});
