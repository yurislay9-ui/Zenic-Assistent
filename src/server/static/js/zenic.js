/**
 * Zenic-Agents Asistente — Custom JavaScript
 * Chart initialization helpers, HTMX event handlers, Alpine.js stores,
 * theme toggle, form validation helpers, toast notification system.
 */

/* ── Chart Initialization Helpers ──────────────────── */

const ZenicChart = {
  // Color palette for charts
  palette: [
    '#6366f1', '#3b82f6', '#22c55e', '#f59e0b',
    '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899',
    '#14b8a6', '#f97316', '#84cc16', '#64748b',
  ],

  // Default chart options for dark theme
  defaultOptions(title) {
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const gridColor = isDark ? '#2d3148' : '#e5e7eb';
    const tickColor = isDark ? '#94a3b8' : '#6b7280';

    return {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          display: false,
        },
        title: {
          display: !!title,
          text: title || '',
          color: tickColor,
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: tickColor },
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: tickColor },
          beginAtZero: true,
        },
      },
    };
  },

  // Create a line chart
  createLineChart(canvasId, labels, data, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: options.label || 'Data',
          data,
          borderColor: options.borderColor || '#6366f1',
          backgroundColor: options.fillColor || 'rgba(99,102,241,0.1)',
          fill: options.fill !== false,
          tension: options.tension || 0.4,
          pointRadius: options.pointRadius || 3,
        }],
      },
      options: this.defaultOptions(options.title),
    });
  },

  // Create a bar chart
  createBarChart(canvasId, labels, data, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: options.label || 'Data',
          data,
          backgroundColor: options.colors || this.palette.slice(0, data.length),
          borderWidth: options.borderWidth || 1,
          borderColor: options.borderColor || 'transparent',
        }],
      },
      options: this.defaultOptions(options.title),
    });
  },

  // Create a pie chart
  createPieChart(canvasId, labels, data, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'pie',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: options.colors || this.palette.slice(0, data.length),
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: options.legendPosition || 'bottom',
            labels: {
              color: document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#94a3b8' : '#6b7280',
            },
          },
        },
      },
    });
  },

  // Create a doughnut chart
  createDoughnutChart(canvasId, labels, data, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: options.colors || this.palette.slice(0, data.length),
        }],
      },
      options: {
        responsive: true,
        cutout: options.cutout || '60%',
        plugins: {
          legend: {
            position: options.legendPosition || 'bottom',
            labels: {
              color: document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#94a3b8' : '#6b7280',
            },
          },
        },
      },
    });
  },

  // Update chart data dynamically
  updateChart(chart, labels, data) {
    if (!chart) return;
    chart.data.labels = labels;
    chart.data.datasets[0].data = data;
    chart.update('none');
  },
};

/* ── Alpine.js Stores ─────────────────────────────── */

document.addEventListener('alpine:init', () => {
  // Global notification store
  Alpine.store('notifications', {
    items: [],
    add(message, type = 'info') {
      this.items.push({ id: Date.now(), message, type });
      setTimeout(() => this.remove(this.items[0]?.id), 4000);
    },
    remove(id) {
      this.items = this.items.filter(n => n.id !== id);
    },
  });

  // Global filter store
  Alpine.store('filters', {
    active: {},
    set(key, value) { this.active[key] = value; },
    get(key) { return this.active[key]; },
    clear() { this.active = {}; },
  });
});

/* ── ZenicApp Alpine Component ────────────────────── */

function ZenicApp() {
  return {
    sidebarOpen: true,
    darkMode: true,

    init() {
      // Restore theme from localStorage
      const savedTheme = localStorage.getItem('zenic-theme');
      if (savedTheme) {
        this.darkMode = savedTheme === 'dark';
        document.documentElement.setAttribute('data-bs-theme', this.darkMode ? 'dark' : 'light');
      }
    },
  };
}

/* ── Dashboard Store ──────────────────────────────── */

function dashboardStore() {
  return {
    metrics: {},
    init() { this.loadMetrics(); },
    async loadMetrics() {
      try {
        const r = await fetch('/htmx/dashboard/metrics');
        if (r.ok) this.metrics = await r.json();
      } catch(e) { console.error('Dashboard metrics error', e); }
    },
  };
}

/* ── HTMX Event Handlers ──────────────────────────── */

document.addEventListener('DOMContentLoaded', function() {
  // Show toast on HTMX errors
  document.body.addEventListener('htmx:responseError', function(evt) {
    ZenicToast.show('Error de conexión: ' + (evt.detail.xhr?.status || 'desconocido'), 'danger');
  });

  // Show toast on HTMX after swap for confirmation messages
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    const target = evt.detail.target;
    if (target && target.querySelector && target.querySelector('[data-zenic-notify]')) {
      const el = target.querySelector('[data-zenic-notify]');
      ZenicToast.show(el.dataset.zenicNotify, el.dataset.zenicType || 'success');
    }
  });

  // Add CSRF header to HTMX requests
  document.body.addEventListener('htmx:configRequest', function(evt) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) {
      evt.detail.headers['X-CSRF-Token'] = csrfMeta.content;
    }
  });
});

/* ── Theme Toggle ─────────────────────────────────── */

const ZenicTheme = {
  toggle() {
    const html = document.documentElement;
    const current = html.getAttribute('data-bs-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-bs-theme', next);
    localStorage.setItem('zenic-theme', next);

    // Refresh charts with new theme colors
    ZenicTheme.refreshCharts();
  },

  refreshCharts() {
    // Trigger chart re-render by dispatching custom event
    window.dispatchEvent(new CustomEvent('zenic:theme-changed'));
  },

  isDark() {
    return document.documentElement.getAttribute('data-bs-theme') === 'dark';
  },
};

/* ── Form Validation Helpers ──────────────────────── */

const ZenicForm = {
  // Validate required fields
  validateRequired(formEl) {
    let valid = true;
    formEl.querySelectorAll('[required]').forEach(field => {
      if (!field.value.trim()) {
        field.classList.add('is-invalid');
        valid = false;
      } else {
        field.classList.remove('is-invalid');
      }
    });
    return valid;
  },

  // Validate email format
  validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  },

  // Show validation error on field
  showError(field, message) {
    field.classList.add('is-invalid');
    let feedback = field.nextElementSibling;
    if (!feedback || !feedback.classList.contains('invalid-feedback')) {
      feedback = document.createElement('div');
      feedback.className = 'invalid-feedback';
      field.parentNode.insertBefore(feedback, field.nextSibling);
    }
    feedback.textContent = message;
  },

  // Clear validation errors
  clearErrors(formEl) {
    formEl.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
  },

  // Serialize form to JSON
  serializeForm(formEl) {
    const data = {};
    new FormData(formEl).forEach((value, key) => {
      data[key] = value;
    });
    return data;
  },
};

/* ── Toast Notification System ────────────────────── */

const ZenicToast = {
  show(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const id = Date.now();
    const icons = {
      info: 'bi-info-circle',
      success: 'bi-check-circle',
      warning: 'bi-exclamation-triangle',
      danger: 'bi-x-circle',
    };

    const toastEl = document.createElement('div');
    toastEl.className = `toast show toast-${type} zenic-fade-in`;
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
      <div class="toast-body d-flex align-items-center gap-2">
        <i class="bi ${icons[type] || icons.info}"></i>
        <span>${message}</span>
        <button type="button" class="btn-close btn-close-white ms-auto" onclick="this.closest('.toast').remove()"></button>
      </div>
    `;

    container.appendChild(toastEl);
    setTimeout(() => {
      toastEl.style.opacity = '0';
      toastEl.style.transform = 'translateX(100%)';
      toastEl.style.transition = 'all 0.3s ease';
      setTimeout(() => toastEl.remove(), 300);
    }, duration);
  },
};

/* ── Utility Functions ─────────────────────────────── */

const ZenicUtil = {
  // Format number with commas
  formatNumber(n) {
    return Number(n || 0).toLocaleString();
  },

  // Format currency
  formatCurrency(n, currency = 'USD') {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n || 0);
  },

  // Format timestamp to locale string
  formatTimestamp(ts) {
    if (!ts) return '--';
    return new Date(ts * 1000).toLocaleString('es');
  },

  // Format date relative (e.g., "2 hours ago")
  timeAgo(ts) {
    if (!ts) return '--';
    const seconds = Math.floor((Date.now() / 1000) - ts);
    if (seconds < 60) return 'justo ahora';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' min';
    if (seconds < 86400) return Math.floor(seconds / 3600) + ' h';
    return Math.floor(seconds / 86400) + ' días';
  },

  // Debounce function
  debounce(fn, delay = 300) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), delay);
    };
  },
};

// Make helpers globally available
window.ZenicChart = ZenicChart;
window.ZenicTheme = ZenicTheme;
window.ZenicForm = ZenicForm;
window.ZenicToast = ZenicToast;
window.ZenicUtil = ZenicUtil;
window.ZenicApp = ZenicApp;
window.dashboardStore = dashboardStore;
