/**
 * Zenic-Agents — Dashboard JS (Phase 7.2)
 * Alpine.js data + Chart.js initialization + HTMX helpers.
 */

function dashboardData() {
  return {
    metrics: {
      sales_today: '--',
      sales_change: 0,
      pending_invoices: 0,
      active_alerts: 0,
      system_mode: 'NORMAL',
    },

    init() {
      this.loadMetrics();
      this.initCharts();
    },

    async loadMetrics() {
      try {
        const resp = await fetch('/htmx/dashboard/metrics');
        if (resp.ok) {
          const data = await resp.json();
          this.metrics = { ...this.metrics, ...data };
        }
      } catch (e) {
        console.error('Dashboard: metrics load failed', e);
      }
    },

    initCharts() {
      // Sales chart (7-day line)
      const salesCtx = document.getElementById('chart-sales');
      if (salesCtx) {
        fetch('/htmx/dashboard/sales-chart').then(r => r.json()).then(data => {
          new Chart(salesCtx, {
            type: 'line',
            data: {
              labels: data.labels || ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'],
              datasets: [{
                label: 'Ventas',
                data: data.values || [0, 0, 0, 0, 0, 0, 0],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99,102,241,0.1)',
                fill: true,
                tension: 0.4,
              }],
            },
            options: {
              responsive: true,
              plugins: { legend: { display: false } },
              scales: {
                x: { grid: { color: '#2d3148' }, ticks: { color: '#94a3b8' } },
                y: { grid: { color: '#2d3148' }, ticks: { color: '#94a3b8' } },
              },
            },
          });
        }).catch(() => {});
      }

      // Executor actions chart (doughnut)
      const execCtx = document.getElementById('chart-executors');
      if (execCtx) {
        fetch('/htmx/dashboard/executor-chart').then(r => r.json()).then(data => {
          new Chart(execCtx, {
            type: 'doughnut',
            data: {
              labels: data.labels || ['Email', 'HTTP', 'DB', 'File', 'Notify', 'Schedule', 'Webhook', 'Transform'],
              datasets: [{
                data: data.values || [1, 1, 1, 1, 1, 1, 1, 1],
                backgroundColor: ['#6366f1', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899'],
              }],
            },
            options: {
              responsive: true,
              plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8' } } },
            },
          });
        }).catch(() => {});
      }
    },
  };
}
