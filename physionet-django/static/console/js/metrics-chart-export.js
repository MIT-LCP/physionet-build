/* Export the visible SVG and its selected legend locally; no data leaves the browser. */
document.querySelectorAll('[data-metrics-chart]').forEach(function (container) {
  const data = JSON.parse(document.getElementById(container.dataset.metricsChart).textContent);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn btn-sm metrics-download';
  button.dataset.metricsExport = '';
  button.textContent = 'Download chart (PNG)';
  button.setAttribute('aria-label', 'Download chart (PNG): ' + (container.dataset.title || container.dataset.label));
  const error = document.createElement('p');
  error.className = 'small text-danger';
  error.setAttribute('role', 'status');
  error.hidden = true;
  const actions = Array.from(document.querySelectorAll('[data-chart-downloads-for]')).find(function (node) {
    return node.dataset.chartDownloadsFor === container.dataset.metricsChart;
  });
  if (!actions) return;
  actions.prepend(button);
  actions.appendChild(error);
  error.classList.add('metrics-export-error');
  let exporting = false;

  function visibleSeries() {
    const boxes = container.querySelectorAll('input[type="checkbox"]');
    return data.series.filter(function (_, i) { return !boxes.length || boxes[i].checked; });
  }
  function updateButton() {
    button.disabled = exporting || visibleSeries().length === 0;
  }
  container.addEventListener('change', updateButton);
  container.addEventListener('click', updateButton);
  updateButton();

  function wrap(context, text, width) {
    const lines = [];
    let line = '';
    Array.from(text).forEach(function (character) {
      if (line && context.measureText(line + character).width > width) {
        lines.push(line.trim());
        line = '';
      }
      line += character;
    });
    if (line.trim()) lines.push(line.trim());
    return lines;
  }

  button.addEventListener('click', async function () {
    exporting = true;
    updateButton();
    error.hidden = true;
    let imageURL;
    try {
      const svg = container.querySelector('svg').cloneNode(true);
      const width = 900;
      const height = Number(svg.getAttribute('viewBox').split(/\s+/)[3]);
      svg.setAttribute('width', width);
      svg.setAttribute('height', height);
      svg.style.width = width + 'px';
      svg.style.fontFamily = 'Arial, sans-serif';
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      context.font = 'bold 20px Arial';
      const title = container.dataset.title || container.dataset.label.split('.')[0];
      const titleLines = wrap(context, title, width - 64);
      const period = container.closest('[data-metrics-start]');
      const start = period ? period.dataset.metricsStart : '';
      const end = period ? period.dataset.metricsEnd : '';
      const top = 32 + titleLines.length * 26 + (start && end ? 24 : 0);
      const selected = visibleSeries();
      context.font = '14px Arial';
      const legend = data.interactive_legend ? selected.map(function (series) {
        return {series: series, lines: wrap(context, series.name, 350)};
      }) : [];
      const legendRows = [];
      for (let i = 0; i < legend.length; i += 2) {
        legendRows.push(Math.max(legend[i].lines.length, legend[i + 1] ? legend[i + 1].lines.length : 0) * 18 + 14);
      }
      const partial = (data.partial || []).some(Boolean);
      const footer = partial ? 32 : 0;
      canvas.width = width * 2;
      canvas.height = (top + height + legendRows.reduce(function (sum, value) { return sum + value; }, 0) + footer + 24) * 2;
      context.scale(2, 2);
      context.fillStyle = '#fff';
      context.fillRect(0, 0, canvas.width / 2, canvas.height / 2);
      context.fillStyle = '#1f2937';
      context.font = 'bold 20px Arial';
      titleLines.forEach(function (line, i) { context.fillText(line, 32, 30 + i * 26); });
      if (start && end) {
        context.font = '14px Arial';
        context.fillText(start + ' to ' + end, 32, top - 12);
      }
      const serialized = new XMLSerializer().serializeToString(svg);
      imageURL = URL.createObjectURL(new Blob([serialized], {type: 'image/svg+xml;charset=utf-8'}));
      const image = new Image();
      await new Promise(function (resolve, reject) {
        image.onload = resolve;
        image.onerror = reject;
        image.src = imageURL;
      });
      context.drawImage(image, 0, top, width, height);
      const symbols = {circle: '●', square: '■', triangle: '▲', diamond: '◆', plus: '✚', cross: '×',
        'triangle-down': '▼', hexagon: '⬢', pentagon: '⬟', star: '★'};
      let y = top + height + 10;
      context.font = '14px Arial';
      legend.forEach(function (item, index) {
        const x = 65 + (index % 2) * 390;
        context.fillStyle = item.series.color;
        context.fillText(symbols[item.series.marker] || '●', x, y + 14);
        context.fillStyle = '#1f2937';
        item.lines.forEach(function (line, i) { context.fillText(line, x + 24, y + 14 + i * 18); });
        if (index % 2 || index === legend.length - 1) y += legendRows[Math.floor(index / 2)];
      });
      if (partial) {
        context.fillStyle = '#b45309';
        context.fillText('*', 32, y + 20);
        context.fillStyle = '#4b5563';
        context.fillText('Partial ' + (data.period_unit || 'month'), 44, y + 20);
      }
      const png = await new Promise(function (resolve) { canvas.toBlob(resolve, 'image/png'); });
      if (!png) throw new Error('PNG export failed');
      const downloadURL = URL.createObjectURL(png);
      const link = document.createElement('a');
      link.href = downloadURL;
      link.download = container.dataset.metricsChart + (start && end ? '-' + start + '-' + end : '') + '.png';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(downloadURL); }, 1000);
    } catch (_) {
      error.textContent = 'Could not export the image. Please try again.';
      error.hidden = false;
    } finally {
      if (imageURL) URL.revokeObjectURL(imageURL);
      exporting = false;
      updateButton();
    }
  });
});
