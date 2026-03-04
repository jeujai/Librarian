/**
 * Loading States Manager
 * 
 * Manages visual quality indicators and loading states for the application.
 * Provides real-time updates on system capabilities and loading progress.
 */

class LoadingStatesManager {
    constructor() {
        this.updateInterval = null;
        this.lastUpdate = null;
        this.capabilities = {};
        this.loadingProgress = {};

        // Configuration
        this.config = {
            updateIntervalMs: 2000,  // Update every 2 seconds
            animationDuration: 300,
            maxRetries: 3,
            retryDelay: 1000
        };

        // Quality level definitions
        this.qualityLevels = {
            basic: {
                icon: '⚡',
                label: 'Basic',
                description: 'Quick response mode - Basic text processing only',
                color: '#f59e0b'
            },
            enhanced: {
                icon: '🔄',
                label: 'Enhanced',
                description: 'Partial AI mode - Some advanced features available',
                color: '#3b82f6'
            },
            full: {
                icon: '🧠',
                label: 'Full',
                description: 'Full AI mode - All capabilities ready',
                color: '#10b981'
            }
        };

        this.init();
    }

    init() {
        console.log('Initializing Loading States Manager');

        // Create UI elements if they don't exist
        this.createUIElements();

        // Start monitoring - do initial fetch immediately
        this.startMonitoring();

        // Handle page visibility changes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopMonitoring();
            } else {
                this.startMonitoring();
            }
        });

        // Handle window focus/blur
        window.addEventListener('focus', () => this.startMonitoring());
        window.addEventListener('blur', () => this.stopMonitoring());

        // Emit event when capabilities are first loaded
        this.updateCapabilities().then(() => {
            console.log('Initial capabilities loaded:', this.capabilities);
            window.dispatchEvent(new CustomEvent('capabilitiesLoaded', {
                detail: { capabilities: this.capabilities }
            }));
        });
    }

    createUIElements() {
        // Create main quality indicator if it doesn't exist
        if (!document.getElementById('qualityIndicator')) {
            const header = document.querySelector('.header-left');
            if (header) {
                const qualityIndicator = document.createElement('div');
                qualityIndicator.id = 'qualityIndicator';
                qualityIndicator.className = 'quality-indicator basic loading';
                qualityIndicator.innerHTML = `
                    <span class="icon">⚡</span>
                    <span class="label">Starting...</span>
                `;
                header.appendChild(qualityIndicator);
            }
        }

        // Create capability status bar for main interface
        if (!document.getElementById('capabilityStatusBar')) {
            const chatContainer = document.querySelector('.chat-container');
            if (chatContainer) {
                const statusBar = document.createElement('div');
                statusBar.id = 'capabilityStatusBar';
                statusBar.className = 'capability-status-bar';
                statusBar.style.display = 'none';
                statusBar.innerHTML = this.createCapabilityStatusBarHTML();

                // Insert at the top of chat container
                chatContainer.insertBefore(statusBar, chatContainer.firstChild);
            }
        }

        // Create capability status panel if it doesn't exist
        if (!document.getElementById('capabilityStatus')) {
            const chatMessages = document.getElementById('chatMessages');
            if (chatMessages) {
                const statusPanel = document.createElement('div');
                statusPanel.id = 'capabilityStatus';
                statusPanel.className = 'capability-status';
                statusPanel.style.display = 'none';
                statusPanel.innerHTML = this.createCapabilityStatusHTML();

                // Insert after welcome message
                const welcomeMessage = chatMessages.querySelector('.welcome-message');
                if (welcomeMessage) {
                    welcomeMessage.insertAdjacentElement('afterend', statusPanel);
                } else {
                    chatMessages.insertBefore(statusPanel, chatMessages.firstChild);
                }
            }
        }

        // Create loading message container
        if (!document.getElementById('loadingMessage')) {
            const inputContainer = document.querySelector('.chat-input-container');
            if (inputContainer) {
                const loadingMessage = document.createElement('div');
                loadingMessage.id = 'loadingMessage';
                loadingMessage.className = 'loading-message';
                loadingMessage.style.display = 'none';
                inputContainer.insertBefore(loadingMessage, inputContainer.firstChild);
            }
        }
    }

    createCapabilityStatusBarHTML() {
        return `
            <div class="capability-status-bar-content">
                <div class="capability-status-bar-left">
                    <div class="capability-status-bar-icon">🔄</div>
                    <div class="capability-status-bar-text">
                        <span class="primary-text">AI System Loading</span>
                        <span class="secondary-text">Some features may be limited</span>
                    </div>
                </div>
                <div class="capability-status-bar-right">
                    <div class="capability-quick-indicators" id="quickIndicators">
                        <div class="quick-indicator loading" data-tooltip="Chat AI loading">💬</div>
                        <div class="quick-indicator loading" data-tooltip="Document processing loading">📄</div>
                        <div class="quick-indicator loading" data-tooltip="Advanced search loading">🔍</div>
                        <div class="quick-indicator loading" data-tooltip="Complex analysis loading">🧠</div>
                    </div>
                    <button class="capability-details-btn" onclick="document.getElementById('capabilityStatus').style.display = document.getElementById('capabilityStatus').style.display === 'none' ? 'block' : 'none'">
                        Details
                    </button>
                </div>
            </div>
        `;
    }

    createCapabilityStatusHTML() {
        return `
            <div class="capability-status-header">
                <div class="capability-status-title">System Status</div>
                <div class="overall-progress" id="overallProgress">Loading...</div>
            </div>
            
            <div class="progress-container">
                <div class="progress-label">
                    <span>Overall Progress</span>
                    <span id="progressPercent">0%</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill loading" id="overallProgressBar" style="width: 0%"></div>
                </div>
            </div>
            
            <div class="capability-category">
                <div class="capability-category-title">
                    <span class="icon">⚡</span>
                    <span>Basic Capabilities</span>
                </div>
                <div class="capability-list" id="basicCapabilities"></div>
            </div>
            
            <div class="capability-category">
                <div class="capability-category-title">
                    <span class="icon">🔄</span>
                    <span>Enhanced Capabilities</span>
                </div>
                <div class="capability-list" id="enhancedCapabilities"></div>
            </div>
            
            <div class="capability-category">
                <div class="capability-category-title">
                    <span class="icon">🧠</span>
                    <span>Full Capabilities</span>
                </div>
                <div class="capability-list" id="fullCapabilities"></div>
            </div>
        `;
    }

    startMonitoring() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }

        // Initial update
        this.updateCapabilities();

        // Set up periodic updates
        this.updateInterval = setInterval(() => {
            this.updateCapabilities();
        }, this.config.updateIntervalMs);

        console.log('Started capability monitoring');
    }

    stopMonitoring() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
        console.log('Stopped capability monitoring');
    }

    async updateCapabilities() {
        try {
            // Fetch capability summary
            const capabilityResponse = await fetch('/api/loading/capabilities');
            if (!capabilityResponse.ok) {
                throw new Error(`HTTP ${capabilityResponse.status}`);
            }
            const capabilityData = await capabilityResponse.json();

            // Fetch loading progress
            const progressResponse = await fetch('/api/loading/progress');
            if (!progressResponse.ok) {
                throw new Error(`HTTP ${progressResponse.status}`);
            }
            const progressResponseData = await progressResponse.json();
            // Extract progress from response wrapper (API returns { status, progress: {...} })
            const progressData = progressResponseData.progress || progressResponseData;

            // Debug logging for capability data structure
            const summary = capabilityData.summary || capabilityData;
            console.debug('Capability update:', {
                currentLevel: summary.overall?.current_level,
                readinessPercent: summary.overall?.readiness_percent,
                overallProgress: progressData.overall_progress
            });

            // Update stored data
            this.capabilities = capabilityData;
            this.loadingProgress = progressData;
            this.lastUpdate = Date.now();

            // Update UI
            this.updateQualityIndicator(capabilityData);
            this.updateCapabilityStatus(capabilityData, progressData);
            this.updateLoadingMessage(capabilityData, progressData);

        } catch (error) {
            console.error('Error updating capabilities:', error);
            this.handleUpdateError(error);
        }
    }

    updateQualityIndicator(capabilityData) {
        const indicator = document.getElementById('qualityIndicator');
        if (!indicator) return;

        // API returns data under capabilityData.summary.overall, not capabilityData.overall
        const summary = capabilityData.summary || capabilityData;
        const currentLevel = summary.overall?.current_level || 'basic';
        const readinessPercent = summary.overall?.readiness_percent || 0;
        const qualityInfo = this.qualityLevels[currentLevel];

        // Update classes
        indicator.className = `quality-indicator ${currentLevel}`;
        if (readinessPercent < 100) {
            indicator.classList.add('loading');
        }

        // Update content
        const icon = indicator.querySelector('.icon');
        const label = indicator.querySelector('.label');

        if (icon) icon.textContent = qualityInfo.icon;
        if (label) {
            if (readinessPercent < 100) {
                label.textContent = `${qualityInfo.label} (${Math.round(readinessPercent)}%)`;
            } else {
                label.textContent = qualityInfo.label;
            }
        }

        // Update tooltip
        indicator.setAttribute('data-tooltip', qualityInfo.description);
        indicator.classList.add('tooltip');
    }

    updateCapabilityStatus(capabilityData, progressData) {
        const statusPanel = document.getElementById('capabilityStatus');
        const statusBar = document.getElementById('capabilityStatusBar');

        // API returns data under capabilityData.summary, not directly on capabilityData
        const summary = capabilityData.summary || capabilityData;

        // Show/hide based on loading state
        const isLoading = (summary.overall?.readiness_percent || 0) < 100;

        if (statusPanel) {
            statusPanel.style.display = isLoading ? 'block' : 'none';
        }

        if (statusBar) {
            statusBar.style.display = isLoading ? 'block' : 'none';
        }

        if (!isLoading) return;

        // Update status bar
        this.updateCapabilityStatusBar(capabilityData, progressData);

        // Update detailed status panel
        if (statusPanel) {
            // Update overall progress
            const overallProgress = document.getElementById('overallProgress');
            const progressPercent = document.getElementById('progressPercent');
            const progressBar = document.getElementById('overallProgressBar');

            const readinessPercent = Math.round(summary.overall?.readiness_percent || 0);
            const overallProgressValue = Math.round(progressData.overall_progress || 0);

            if (overallProgress) {
                overallProgress.textContent = `${summary.overall?.available_capabilities || 0} of ${summary.overall?.total_capabilities || 0} ready`;
            }

            if (progressPercent) {
                progressPercent.textContent = `${overallProgressValue}%`;
            }

            if (progressBar) {
                progressBar.style.width = `${overallProgressValue}%`;

                // Update progress bar class based on completion
                progressBar.className = 'progress-fill';
                if (overallProgressValue < 100) {
                    progressBar.classList.add('loading');
                } else {
                    progressBar.classList.add('complete');
                }
            }

            // Update capability categories - use summary for category data
            this.updateCapabilityCategory('basic', summary.basic);
            this.updateCapabilityCategory('enhanced', summary.enhanced);
            this.updateCapabilityCategory('full', summary.full);
        }
    }

    updateCapabilityStatusBar(capabilityData, progressData) {
        const statusBar = document.getElementById('capabilityStatusBar');
        if (!statusBar) return;

        // API returns data under capabilityData.summary, not directly on capabilityData
        const summary = capabilityData.summary || capabilityData;
        const readinessPercent = Math.round(summary.overall?.readiness_percent || 0);
        const currentLevel = summary.overall?.current_level || 'basic';

        // Update status bar text
        const primaryText = statusBar.querySelector('.primary-text');
        const secondaryText = statusBar.querySelector('.secondary-text');

        if (primaryText) {
            if (readinessPercent < 30) {
                primaryText.textContent = 'AI System Starting';
            } else if (readinessPercent < 70) {
                primaryText.textContent = 'AI Models Loading';
            } else {
                primaryText.textContent = 'Finalizing Setup';
            }
        }

        if (secondaryText) {
            secondaryText.textContent = `${readinessPercent}% ready - ${this.getCapabilityLevelDescription(currentLevel)}`;
        }

        // Update quick indicators
        this.updateQuickIndicators(capabilityData);
    }

    updateQuickIndicators(capabilityData) {
        const quickIndicators = document.getElementById('quickIndicators');
        if (!quickIndicators) return;

        // API returns data under capabilityData.summary, not directly on capabilityData
        const summary = capabilityData.summary || capabilityData;

        // Define capability mappings to quick indicators
        const indicatorMappings = [
            { element: quickIndicators.children[0], capabilities: ['basic_chat', 'advanced_chat'], icon: '💬', name: 'Chat AI' },
            { element: quickIndicators.children[1], capabilities: ['document_upload', 'document_analysis'], icon: '📄', name: 'Document processing' },
            { element: quickIndicators.children[2], capabilities: ['simple_search', 'semantic_search'], icon: '🔍', name: 'Search' },
            { element: quickIndicators.children[3], capabilities: ['complex_reasoning', 'multimodal_processing'], icon: '🧠', name: 'Advanced analysis' }
        ];

        indicatorMappings.forEach(mapping => {
            if (!mapping.element) return;

            // Check if any of the mapped capabilities are available
            let isAvailable = false;
            let isLoading = false;

            for (const level of ['basic', 'enhanced', 'full']) {
                const levelData = summary[level];
                if (!levelData) continue;

                // Check available capabilities
                const available = levelData.available || [];
                if (available.some(cap => mapping.capabilities.includes(cap.name))) {
                    isAvailable = true;
                    break;
                }

                // Check loading capabilities
                const loading = levelData.loading || [];
                if (loading.some(cap => mapping.capabilities.includes(cap.name))) {
                    isLoading = true;
                }
            }

            // Update indicator appearance
            mapping.element.className = 'quick-indicator';
            mapping.element.textContent = mapping.icon;

            if (isAvailable) {
                mapping.element.classList.add('ready');
                mapping.element.setAttribute('data-tooltip', `${mapping.name} ready`);
            } else if (isLoading) {
                mapping.element.classList.add('loading');
                mapping.element.setAttribute('data-tooltip', `${mapping.name} loading`);
            } else {
                mapping.element.classList.add('pending');
                mapping.element.setAttribute('data-tooltip', `${mapping.name} pending`);
            }
        });
    }

    getCapabilityLevelDescription(level) {
        const descriptions = {
            basic: 'Basic features available',
            enhanced: 'Enhanced features available',
            full: 'All features ready'
        };
        return descriptions[level] || 'Starting up';
    }

    updateCapabilityCategory(level, categoryData) {
        const container = document.getElementById(`${level}Capabilities`);
        if (!container || !categoryData) return;

        container.innerHTML = '';

        // Add available capabilities
        categoryData.available?.forEach(cap => {
            const item = document.createElement('div');
            item.className = 'capability-item available tooltip';
            item.setAttribute('data-tooltip', cap.description);

            // Create capability-specific indicator
            const specificIndicator = this.getCapabilitySpecificIndicator(cap.name, 'available');

            item.innerHTML = `
                <span class="icon">${cap.indicator}</span>
                <span class="capability-name">${this.formatCapabilityName(cap.name)}</span>
                <span class="capability-specific-indicator">${specificIndicator}</span>
            `;
            container.appendChild(item);
        });

        // Add loading capabilities with progress bars
        categoryData.loading?.forEach(cap => {
            const item = document.createElement('div');
            item.className = 'capability-item loading tooltip';

            let tooltip = cap.description;
            if (cap.eta_seconds) {
                tooltip += ` (Ready in ${this.formatDuration(cap.eta_seconds)})`;
            }
            item.setAttribute('data-tooltip', tooltip);

            // Create capability-specific loading indicator
            const specificIndicator = this.getCapabilitySpecificIndicator(cap.name, 'loading');

            // Calculate progress percentage (if available)
            const progressPercent = cap.progress_percent || this.estimateProgressFromETA(cap.eta_seconds);

            item.innerHTML = `
                <div class="capability-item-header">
                    <span class="icon">${cap.indicator}</span>
                    <span class="capability-name">${this.formatCapabilityName(cap.name)}</span>
                    <span class="capability-specific-indicator">${specificIndicator}</span>
                    ${cap.eta_seconds ? `<span class="eta-display">${this.formatDuration(cap.eta_seconds)}</span>` : ''}
                </div>
                <div class="capability-progress-container">
                    <div class="capability-progress-bar">
                        <div class="capability-progress-fill" style="width: ${progressPercent}%"></div>
                    </div>
                    <div class="capability-progress-text">
                        <span class="progress-label">${this.getProgressLabel(cap.name, progressPercent)}</span>
                        <span class="progress-percent">${Math.round(progressPercent)}%</span>
                    </div>
                </div>
            `;
            container.appendChild(item);
        });

        // Show message if no capabilities in this category
        if (container.children.length === 0) {
            const item = document.createElement('div');
            item.className = 'capability-item unavailable';
            item.innerHTML = `<span>No ${level} capabilities</span>`;
            container.appendChild(item);
        }
    }

    updateLoadingMessage(capabilityData, progressData) {
        const loadingMessage = document.getElementById('loadingMessage');
        if (!loadingMessage) return;

        // API returns data under capabilityData.summary, not directly on capabilityData
        const summary = capabilityData.summary || capabilityData;
        const currentLevel = summary.overall?.current_level || 'basic';
        const readinessPercent = summary.overall?.readiness_percent || 0;
        const isLoading = readinessPercent < 100;

        if (!isLoading) {
            loadingMessage.style.display = 'none';
            return;
        }

        // Show loading message
        loadingMessage.style.display = 'flex';
        loadingMessage.className = `loading-message ${currentLevel}`;

        // Determine message content based on current state
        let primaryMessage, secondaryMessage;

        if (readinessPercent < 30) {
            primaryMessage = 'AI system is starting up...';
            secondaryMessage = 'Basic features will be available shortly. Full AI capabilities loading in background.';
        } else if (readinessPercent < 70) {
            primaryMessage = 'Enhanced AI features loading...';
            secondaryMessage = 'Some advanced features are now available. Full capabilities coming soon.';
        } else {
            primaryMessage = 'Final AI models loading...';
            secondaryMessage = 'Most features are ready. Advanced analysis capabilities finishing up.';
        }

        // Add ETA if available
        if (progressData.estimated_completion) {
            const eta = new Date(progressData.estimated_completion);
            const now = new Date();
            const secondsRemaining = Math.max(0, Math.floor((eta - now) / 1000));

            if (secondsRemaining > 0) {
                secondaryMessage += ` Full system ready in ${this.formatDuration(secondsRemaining)}.`;
            }
        }

        loadingMessage.innerHTML = `
            <div class="loading-spinner"></div>
            <div class="loading-text">
                <span class="primary">${primaryMessage}</span>
                <span class="secondary">${secondaryMessage}</span>
            </div>
        `;
    }

    handleUpdateError(error) {
        console.error('Capability update error:', error);

        // Update quality indicator to show error state
        const indicator = document.getElementById('qualityIndicator');
        if (indicator) {
            indicator.className = 'quality-indicator basic';
            indicator.innerHTML = `
                <span class="icon">⚠️</span>
                <span class="label">Connection Issue</span>
            `;
            indicator.setAttribute('data-tooltip', 'Unable to get system status. Retrying...');
        }

        // Hide capability status panel
        const statusPanel = document.getElementById('capabilityStatus');
        if (statusPanel) {
            statusPanel.style.display = 'none';
        }

        // Show error in loading message
        const loadingMessage = document.getElementById('loadingMessage');
        if (loadingMessage) {
            loadingMessage.style.display = 'flex';
            loadingMessage.className = 'loading-message basic';
            loadingMessage.innerHTML = `
                <div class="loading-spinner"></div>
                <div class="loading-text">
                    <span class="primary">Connection issue</span>
                    <span class="secondary">Trying to reconnect to system status...</span>
                </div>
            `;
        }
    }

    formatCapabilityName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    formatDuration(seconds) {
        if (seconds < 60) {
            return `${seconds}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = seconds % 60;
            return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
        }
    }

    getCapabilitySpecificIndicator(capabilityName, status) {
        // Define capability-specific indicators
        const indicators = {
            // Basic capabilities
            'health_check': {
                available: '✅',
                loading: '🔄',
                description: 'System monitoring active'
            },
            'simple_text': {
                available: '📝',
                loading: '⏳',
                description: 'Text processing ready'
            },
            'status_updates': {
                available: '📊',
                loading: '📈',
                description: 'Status reporting active'
            },

            // Enhanced capabilities
            'basic_chat': {
                available: '💬',
                loading: '🤖',
                description: 'Chat AI ready'
            },
            'simple_search': {
                available: '🔍',
                loading: '🔎',
                description: 'Search functionality ready'
            },
            'document_upload': {
                available: '📤',
                loading: '📋',
                description: 'Document upload ready'
            },

            // Full capabilities
            'advanced_chat': {
                available: '🧠',
                loading: '🤯',
                description: 'Advanced AI ready'
            },
            'semantic_search': {
                available: '🎯',
                loading: '🔍',
                description: 'Semantic search ready'
            },
            'document_analysis': {
                available: '📊',
                loading: '📄',
                description: 'Document analysis ready'
            },
            'complex_reasoning': {
                available: '🧮',
                loading: '💭',
                description: 'Complex reasoning ready'
            },
            'multimodal_processing': {
                available: '🎨',
                loading: '🖼️',
                description: 'Multimodal processing ready'
            }
        };

        const capabilityIndicator = indicators[capabilityName];
        if (capabilityIndicator) {
            return capabilityIndicator[status] || '❓';
        }

        // Default indicators based on status
        return status === 'available' ? '✅' : '⏳';
    }

    /**
     * Estimate progress percentage from ETA
     */
    estimateProgressFromETA(etaSeconds) {
        if (!etaSeconds || etaSeconds <= 0) return 95;

        // Estimate progress based on typical loading times
        const maxLoadTime = 300; // 5 minutes max
        const elapsed = maxLoadTime - etaSeconds;
        const progress = Math.max(0, Math.min(95, (elapsed / maxLoadTime) * 100));

        return Math.round(progress);
    }

    /**
     * Get progress label for capability
     */
    getProgressLabel(capabilityName, progressPercent) {
        const labels = {
            // Basic capabilities
            'health_check': {
                0: 'Initializing monitoring...',
                25: 'Setting up health checks...',
                50: 'Configuring endpoints...',
                75: 'Testing connectivity...',
                90: 'Almost ready...'
            },
            'simple_text': {
                0: 'Loading text processor...',
                25: 'Initializing tokenizer...',
                50: 'Setting up pipeline...',
                75: 'Testing processing...',
                90: 'Finalizing setup...'
            },
            'status_updates': {
                0: 'Setting up status system...',
                25: 'Configuring reporters...',
                50: 'Testing status flow...',
                75: 'Validating updates...',
                90: 'Ready to report...'
            },

            // Enhanced capabilities
            'basic_chat': {
                0: 'Loading chat model...',
                25: 'Initializing AI engine...',
                50: 'Setting up conversation...',
                75: 'Testing responses...',
                90: 'Chat ready...'
            },
            'simple_search': {
                0: 'Loading search index...',
                25: 'Building search engine...',
                50: 'Optimizing queries...',
                75: 'Testing search...',
                90: 'Search ready...'
            },
            'document_upload': {
                0: 'Setting up file handlers...',
                25: 'Configuring storage...',
                50: 'Testing uploads...',
                75: 'Validating formats...',
                90: 'Upload ready...'
            },

            // Full capabilities
            'advanced_chat': {
                0: 'Loading advanced AI...',
                25: 'Initializing reasoning...',
                50: 'Setting up context...',
                75: 'Testing intelligence...',
                90: 'AI ready...'
            },
            'semantic_search': {
                0: 'Loading semantic models...',
                25: 'Building embeddings...',
                50: 'Optimizing similarity...',
                75: 'Testing understanding...',
                90: 'Semantic search ready...'
            },
            'document_analysis': {
                0: 'Loading analysis models...',
                25: 'Setting up processors...',
                50: 'Configuring extractors...',
                75: 'Testing analysis...',
                90: 'Analysis ready...'
            },
            'complex_reasoning': {
                0: 'Loading reasoning engine...',
                25: 'Setting up logic chains...',
                50: 'Configuring inference...',
                75: 'Testing reasoning...',
                90: 'Reasoning ready...'
            },
            'multimodal_processing': {
                0: 'Loading multimodal AI...',
                25: 'Setting up vision...',
                50: 'Configuring audio...',
                75: 'Testing processing...',
                90: 'Multimodal ready...'
            }
        };

        const capabilityLabels = labels[capabilityName];
        if (!capabilityLabels) {
            return 'Loading...';
        }

        // Find the appropriate label based on progress
        const thresholds = [90, 75, 50, 25, 0];
        for (const threshold of thresholds) {
            if (progressPercent >= threshold) {
                return capabilityLabels[threshold] || 'Loading...';
            }
        }

        return 'Loading...';
    }

    // Public API methods

    /**
     * Get current capability level
     */
    getCurrentLevel() {
        // Handle both direct summary and nested summary structures
        const summary = this.capabilities?.summary || this.capabilities;
        const level = summary?.overall?.current_level || 'basic';
        console.debug('getCurrentLevel:', level, 'from capabilities:', this.capabilities);
        return level;
    }

    /**
     * Get readiness percentage
     */
    getReadinessPercent() {
        // Handle both direct summary and nested summary structures
        const summary = this.capabilities?.summary || this.capabilities;
        const percent = summary?.overall?.readiness_percent || 0;
        console.debug('getReadinessPercent:', percent);
        return percent;
    }

    /**
     * Check if a specific capability is available
     */
    isCapabilityAvailable(capabilityName) {
        const summary = this.capabilities.summary || this.capabilities;
        for (const level of ['basic', 'enhanced', 'full']) {
            const available = summary[level]?.available || [];
            if (available.some(cap => cap.name === capabilityName)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Get ETA for a specific capability
     */
    getCapabilityETA(capabilityName) {
        const summary = this.capabilities.summary || this.capabilities;
        for (const level of ['basic', 'enhanced', 'full']) {
            const loading = summary[level]?.loading || [];
            const cap = loading.find(c => c.name === capabilityName);
            if (cap) {
                return cap.eta_seconds;
            }
        }
        return null;
    }

    /**
     * Show expectation management notice
     */
    showExpectationNotice(message, type = 'info') {
        const chatMessages = document.getElementById('chatMessages');
        if (!chatMessages) return;

        const notice = document.createElement('div');
        notice.className = 'expectation-notice';
        notice.innerHTML = `
            <div class="expectation-notice-header">
                <span class="icon">ℹ️</span>
                <span>System Status</span>
            </div>
            <div class="expectation-notice-content">${message}</div>
        `;

        chatMessages.appendChild(notice);

        // Auto-remove after 10 seconds
        setTimeout(() => {
            if (notice.parentNode) {
                notice.remove();
            }
        }, 10000);
    }

    /**
     * Manually trigger capability update
     */
    async refresh() {
        await this.updateCapabilities();
    }

    /**
     * Destroy the manager and clean up
     */
    destroy() {
        this.stopMonitoring();

        // Remove event listeners
        document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        window.removeEventListener('focus', this.startMonitoring);
        window.removeEventListener('blur', this.stopMonitoring);

        console.log('Loading States Manager destroyed');
    }
}

// Global instance
let loadingStatesManager = null;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        loadingStatesManager = new LoadingStatesManager();
        // Export instance after creation
        window.loadingStatesManager = loadingStatesManager;
    });
} else {
    loadingStatesManager = new LoadingStatesManager();
    // Export instance after creation
    window.loadingStatesManager = loadingStatesManager;
}

// Export class for use in other scripts
window.LoadingStatesManager = LoadingStatesManager;