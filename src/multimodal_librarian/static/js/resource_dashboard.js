/**
 * Resource Usage Dashboard JavaScript
 * 
 * Provides interactive functionality for the resource usage dashboard including:
 * - Real-time data updates
 * - Chart rendering and updates
 * - Dashboard navigation
 * - Monitoring controls
 * - Alert management
 * - Optimization recommendations display
 */

class ResourceDashboard {
    constructor() {
        this.charts = {};
        this.currentDashboard = 'system_resources';
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds
        this.isMonitoring = false;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeCharts();
        this.checkServiceStatus();
        this.loadDashboardData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        // Navigation buttons
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchDashboard(e.target.dataset.dashboard);
            });
        });

        // Control buttons
        document.getElementById('start-monitoring-btn').addEventListener('click', () => {
            this.startMonitoring();
        });

        document.getElementById('stop-monitoring-btn').addEventListener('click', () => {
            this.stopMonitoring();
        });

        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.refreshDashboard();
        });

        // Modal close
        document.querySelector('.modal-close').addEventListener('click', () => {
            this.closeErrorModal();
        });

        // Close modal on background click
        document.getElementById('error-modal').addEventListener('click', (e) => {
            if (e.target.id === 'error-modal') {
                this.closeErrorModal();
            }
        });
    }

    initializeCharts() {
        // System CPU Chart
        const cpuCtx = document.getElementById('system-cpu-chart').getContext('2d');
        this.charts.systemCpu = new Chart(cpuCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'CPU Usage (%)',
                    data: [],
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function (value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });

        // System Memory Chart
        const memoryCtx = document.getElementById('system-memory-chart').getContext('2d');
        this.charts.systemMemory = new Chart(memoryCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Memory Usage (%)',
                    data: [],
                    borderColor: '#2ecc71',
                    backgroundColor: 'rgba(46, 204, 113, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function (value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });

        // System Disk Chart (Gauge)
        const diskCtx = document.getElementById('system-disk-chart').getContext('2d');
        this.charts.systemDisk = new Chart(diskCtx, {
            type: 'doughnut',
            data: {
                labels: ['Used', 'Free'],
                datasets: [{
                    data: [0, 100],
                    backgroundColor: ['#f39c12', '#ecf0f1'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });

        // Container Memory Chart
        const containerMemoryCtx = document.getElementById('container-memory-chart').getContext('2d');
        this.charts.containerMemory = new Chart(containerMemoryCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Memory Usage (MB)',
                    data: [],
                    backgroundColor: '#9b59b6',
                    borderColor: '#8e44ad',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value + ' MB';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });

        // Container CPU Chart
        const containerCpuCtx = document.getElementById('container-cpu-chart').getContext('2d');
        this.charts.containerCpu = new Chart(containerCpuCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'CPU Usage (%)',
                    data: [],
                    backgroundColor: '#e67e22',
                    borderColor: '#d35400',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });

        // Total Container Resources Chart
        const totalContainerCtx = document.getElementById('total-container-chart').getContext('2d');
        this.charts.totalContainer = new Chart(totalContainerCtx, {
            type: 'pie',
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    backgroundColor: [
                        '#3498db', '#2ecc71', '#f39c12',
                        '#e74c3c', '#9b59b6', '#1abc9c'
                    ],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });

        // Resource Trends Chart
        const trendsCtx = document.getElementById('trends-chart').getContext('2d');
        this.charts.trends = new Chart(trendsCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'CPU',
                        data: [],
                        borderColor: '#3498db',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        borderWidth: 2,
                        fill: false
                    },
                    {
                        label: 'Memory',
                        data: [],
                        borderColor: '#2ecc71',
                        backgroundColor: 'rgba(46, 204, 113, 0.1)',
                        borderWidth: 2,
                        fill: false
                    },
                    {
                        label: 'Disk',
                        data: [],
                        borderColor: '#f39c12',
                        backgroundColor: 'rgba(243, 156, 18, 0.1)',
                        borderWidth: 2,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function (value) {
                                return value + '%';
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top'
                    }
                }
            }
        });

        // Efficiency Score Chart
        const efficiencyCtx = document.getElementById('efficiency-score-chart').getContext('2d');
        this.charts.efficiencyScore = new Chart(efficiencyCtx, {
            type: 'doughnut',
            data: {
                labels: ['Score', 'Remaining'],
                datasets: [{
                    data: [0, 100],
                    backgroundColor: ['#2ecc71', '#ecf0f1'],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '80%',
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    switchDashboard(dashboardId) {
        // Update navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-dashboard="${dashboardId}"]`).classList.add('active');

        // Update panels
        document.querySelectorAll('.dashboard-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        document.getElementById(dashboardId).classList.add('active');

        this.currentDashboard = dashboardId;
        this.loadDashboardData();
    }

    async checkServiceStatus() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/status');
            const result = await response.json();

            if (result.success) {
                this.updateServiceStatus(result.data);
            }
        } catch (error) {
            console.error('Error checking service status:', error);
        }
    }

    updateServiceStatus(status) {
        this.isMonitoring = status.monitoring.active;

        // Update monitoring indicator
        const indicator = document.getElementById('monitoring-indicator');
        const text = document.getElementById('monitoring-text');

        if (this.isMonitoring) {
            indicator.className = 'status-indicator active';
            text.textContent = 'Monitoring Active';
        } else {
            indicator.className = 'status-indicator inactive';
            text.textContent = 'Monitoring Inactive';
        }

        // Update buttons
        document.getElementById('start-monitoring-btn').disabled = this.isMonitoring;
        document.getElementById('stop-monitoring-btn').disabled = !this.isMonitoring;

        // Update status bar
        document.getElementById('docker-status').textContent =
            status.monitoring.docker_available ? 'Available' : 'Unavailable';
        document.getElementById('samples-count').textContent =
            status.statistics.resource_history_samples;
        document.getElementById('containers-count').textContent =
            status.statistics.monitored_containers;
    }

    async startMonitoring() {
        try {
            this.showLoading();
            const response = await fetch('/api/v1/resource-dashboard/monitoring/start', {
                method: 'POST'
            });
            const result = await response.json();

            if (result.success) {
                this.isMonitoring = true;
                this.updateServiceStatus({
                    monitoring: { active: true, docker_available: result.data.docker_available },
                    statistics: { resource_history_samples: 0, monitored_containers: 0 }
                });
                this.showSuccess('Resource monitoring started successfully');
            } else {
                this.showError('Failed to start monitoring: ' + result.message);
            }
        } catch (error) {
            this.showError('Error starting monitoring: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }

    async stopMonitoring() {
        try {
            this.showLoading();
            const response = await fetch('/api/v1/resource-dashboard/monitoring/stop', {
                method: 'POST'
            });
            const result = await response.json();

            if (result.success) {
                this.isMonitoring = false;
                this.updateServiceStatus({
                    monitoring: { active: false, docker_available: false },
                    statistics: { resource_history_samples: 0, monitored_containers: 0 }
                });
                this.showSuccess('Resource monitoring stopped successfully');
            } else {
                this.showError('Failed to stop monitoring: ' + result.message);
            }
        } catch (error) {
            this.showError('Error stopping monitoring: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }

    async loadDashboardData() {
        try {
            // Load system metrics
            await this.loadSystemMetrics();

            // Load container metrics if on container dashboard
            if (this.currentDashboard === 'container_resources') {
                await this.loadContainerMetrics();
            }

            // Load trends if on trends dashboard
            if (this.currentDashboard === 'resource_trends') {
                await this.loadTrends();
                await this.loadOptimizationRecommendations();
                await this.loadEfficiencyAnalysis();
            }

            // Load alerts for all dashboards
            await this.loadAlerts();

            // Update last updated time
            document.getElementById('last-updated').textContent =
                new Date().toLocaleTimeString();

        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    async loadSystemMetrics() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/metrics/system');
            const result = await response.json();

            if (result.success && result.data.status !== 'no_data') {
                this.updateSystemCharts(result.data);
            }
        } catch (error) {
            console.error('Error loading system metrics:', error);
        }
    }

    updateSystemCharts(data) {
        // Update CPU chart
        const cpuChart = this.charts.systemCpu;
        const now = new Date().toLocaleTimeString();

        cpuChart.data.labels.push(now);
        cpuChart.data.datasets[0].data.push(data.cpu.percent);

        // Keep only last 30 data points
        if (cpuChart.data.labels.length > 30) {
            cpuChart.data.labels.shift();
            cpuChart.data.datasets[0].data.shift();
        }

        cpuChart.update('none');

        // Update Memory chart
        const memoryChart = this.charts.systemMemory;
        memoryChart.data.labels.push(now);
        memoryChart.data.datasets[0].data.push(data.memory.percent);

        if (memoryChart.data.labels.length > 30) {
            memoryChart.data.labels.shift();
            memoryChart.data.datasets[0].data.shift();
        }

        memoryChart.update('none');

        // Update Disk chart
        const diskChart = this.charts.systemDisk;
        diskChart.data.datasets[0].data = [data.disk.percent, 100 - data.disk.percent];
        diskChart.update('none');

        // Update current values and status
        document.getElementById('cpu-current').textContent = data.cpu.percent.toFixed(1) + '%';
        document.getElementById('cpu-status').textContent = data.cpu.status;
        document.getElementById('cpu-status').className = `chart-status ${data.cpu.status}`;

        document.getElementById('memory-current').textContent = data.memory.percent.toFixed(1) + '%';
        document.getElementById('memory-status').textContent = data.memory.status;
        document.getElementById('memory-status').className = `chart-status ${data.memory.status}`;

        document.getElementById('disk-current').textContent = data.disk.percent.toFixed(1) + '%';
        document.getElementById('disk-status').textContent = data.disk.status;
        document.getElementById('disk-status').className = `chart-status ${data.disk.status}`;
    }

    async loadContainerMetrics() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/metrics/containers');
            const result = await response.json();

            if (result.success && result.data.docker_available) {
                this.updateContainerCharts(result.data);
                this.updateContainerEfficiencyTable(result.data);
            }
        } catch (error) {
            console.error('Error loading container metrics:', error);
        }
    }

    updateContainerCharts(data) {
        const containers = Object.entries(data.containers);

        // Update container memory chart
        const memoryChart = this.charts.containerMemory;
        memoryChart.data.labels = containers.map(([name]) => name);
        memoryChart.data.datasets[0].data = containers.map(([, metrics]) => metrics.memory_usage_mb);
        memoryChart.update();

        // Update container CPU chart
        const cpuChart = this.charts.containerCpu;
        cpuChart.data.labels = containers.map(([name]) => name);
        cpuChart.data.datasets[0].data = containers.map(([, metrics]) => metrics.cpu_percent);
        cpuChart.update();

        // Update total container resources chart
        const totalChart = this.charts.totalContainer;
        totalChart.data.labels = containers.map(([name]) => name);
        totalChart.data.datasets[0].data = containers.map(([, metrics]) => metrics.memory_usage_mb);
        totalChart.update();
    }

    updateContainerEfficiencyTable(data) {
        const containers = Object.entries(data.containers);
        const tableContainer = document.getElementById('efficiency-table');

        if (containers.length === 0) {
            tableContainer.innerHTML = '<div class="no-data">No container data available</div>';
            return;
        }

        let tableHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Container</th>
                        <th>Memory Usage</th>
                        <th>CPU Usage</th>
                        <th>Status</th>
                        <th>Efficiency</th>
                    </tr>
                </thead>
                <tbody>
        `;

        containers.forEach(([name, metrics]) => {
            const memoryEfficiency = this.calculateEfficiency(metrics.memory_percent, 40, 80);
            const cpuEfficiency = this.calculateEfficiency(metrics.cpu_percent, 20, 70);

            tableHTML += `
                <tr>
                    <td>${name}</td>
                    <td>${metrics.memory_usage_mb.toFixed(1)} MB (${metrics.memory_percent.toFixed(1)}%)</td>
                    <td>${metrics.cpu_percent.toFixed(1)}%</td>
                    <td><span class="chart-status ${metrics.health_status}">${metrics.health_status}</span></td>
                    <td>M: ${memoryEfficiency}, C: ${cpuEfficiency}</td>
                </tr>
            `;
        });

        tableHTML += '</tbody></table>';
        tableContainer.innerHTML = tableHTML;
    }

    calculateEfficiency(value, optimalMin, optimalMax) {
        if (value >= optimalMin && value <= optimalMax) {
            return 'Optimal';
        } else if (value < optimalMin) {
            return 'Under-utilized';
        } else {
            return 'Over-utilized';
        }
    }

    async loadTrends() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/trends?hours=24');
            const result = await response.json();

            if (result.success && result.data.trends) {
                this.updateTrendsChart(result.data.trends);
            }
        } catch (error) {
            console.error('Error loading trends:', error);
        }
    }

    updateTrendsChart(trends) {
        const trendsChart = this.charts.trends;

        // Sample data points (take every 10th point to avoid overcrowding)
        const sampledTrends = trends.filter((_, index) => index % 10 === 0);

        trendsChart.data.labels = sampledTrends.map(trend =>
            new Date(trend.timestamp).toLocaleTimeString()
        );

        trendsChart.data.datasets[0].data = sampledTrends.map(trend => trend.cpu_percent);
        trendsChart.data.datasets[1].data = sampledTrends.map(trend => trend.memory_percent);
        trendsChart.data.datasets[2].data = sampledTrends.map(trend => trend.disk_percent);

        trendsChart.update();
    }

    async loadOptimizationRecommendations() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/optimization');
            const result = await response.json();

            if (result.success) {
                this.updateOptimizationList(result.data);
            }
        } catch (error) {
            console.error('Error loading optimization recommendations:', error);
        }
    }

    updateOptimizationList(data) {
        const container = document.getElementById('optimization-list');
        const allRecommendations = [
            ...data.recommendations.high_priority,
            ...data.recommendations.medium_priority,
            ...data.recommendations.low_priority
        ];

        if (allRecommendations.length === 0) {
            container.innerHTML = '<div class="no-data">No optimization recommendations available</div>';
            return;
        }

        let html = '';
        allRecommendations.forEach(rec => {
            html += `
                <div class="optimization-item ${rec.priority}-priority">
                    <div class="optimization-title">${rec.title}</div>
                    <div class="optimization-description">${rec.description}</div>
                    <div class="optimization-meta">
                        <span>Priority: ${rec.priority}</span>
                        <span>Impact: ${rec.impact}</span>
                        <span>Effort: ${rec.implementation_effort}</span>
                        ${rec.estimated_savings ? `<span>Savings: ${rec.estimated_savings}</span>` : ''}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    async loadEfficiencyAnalysis() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/efficiency');
            const result = await response.json();

            if (result.success && result.data.status !== 'insufficient_data') {
                this.updateEfficiencyScore(result.data);
            }
        } catch (error) {
            console.error('Error loading efficiency analysis:', error);
        }
    }

    updateEfficiencyScore(data) {
        const scoreChart = this.charts.efficiencyScore;
        const score = data.efficiency_score.overall;

        // Update chart
        scoreChart.data.datasets[0].data = [score, 100 - score];

        // Update colors based on score
        let color = '#e74c3c'; // Poor
        if (score >= 85) color = '#27ae60'; // Excellent
        else if (score >= 70) color = '#2ecc71'; // Good
        else if (score >= 40) color = '#f39c12'; // Fair

        scoreChart.data.datasets[0].backgroundColor[0] = color;
        scoreChart.update();

        // Update text
        document.getElementById('efficiency-score').textContent = score.toFixed(0);
        document.getElementById('efficiency-grade').textContent = data.efficiency_score.grade;
        document.getElementById('cpu-efficiency').textContent = data.efficiency_score.cpu.toFixed(0) + '%';
        document.getElementById('memory-efficiency').textContent = data.efficiency_score.memory.toFixed(0) + '%';
    }

    async loadAlerts() {
        try {
            const response = await fetch('/api/v1/resource-dashboard/alerts');
            const result = await response.json();

            if (result.success) {
                this.updateAlertsList(result.data);
            }
        } catch (error) {
            console.error('Error loading alerts:', error);
        }
    }

    updateAlertsList(data) {
        const container = document.getElementById('alerts-list');
        const allAlerts = [
            ...data.alerts.critical,
            ...data.alerts.warning,
            ...data.alerts.info
        ];

        if (allAlerts.length === 0) {
            container.innerHTML = '<div class="no-alerts">No active alerts</div>';
            return;
        }

        let html = '';
        allAlerts.forEach(alert => {
            const time = new Date(alert.timestamp).toLocaleTimeString();
            html += `
                <div class="alert-item ${alert.severity}">
                    <div class="alert-message">${alert.message}</div>
                    <div class="alert-time">${time}</div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    refreshDashboard() {
        this.loadDashboardData();
    }

    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        this.refreshInterval = setInterval(() => {
            if (this.isMonitoring) {
                this.loadDashboardData();
            }
        }, this.refreshRate);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    showLoading() {
        document.getElementById('loading-overlay').classList.add('show');
    }

    hideLoading() {
        document.getElementById('loading-overlay').classList.remove('show');
    }

    showError(message) {
        document.getElementById('error-message').textContent = message;
        document.getElementById('error-modal').classList.add('show');
    }

    showSuccess(message) {
        // You could implement a success notification here
        console.log('Success:', message);
    }

    closeErrorModal() {
        document.getElementById('error-modal').classList.remove('show');
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.resourceDashboard = new ResourceDashboard();
});

// Global function for modal close button
function closeErrorModal() {
    window.resourceDashboard.closeErrorModal();
}