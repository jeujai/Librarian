/**
 * Analytics Dashboard JavaScript
 * 
 * Handles data fetching, chart rendering, and user interactions
 * for the analytics dashboard.
 */

class AnalyticsDashboard {
    constructor() {
        this.charts = {};
        this.data = null;
        this.refreshInterval = null;
        
        this.init();
    }
    
    async init() {
        console.log('🚀 Initializing Analytics Dashboard');
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Load initial data
        await this.loadDashboardData();
        
        // Set up auto-refresh (every 5 minutes)
        this.setupAutoRefresh();
    }
    
    setupEventListeners() {
        // Refresh button
        document.getElementById('refreshBtn')?.addEventListener('click', () => {
            this.loadDashboardData();
        });
        
        // Export button
        document.getElementById('exportBtn')?.addEventListener('click', () => {
            this.exportData();
        });
        
        // Retry button (for error state)
        document.getElementById('retryBtn')?.addEventListener('click', () => {
            this.loadDashboardData();
        });
    }
    
    setupAutoRefresh() {
        // Refresh every 5 minutes
        this.refreshInterval = setInterval(() => {
            this.loadDashboardData(false); // Silent refresh
        }, 5 * 60 * 1000);
    }
    
    async loadDashboardData(showLoading = true) {
        try {
            if (showLoading) {
                this.showLoadingState();
            }
            
            console.log('📊 Fetching analytics data...');
            
            const response = await fetch('/api/analytics/dashboard/summary');
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.message || 'Failed to load analytics data');
            }
            
            this.data = result.data;
            console.log('✅ Analytics data loaded successfully');
            
            // Update UI
            this.updateOverviewStats();
            this.renderCharts();
            this.updateInsights();
            this.updateEngagement();
            this.updateLastUpdated();
            
            this.showDashboardContent();
            
        } catch (error) {
            console.error('❌ Error loading analytics data:', error);
            this.showErrorState(error.message);
        }
    }
    
    updateOverviewStats() {
        const overview = this.data.overview;
        
        // Update stat cards
        document.getElementById('totalDocs').textContent = overview.total_documents || 0;
        document.getElementById('totalSize').textContent = `${overview.total_size_mb || 0} MB`;
        document.getElementById('chatSessions').textContent = overview.chat_sessions || 0;
        document.getElementById('similarPairs').textContent = overview.similar_pairs || 0;
        
        // Add animation
        document.querySelectorAll('.stat-card').forEach((card, index) => {
            setTimeout(() => {
                card.classList.add('slide-up');
            }, index * 100);
        });
    }
    
    renderCharts() {
        this.renderUploadTimelineChart();
        this.renderFileTypesChart();
        this.renderDailyActivityChart();
        this.renderFeatureUsageChart();
    }
    
    renderUploadTimelineChart() {
        const ctx = document.getElementById('uploadTimelineChart');
        if (!ctx) return;
        
        const timelineData = this.data.charts_data.upload_timeline || {};
        const dates = Object.keys(timelineData).sort();
        const uploads = dates.map(date => timelineData[date]);
        
        // Destroy existing chart
        if (this.charts.uploadTimeline) {
            this.charts.uploadTimeline.destroy();
        }
        
        this.charts.uploadTimeline = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Documents Uploaded',
                    data: uploads,
                    borderColor: '#4facfe',
                    backgroundColor: 'rgba(79, 172, 254, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
    
    renderFileTypesChart() {
        const ctx = document.getElementById('fileTypesChart');
        if (!ctx) return;
        
        const fileTypes = this.data.charts_data.file_types || {};
        const labels = Object.keys(fileTypes);
        const data = Object.values(fileTypes);
        
        // Destroy existing chart
        if (this.charts.fileTypes) {
            this.charts.fileTypes.destroy();
        }
        
        this.charts.fileTypes = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        '#4facfe',
                        '#00f2fe',
                        '#667eea',
                        '#764ba2',
                        '#f093fb',
                        '#f5576c'
                    ],
                    borderWidth: 0
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
    }
    
    renderDailyActivityChart() {
        const ctx = document.getElementById('dailyActivityChart');
        if (!ctx) return;
        
        const activityData = this.data.charts_data.daily_activity || {};
        const dates = Object.keys(activityData).sort();
        
        const chatData = dates.map(date => activityData[date]?.chat_messages || 0);
        const uploadData = dates.map(date => activityData[date]?.document_uploads || 0);
        const searchData = dates.map(date => activityData[date]?.search_queries || 0);
        
        // Destroy existing chart
        if (this.charts.dailyActivity) {
            this.charts.dailyActivity.destroy();
        }
        
        this.charts.dailyActivity = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: dates,
                datasets: [
                    {
                        label: 'Chat Messages',
                        data: chatData,
                        backgroundColor: '#4facfe'
                    },
                    {
                        label: 'Document Uploads',
                        data: uploadData,
                        backgroundColor: '#00f2fe'
                    },
                    {
                        label: 'Search Queries',
                        data: searchData,
                        backgroundColor: '#667eea'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true
                    }
                }
            }
        });
    }
    
    renderFeatureUsageChart() {
        const ctx = document.getElementById('featureUsageChart');
        if (!ctx) return;
        
        const featureData = this.data.charts_data.feature_usage || {};
        const labels = Object.keys(featureData);
        const data = Object.values(featureData);
        
        // Destroy existing chart
        if (this.charts.featureUsage) {
            this.charts.featureUsage.destroy();
        }
        
        this.charts.featureUsage = new Chart(ctx, {
            type: 'horizontalBar',
            data: {
                labels: labels.map(label => label.replace(/_/g, ' ').toUpperCase()),
                datasets: [{
                    label: 'Usage %',
                    data: data,
                    backgroundColor: labels.map((_, index) => {
                        const colors = ['#4facfe', '#00f2fe', '#667eea', '#764ba2', '#f093fb'];
                        return colors[index % colors.length];
                    })
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });
    }
    
    updateInsights() {
        this.updateKeywords();
        this.updateContentClusters();
        this.updateSimilarDocuments();
        this.updateQualityMetrics();
    }
    
    updateKeywords() {
        const insights = this.data.insights;
        
        // Title keywords
        const titleKeywordsContainer = document.getElementById('titleKeywords');
        if (titleKeywordsContainer && insights.top_keywords?.titles) {
            titleKeywordsContainer.innerHTML = insights.top_keywords.titles
                .map(([keyword, count]) => 
                    `<span class="keyword-tag">${keyword}<span class="keyword-count">${count}</span></span>`
                ).join('');
        }
        
        // Description keywords
        const descKeywordsContainer = document.getElementById('descriptionKeywords');
        if (descKeywordsContainer && insights.top_keywords?.descriptions) {
            descKeywordsContainer.innerHTML = insights.top_keywords.descriptions
                .map(([keyword, count]) => 
                    `<span class="keyword-tag">${keyword}<span class="keyword-count">${count}</span></span>`
                ).join('');
        }
    }
    
    updateContentClusters() {
        const clustersContainer = document.getElementById('contentClusters');
        if (!clustersContainer) return;
        
        const clusters = this.data.insights.content_clusters || {};
        
        clustersContainer.innerHTML = Object.entries(clusters)
            .map(([clusterName, documents]) => `
                <div class="cluster-item">
                    <div class="cluster-name">${clusterName}</div>
                    <div class="cluster-count">${documents.length} documents</div>
                </div>
            `).join('');
    }
    
    updateSimilarDocuments() {
        const similarContainer = document.getElementById('similarDocuments');
        if (!similarContainer) return;
        
        const similarDocs = this.data.insights.similar_documents || [];
        
        if (similarDocs.length === 0) {
            similarContainer.innerHTML = '<p style="color: #718096; font-style: italic;">No similar documents found</p>';
            return;
        }
        
        similarContainer.innerHTML = similarDocs
            .map(pair => `
                <div class="similar-pair">
                    <span class="similarity-score">${Math.round(pair.similarity_score * 100)}%</span>
                    <div class="doc-title">${pair.document1.title}</div>
                    <div class="doc-title">${pair.document2.title}</div>
                </div>
            `).join('');
    }
    
    updateQualityMetrics() {
        const qualityContainer = document.getElementById('qualityMetrics');
        if (!qualityContainer) return;
        
        const quality = this.data.quick_stats.content_quality || {};
        
        const metrics = [
            { name: 'Description Coverage', value: `${quality.description_coverage || 0}%` },
            { name: 'Meaningful Titles', value: `${quality.meaningful_titles || 0}%` },
            { name: 'Avg Title Words', value: quality.avg_title_words || 0 },
            { name: 'Content Richness', value: `${quality.content_richness_score || 0}%` }
        ];
        
        qualityContainer.innerHTML = metrics
            .map(metric => `
                <div class="quality-metric">
                    <span class="metric-name">${metric.name}</span>
                    <span class="metric-value">${metric.value}</span>
                </div>
            `).join('');
    }
    
    updateEngagement() {
        const engagement = this.data.quick_stats.user_engagement || {};
        
        // Engagement score
        const scoreElement = document.getElementById('engagementScore');
        if (scoreElement) {
            scoreElement.textContent = engagement.engagement_score || 0;
        }
        
        // Preferred features
        const featuresContainer = document.getElementById('preferredFeatures');
        if (featuresContainer && engagement.preferred_features) {
            featuresContainer.innerHTML = engagement.preferred_features
                .map(feature => `
                    <div class="feature-item">
                        <span class="feature-name">${feature.replace(/_/g, ' ')}</span>
                        <span class="feature-badge">Preferred</span>
                    </div>
                `).join('');
        }
        
        // Activity trends (mock data)
        const trendsContainer = document.getElementById('activityTrends');
        if (trendsContainer) {
            trendsContainer.innerHTML = `
                <div class="feature-item">
                    <span class="feature-name">Daily Active Sessions</span>
                    <span class="metric-value">↗️ +15%</span>
                </div>
                <div class="feature-item">
                    <span class="feature-name">Document Interactions</span>
                    <span class="metric-value">↗️ +8%</span>
                </div>
                <div class="feature-item">
                    <span class="feature-name">Search Efficiency</span>
                    <span class="metric-value">↗️ +22%</span>
                </div>
            `;
        }
    }
    
    updateLastUpdated() {
        const lastUpdatedElement = document.getElementById('lastUpdated');
        if (lastUpdatedElement) {
            lastUpdatedElement.textContent = new Date().toLocaleString();
        }
    }
    
    exportData() {
        if (!this.data) {
            alert('No data to export');
            return;
        }
        
        const dataStr = JSON.stringify(this.data, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `analytics-export-${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        
        console.log('📥 Analytics data exported');
    }
    
    showLoadingState() {
        document.getElementById('loadingState').style.display = 'flex';
        document.getElementById('dashboardContent').style.display = 'none';
        document.getElementById('errorState').style.display = 'none';
    }
    
    showDashboardContent() {
        document.getElementById('loadingState').style.display = 'none';
        document.getElementById('dashboardContent').style.display = 'block';
        document.getElementById('errorState').style.display = 'none';
        
        // Add fade-in animation
        document.getElementById('dashboardContent').classList.add('fade-in');
    }
    
    showErrorState(message) {
        document.getElementById('loadingState').style.display = 'none';
        document.getElementById('dashboardContent').style.display = 'none';
        document.getElementById('errorState').style.display = 'flex';
        
        const errorMessageElement = document.getElementById('errorMessage');
        if (errorMessageElement) {
            errorMessageElement.textContent = message;
        }
    }
    
    destroy() {
        // Clean up charts
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        
        // Clear refresh interval
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.analyticsDashboard = new AnalyticsDashboard();
});

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (window.analyticsDashboard) {
        window.analyticsDashboard.destroy();
    }
});