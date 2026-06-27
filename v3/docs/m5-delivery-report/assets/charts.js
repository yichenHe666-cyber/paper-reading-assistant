(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var green = style.getPropertyValue('--green').trim();

  // --- Chart 1: Code Scale ---
  var chart1 = echarts.init(document.getElementById('chart-code-scale'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      formatter: function(params) {
        return params[0].name + '<br/>' + params[0].value.toLocaleString() + ' 行';
      }
    },
    grid: { left: '8%', right: '8%', top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['Go 后端', 'Rust 核心', 'TypeScript 前端'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 13 }
    },
    yAxis: {
      type: 'value',
      name: '行数',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 7398, itemStyle: { color: green } },
        { value: 2061, itemStyle: { color: accent2 } },
        { value: 1882, itemStyle: { color: '#1565c0' } }
      ],
      barWidth: '45%',
      label: {
        show: true,
        position: 'top',
        color: ink,
        fontSize: 13,
        fontWeight: 700,
        formatter: function(params) {
          return params.value.toLocaleString();
        }
      }
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // --- Chart 2: Review Scores ---
  var chart2 = echarts.init(document.getElementById('chart-review-scores'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      formatter: function(params) {
        return params[0].name + '<br/>评分：' + params[0].value + ' / 10';
      }
    },
    grid: { left: '8%', right: '8%', top: 30, bottom: 30 },
    xAxis: {
      type: 'value',
      max: 10,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'category',
      data: ['Rust 核心', 'Go 后端', '前端'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 13 }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 6.0, itemStyle: { color: accent2 } },
        { value: 6.5, itemStyle: { color: accent } },
        { value: 6.5, itemStyle: { color: '#1565c0' } }
      ],
      barWidth: '50%',
      label: {
        show: true,
        position: 'right',
        color: ink,
        fontSize: 13,
        fontWeight: 700,
        formatter: '{c} / 10'
      }
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // --- Chart 3: Test Distribution ---
  var chart3 = echarts.init(document.getElementById('chart-test-distribution'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      appendToBody: true,
      formatter: '{b}<br/>{c} 项 ({d}%)'
    },
    legend: {
      bottom: 10,
      textStyle: { color: ink, fontSize: 13 }
    },
    series: [{
      type: 'pie',
      radius: ['35%', '65%'],
      center: ['50%', '45%'],
      data: [
        { value: 79, name: 'Go 后端', itemStyle: { color: green } },
        { value: 19, name: 'Rust 核心', itemStyle: { color: accent2 } }
      ],
      label: {
        show: true,
        color: ink,
        fontSize: 13,
        fontWeight: 700,
        formatter: '{b}\n{c} 项'
      },
      labelLine: { lineStyle: { color: muted } }
    }]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
