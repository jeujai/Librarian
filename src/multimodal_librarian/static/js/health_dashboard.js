/**
 * Health Check Dashboard JavaScript
 * 
 * This script manages the health check dashboard interface, including:
 * - Real-time health monitoring
 * - Service status updates
 * - Interactive charts and visualizations
 * - Error handling and user feedback
 */

class HealthDashboard {
    constructor() {
        this.currentPanel = 'overview';
        this.isMonitoring = false;
        this.monitoringInterval = null;
        this.realtimeInterval = null;
        this.charts = {};
        this.healthData = {};

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeCharts();
        this.loadInitialData();
    }

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchPanel(e.target.dataset.dashboard);
            });
        });

        // Service tabs
        document.querySelectorAll('.service-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.showServiceDetails(e.target.dataset.service);
            });
        });

        // Service cards
        document.querySelectorAll('.service-card').forEach(card => {
            card.addEventListener('click', (e) => {
                const service = e.currentTarget.dataset.service;
                this.switchPanel('services');
                this.showServiceDetails(service);
            });
        });

        // Control buttons
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.refreshData();
        });

        document.getElementById('start-monitoring-btn').addEventListener('click', () => {
            this.startMonitoring();
        });

        document.getElementById('stop-monitoring-btn').addEventListener('click', () => {
            this.stopMonitoring();
        });

        document.getElementById('start-realtime-btn').addEventListener('click', () => {
            this.startRealtimeMonitoring();
        });

        document.getElementById('stop-realtime-btn').addEventListener('click', () => {
            this.stopRealtimeMonitoring();
        });

        // Modal controls
        document.querySelector('.modal-close').addEventListener('click', () => {
            this.closeErrorModal();
        });

        // Auto-refresh every 30 seconds when not in real-time mode
        setInterval(() => {
            if (!this.isMonitoring) {
                this.refreshData();
            }
        }, 30000);
    }

    switchPanel(panelName) {
        // Hide all panels
        document.querySelectorAll('.dashboard-panel').forEach(panel => {
            panel.classList.remove('active');
        });

        // Show selected panel
        document.getElementById(panelName).classList.add('active');

        // Update navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-dashboard="${panelName}"]`).classList.add('active');

        this.currentPanel = panelName;

        // Load panel-specific data
        this.loadPanelData(panelName);
    }

    async loadPanelData(panelName) {
        try {
            switch (panelName) {
                case 'overview':
                    await this.loadOverviewData();
                    break;
                case 'services':
                    await this.loadServicesData();
                    break;
                case 'connectivity':
                    await this.loadConnectivityData();
                    break;
                case 'performance':
                    await this.loadPerformanceData();
                    break;
                case 'dependencies':
                    await this.loadDependenciesData();
                    break;
            }
        } catch (error) {
            this.showError('Failed to load panel data', error);
        }
    }

    async loadInitialData() {
        this.showLoading(true);
        try {
            await this.loadOverviewData();
        } catch (error) {
            this.showError('Failed to load initial health data', error);
        } finally {
            this.showLoading(false);
        }
    }

    async refreshData() {
        await this.loadPanelData(this.currentPanel);
        this.updateLastUpdated();
    }

    async loadOverviewData() {
        try {
            const response = await fetch('/api/health/local/');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.healthData = data;

            this.updateOverallStatus(data);
            this.updateServiceCards(data.services || {});
            this.updateHealthAlerts(data);
            this.updateRecommendations(data.recommendations || []);
            this.updateHealthChart(data);

        } catch (error) {
            console.error('Failed to load overview data:', error);
            this.showError('Failed to load health overview', error);
        }
    }

    async loadServicesData() {
        // Service details are loaded when a specific service tab is clicked
        if (document.querySelector('.service-tab.active')) {
            const activeService = document.querySelector('.service-tab.active').dataset.service;
            await this.loadServiceDetails(activeService);
        }
    }

    async loadConnectivityData() {
        try {
            const response = await fetch('/api/health/local/connectivity?include_pool_stats=true&include_performance=true');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            this.updateConnectivityOverview(data);
            this.updateConnectionPools(data);
            this.updateResponseTimeChart(data);

        } catch (error) {
            console.error('Failed to load connectivity data:', error);
            this.showError('Failed to load connectivity data', error);
        }
    }

    async loadPerformanceData() {
        try {
            const response = await fetch('/api/health/local/performance');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            this.updatePerformanceOverview(data);
            this.updatePerformanceCharts(data);
            this.updatePerformanceTable(data);

        } catch (error) {
            console.error('Failed to load performance data:', error);
            this.showError('Failed to load performance data', error);
        }
    }

    async loadDependenciesData() {
        try {
            const response = await fetch('/api/health/local/dependencies');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            this.updateDependencyChain(data);
            this.updateDockerStatus(data);
            this.updateStartupOrder(data);

        } catch (error) {
            console.error('Failed to load dependencies data:', error);
            this.showError('Failed to load dependencies data', error);
        }
    }

    async loadServiceDetails(serviceName) {
        try {
            const response = await fetch(`/api/health/local/${serviceName}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.displayServiceDetails(serviceName, data);

        } catch (error) {
            console.error(`Failed to load ${serviceName} details:`, error);
            this.showError(`Failed to load ${serviceName} details`, error);
        }
    }

    updateOverallStatus(data) {
        const indicator = document.getElementById('overall-status-indicator');
        const text = document.getElementById('overall-status-text');
        const percentage = document.getElementById('health-percentage');
        const grade = document.getElementById('health-grade');
        const healthyCount = document.getElementById('healthy-count');
        const totalServices = document.getElementById('total-services');
        const lastCheck = document.getElementById('last-check-time');

        const status = data.overall_status || 'unknown';
        const summary = data.summary || {};

        // Update status indicator
        indicator.className = `status-indicator ${status}`;
        text.textContent = this.formatStatus(status);

        // Calculate health percentage
        const total = summary.total_services || 0;
        const healthy = summary.healthy_services || 0;
        const healthPercent = total > 0 ? Math.round((healthy / total) * 100) : 0;

        percentage.textContent = `${healthPercent}%`;
        grade.textContent = this.getHealthGrade(healthPercent);

        // Update summary
        healthyCount.textContent = `${healthy}/${total}`;
        totalServices.textContent = total;
        lastCheck.textContent = this.formatTime(data.check_timestamp);
    }

    updateServiceCards(services) {
        Object.entries(services).forEach(([serviceName, serviceData]) => {
            const card = document.querySelector(`[data-service="${serviceName}"]`);
            if (!card) return;

            const status = serviceData.status || 'unknown';
            const responseTime = serviceData.response_time_ms || 0;

            // Update card status
            card.className = `service-card ${status}`;

            // Update status badge
            const badge = document.getElementById(`${serviceName}-status`);
            if (badge) {
                badge.className = `service-status-badge ${status}`;
                badge.textContent = this.formatStatus(status);
            }

            // Update response time
            const responseTimeEl = document.getElementById(`${serviceName}-response-time`);
            if (responseTimeEl) {
                responseTimeEl.textContent = `${responseTime.toFixed(1)}ms`;
            }

            // Update service-specific metrics
            this.updateServiceMetrics(serviceName, serviceData);
        });
    }

    updateServiceMetrics(serviceName, serviceData) {
        const metrics = serviceData.metrics || {};
        const details = serviceData.details || {};

        switch (serviceName) {
            case 'postgres':
                const connectionsEl = document.getElementById('postgres-connections');
                if (connectionsEl) {
                    connectionsEl.textContent = metrics.active_connections || '--';
                }
                break;

            case 'neo4j':
                const nodesEl = document.getElementById('neo4j-nodes');
                if (nodesEl) {
                    nodesEl.textContent = metrics.node_count || '--';
                }
                break;

            case 'milvus':
                const collectionsEl = document.getElementById('milvus-collections');
                if (collectionsEl) {
                    collectionsEl.textContent = metrics.collection_count || '--';
                }
                break;

            case 'redis':
                const memoryEl = document.getElementById('redis-memory');
                if (memoryEl) {
                    memoryEl.textContent = metrics.used_memory || '--';
                }
                break;
        }
    }

    updateHealthAlerts(data) {
        const alertsList = document.getElementById('health-alerts-list');
        const alerts = [];

        // Collect alerts from various sources
        if (data.issues && data.issues.length > 0) {
            data.issues.forEach(issue => {
                alerts.push({
                    level: 'warning',
                    message: issue,
                    service: 'system',
                    timestamp: data.check_timestamp
                });
            });
        }

        // Add service-specific alerts
        Object.entries(data.services || {}).forEach(([serviceName, serviceData]) => {
            if (serviceData.issues && serviceData.issues.length > 0) {
                serviceData.issues.forEach(issue => {
                    alerts.push({
                        level: serviceData.status === 'unhealthy' ? 'critical' : 'warning',
                        message: issue,
                        service: serviceName,
                        timestamp: serviceData.timestamp
                    });
                });
            }
        });

        if (alerts.length === 0) {
            alertsList.innerHTML = '<div class="no-alerts">No active health alerts</div>';
            return;
        }

        alertsList.innerHTML = alerts.map(alert => `
            <div class="alert-item ${alert.level}">
                <div class="alert-message">${alert.message}</div>
                <div class="alert-service">${alert.service}</div>
                <div class="alert-time">${this.formatTime(alert.timestamp)}</div>
            </div>
        `).join('');
    }

    updateRecommendations(recommendations) {
        const recommendationsList = document.getElementById('recommendations-list');

        if (!recommendations || recommendations.length === 0) {
            recommendationsList.innerHTML = '<div class="no-recommendations">No recommendations available</div>';
            return;
        }

        recommendationsList.innerHTML = recommendations.map(rec => {
            const priority = this.getRecommendationPriority(rec);
            return `
                <div class="recommendation-item ${priority}">
                    ${rec}
                </div>
            `;
        }).join('');
    }

    showServiceDetails(serviceName) {
        // Update active tab
        document.querySelectorAll('.service-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`[data-service="${serviceName}"]`).classList.add('active');

        // Load service details
        this.loadServiceDetails(serviceName);
    }

    displayServiceDetails(serviceName, data) {
        const detailsContainer = document.getElementById('service-details');

        const status = data.status || 'unknown';
        const metrics = data.metrics || {};
        const details = data.details || {};
        const issues = data.issues || [];

        detailsContainer.innerHTML = `
            <div class="service-detail-grid">
                <div class="detail-section">
                    <h4>Status Information</h4>
                    <ul class="detail-list">
                        <li><span>Status:</span><span class="service-status-badge ${status}">${this.formatStatus(status)}</span></li>
                        <li><span>Response Time:</span><span>${data.response_time_ms?.toFixed(1) || '--'}ms</span></li>
                        <li><span>Last Check:</span><span>${this.formatTime(data.timestamp)}</span></li>
                        <li><span>Version:</span><span>${details.version || 'Unknown'}</span></li>
                    </ul>
                </div>
                
                <div class="detail-section">
                    <h4>Performance Metrics</h4>
                    <ul class="detail-list">
                        ${Object.entries(metrics).map(([key, value]) => `
                            <li><span>${this.formatMetricName(key)}:</span><span>${value}</span></li>
                        `).join('')}
                    </ul>
                </div>
                
                <div class="detail-section">
                    <h4>Connection Details</h4>
                    <ul class="detail-list">
                        ${Object.entries(details).filter(([key]) => key !== 'version').map(([key, value]) => `
                            <li><span>${this.formatMetricName(key)}:</span><span>${value}</span></li>
                        `).join('')}
                    </ul>
                </div>
                
                ${issues.length > 0 ? `
                <div class="detail-section">
                    <h4>Issues</h4>
                    <ul class="detail-list">
                        ${issues.map(issue => `<li>${issue}</li>`).join('')}
                    </ul>
                </div>
                ` : ''}
            </div>
        `;
    }

    updateConnectivityOverview(data) {
        document.getElementById('connectivity-percentage').textContent =
            `${data.overall_connectivity?.toFixed(1) || '--'}%`;

        document.getElementById('avg-response-time').textContent =
            `${data.summary?.avg_response_time_ms?.toFixed(1) || '--'}ms`;

        document.getElementById('total-connections').textContent =
            data.summary?.total_connections || '--';
    }

    updateConnectionPools(data) {
        const poolsTable = document.getElementById('connection-pools-table');
        const services = data.services || {};

        if (Object.keys(services).length === 0) {
            poolsTable.innerHTML = '<div class="no-data">No connection pool data available</div>';
            return;
        }

        const tableHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Status</th>
                        <th>Connections</th>
                        <th>Utilization</th>
                        <th>Response Time</th>
                    </tr>
                </thead>
                <tbody>
                    ${Object.entries(services).map(([serviceName, serviceData]) => `
                        <tr>
                            <td>${serviceName}</td>
                            <td><span class="service-status-badge ${serviceData.connected ? 'healthy' : 'unhealthy'}">
                                ${serviceData.connected ? 'Connected' : 'Disconnected'}
                            </span></td>
                            <td>${serviceData.connection_count || '--'}</td>
                            <td>${serviceData.pool_utilization?.toFixed(1) || '--'}%</td>
                            <td>${serviceData.response_time_ms?.toFixed(1) || '--'}ms</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        poolsTable.innerHTML = tableHTML;
    }

    updateResponseTimeChart(data) {
        const ctx = document.getElementById('response-time-chart');
        if (!ctx) return;

        const services = data.services || {};
        const labels = Object.keys(services);
        const responseTimes = labels.map(service => services[service].response_time_ms || 0);

        if (this.charts.responseTime) {
            this.charts.responseTime.destroy();
        }

        this.charts.responseTime = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Response Time (ms)',
                    data: responseTimes,
                    backgroundColor: 'rgba(52, 152, 219, 0.6)',
                    borderColor: 'rgba(52, 152, 219, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Response Time (ms)'
                        }
                    }
                }
            }
        });
    }

    updatePerformanceOverview(data) {
        const score = data.summary?.performance_score || 0;
        document.getElementById('performance-score').textContent = score;

        // Update performance score chart
        const ctx = document.getElementById('performance-score-chart');
        if (!ctx) return;

        if (this.charts.performanceScore) {
            this.charts.performanceScore.destroy();
        }

        this.charts.performanceScore = new Chart(ctx, {
            type: 'doughnut',
            data: {
                datasets: [{
                    data: [score, 100 - score],
                    backgroundColor: [
                        this.getPerformanceColor(score),
                        'rgba(200, 200, 200, 0.3)'
                    ],
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
    }

    updatePerformanceCharts(data) {
        // Service response times chart
        const ctx1 = document.getElementById('service-response-chart');
        if (ctx1) {
            const services = data.services || {};
            const labels = Object.keys(services);
            const responseTimes = labels.map(service => services[service].response_time_ms || 0);

            if (this.charts.serviceResponse) {
                this.charts.serviceResponse.destroy();
            }

            this.charts.serviceResponse = new Chart(ctx1, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Response Time (ms)',
                        data: responseTimes,
                        borderColor: 'rgba(52, 152, 219, 1)',
                        backgroundColor: 'rgba(52, 152, 219, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }

        // Throughput chart (placeholder)
        const ctx2 = document.getElementById('throughput-chart');
        if (ctx2) {
            if (this.charts.throughput) {
                this.charts.throughput.destroy();
            }

            this.charts.throughput = new Chart(ctx2, {
                type: 'bar',
                data: {
                    labels: ['PostgreSQL', 'Neo4j', 'Milvus', 'Redis'],
                    datasets: [{
                        label: 'Operations/sec',
                        data: [100, 50, 25, 200], // Placeholder data
                        backgroundColor: 'rgba(46, 204, 113, 0.6)',
                        borderColor: 'rgba(46, 204, 113, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }
    }

    updatePerformanceTable(data) {
        const table = document.getElementById('performance-table');
        const services = data.services || {};

        if (Object.keys(services).length === 0) {
            table.innerHTML = '<div class="no-data">No performance data available</div>';
            return;
        }

        const tableHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Response Time</th>
                        <th>Connections</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${Object.entries(services).map(([serviceName, serviceData]) => `
                        <tr>
                            <td>${serviceName}</td>
                            <td>${serviceData.response_time_ms?.toFixed(1) || '--'}ms</td>
                            <td>${serviceData.connections || '--'}</td>
                            <td><span class="service-status-badge ${serviceData.status}">${this.formatStatus(serviceData.status)}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        table.innerHTML = tableHTML;
    }

    updateDependencyChain(data) {
        const chainContainer = document.getElementById('dependency-chain');
        const dependencyChain = data.dependency_chain || [];

        if (dependencyChain.length === 0) {
            chainContainer.innerHTML = '<div class="no-data">No dependency information available</div>';
            return;
        }

        chainContainer.innerHTML = dependencyChain.map(dep => `
            <div class="dependency-item ${dep.ready ? '' : 'failed'}">
                <span class="dependency-service">${dep.service}</span>
                <span>Dependencies: ${dep.dependencies.join(', ') || 'None'}</span>
                <span class="dependency-status service-status-badge ${dep.ready ? 'healthy' : 'unhealthy'}">
                    ${dep.ready ? 'Ready' : 'Not Ready'}
                </span>
            </div>
        `).join('');
    }

    updateDockerStatus(data) {
        const dockerContainer = document.getElementById('docker-containers');
        const dockerInfo = this.healthData?.docker_info || {};

        if (!dockerInfo.containers || Object.keys(dockerInfo.containers).length === 0) {
            dockerContainer.innerHTML = '<div class="no-data">No Docker container information available</div>';
            return;
        }

        dockerContainer.innerHTML = Object.entries(dockerInfo.containers).map(([name, info]) => `
            <div class="docker-container ${info.status.includes('Up') ? '' : 'unhealthy'}">
                <div class="container-name">${name}</div>
                <div class="container-status">Status: ${info.status}</div>
                <div class="container-status">Ports: ${info.ports || 'None'}</div>
            </div>
        `).join('');
    }

    updateStartupOrder(data) {
        const startupContainer = document.getElementById('startup-order');
        const startupOrder = data.startup_order || [];

        if (startupOrder.length === 0) {
            startupContainer.innerHTML = '<div class="no-data">No startup order information available</div>';
            return;
        }

        startupContainer.innerHTML = startupOrder.map((service, index) => `
            <div class="startup-step">
                ${index + 1}. ${service}
            </div>
        `).join('');
    }

    initializeCharts() {
        // Initialize health overview chart
        const healthCtx = document.getElementById('health-overview-chart');
        if (healthCtx) {
            this.charts.healthOverview = new Chart(healthCtx, {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [0, 100],
                        backgroundColor: ['rgba(200, 200, 200, 0.3)', 'rgba(200, 200, 200, 0.1)'],
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
        }
    }

    updateHealthChart(data) {
        if (!this.charts.healthOverview) return;

        const summary = data.summary || {};
        const total = summary.total_services || 0;
        const healthy = summary.healthy_services || 0;
        const healthPercent = total > 0 ? (healthy / total) * 100 : 0;

        this.charts.healthOverview.data.datasets[0].data = [healthPercent, 100 - healthPercent];
        this.charts.healthOverview.data.datasets[0].backgroundColor = [
            this.getHealthColor(data.overall_status),
            'rgba(200, 200, 200, 0.3)'
        ];
        this.charts.healthOverview.update();
    }

    startMonitoring() {
        if (this.isMonitoring) return;

        this.isMonitoring = true;
        document.getElementById('start-monitoring-btn').style.display = 'none';
        document.getElementById('stop-monitoring-btn').style.display = 'inline-flex';
        document.getElementById('monitoring-status').textContent = 'Active';

        // Refresh every 10 seconds
        this.monitoringInterval = setInterval(() => {
            this.refreshData();
        }, 10000);
    }

    stopMonitoring() {
        if (!this.isMonitoring) return;

        this.isMonitoring = false;
        document.getElementById('start-monitoring-btn').style.display = 'inline-flex';
        document.getElementById('stop-monitoring-btn').style.display = 'none';
        document.getElementById('monitoring-status').textContent = 'Inactive';

        if (this.monitoringInterval) {
            clearInterval(this.monitoringInterval);
            this.monitoringInterval = null;
        }
    }

    async startRealtimeMonitoring() {
        const interval = parseInt(document.getElementById('monitoring-interval').value);
        const duration = 60; // 1 minute

        document.getElementById('start-realtime-btn').style.display = 'none';
        document.getElementById('stop-realtime-btn').style.display = 'inline-flex';

        const resultsContainer = document.getElementById('realtime-results');
        resultsContainer.innerHTML = '<div class="loading-message">Starting real-time monitoring...</div>';

        try {
            const response = await fetch(`/api/health/local/connectivity/realtime?duration_seconds=${duration}&interval_seconds=${interval}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.displayRealtimeResults(data);

        } catch (error) {
            this.showError('Real-time monitoring failed', error);
        } finally {
            document.getElementById('start-realtime-btn').style.display = 'inline-flex';
            document.getElementById('stop-realtime-btn').style.display = 'none';
        }
    }

    stopRealtimeMonitoring() {
        // In a real implementation, this would cancel the ongoing request
        document.getElementById('start-realtime-btn').style.display = 'inline-flex';
        document.getElementById('stop-realtime-btn').style.display = 'none';
    }

    displayRealtimeResults(data) {
        const resultsContainer = document.getElementById('realtime-results');
        const dataPoints = data.data_points || [];

        if (dataPoints.length === 0) {
            resultsContainer.innerHTML = '<div class="no-data">No real-time data available</div>';
            return;
        }

        resultsContainer.innerHTML = `
            <div class="realtime-summary">
                <h4>Real-time Monitoring Results</h4>
                <p>Duration: ${data.duration_seconds}s | Interval: ${data.interval_seconds}s | Checks: ${data.summary.total_checks}</p>
                <p>Uptime: ${data.summary.connectivity_uptime_percent}% | Avg Response: ${data.summary.avg_response_time_ms}ms</p>
            </div>
            <div class="realtime-entries">
                ${dataPoints.slice(-10).map(point => `
                    <div class="realtime-entry">
                        <strong>${this.formatTime(point.timestamp)}</strong> - 
                        Status: ${point.overall_status} | 
                        Services: ${Object.keys(point.services).map(s =>
            `${s}:${point.services[s].connected ? '✓' : '✗'}`
        ).join(', ')}
                    </div>
                `).join('')}
            </div>
        `;
    }

    showLoading(show) {
        const overlay = document.getElementById('loading-overlay');
        if (show) {
            overlay.classList.add('show');
        } else {
            overlay.classList.remove('show');
        }
    }

    showError(message, error) {
        const modal = document.getElementById('error-modal');
        const messageEl = document.getElementById('error-message');
        const detailsEl = document.getElementById('error-details');
        const stackEl = document.getElementById('error-stack');

        messageEl.textContent = message;

        if (error) {
            stackEl.textContent = error.stack || error.message || error.toString();
            detailsEl.style.display = 'none';
        }

        modal.classList.add('show');
    }

    closeErrorModal() {
        document.getElementById('error-modal').classList.remove('show');
    }

    updateLastUpdated() {
        const now = new Date();
        document.getElementById('last-updated').textContent = now.toLocaleTimeString();
    }

    // Utility functions
    formatStatus(status) {
        const statusMap = {
            'healthy': 'Healthy',
            'degraded': 'Degraded',
            'unhealthy': 'Unhealthy',
            'critical': 'Critical',
            'unknown': 'Unknown',
            'error': 'Error'
        };
        return statusMap[status] || status;
    }

    formatTime(timestamp) {
        if (!timestamp) return '--';
        return new Date(timestamp).toLocaleTimeString();
    }

    formatMetricName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    getHealthGrade(percentage) {
        if (percentage >= 95) return 'Excellent';
        if (percentage >= 85) return 'Good';
        if (percentage >= 70) return 'Fair';
        if (percentage >= 50) return 'Poor';
        return 'Critical';
    }

    getHealthColor(status) {
        const colorMap = {
            'healthy': 'rgba(39, 174, 96, 0.8)',
            'degraded': 'rgba(243, 156, 18, 0.8)',
            'unhealthy': 'rgba(231, 76, 60, 0.8)',
            'critical': 'rgba(192, 57, 43, 0.8)',
            'unknown': 'rgba(149, 165, 166, 0.8)'
        };
        return colorMap[status] || colorMap.unknown;
    }

    getPerformanceColor(score) {
        if (score >= 90) return 'rgba(39, 174, 96, 0.8)';
        if (score >= 70) return 'rgba(243, 156, 18, 0.8)';
        return 'rgba(231, 76, 60, 0.8)';
    }

    getRecommendationPriority(recommendation) {
        const text = recommendation.toLowerCase();
        if (text.includes('urgent') || text.includes('critical')) return 'urgent';
        if (text.includes('warning') || text.includes('high')) return 'important';
        return 'normal';
    }
}

// Global functions for modal controls
function toggleErrorDetails() {
    const details = document.getElementById('error-details');
    const button = event.target;

    if (details.style.display === 'none') {
        details.style.display = 'block';
        button.textContent = 'Hide Details';
    } else {
        details.style.display = 'none';
        button.textContent = 'Show Details';
    }
}

function closeErrorModal() {
    document.getElementById('error-modal').classList.remove('show');
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.healthDashboard = new HealthDashboard();
});