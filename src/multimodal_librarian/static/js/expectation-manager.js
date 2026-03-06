/**
 * Expectation Manager
 * 
 * Manages user expectations during system startup and loading phases.
 * Provides contextual messages, tooltips, and guidance based on current capabilities.
 */

class ExpectationManager {
    constructor() {
        this.currentCapabilities = {};
        this.userInteractions = [];
        this.messageTemplates = {};

        this.init();
    }

    init() {
        console.log('Initializing Expectation Manager');

        // Define message templates
        this.defineMessageTemplates();

        // Set up event listeners
        this.setupEventListeners();

        // Initialize tooltips
        this.initializeTooltips();
    }

    defineMessageTemplates() {
        this.messageTemplates = {
            // Request type specific messages
            chat: {
                basic: {
                    title: "Basic Chat Available",
                    message: "I can provide simple text responses right now. Advanced AI reasoning will be available in {eta}.",
                    suggestion: "Try asking basic questions or simple requests while the full AI loads."
                },
                enhanced: {
                    title: "Enhanced Chat Ready",
                    message: "I can handle most conversations with some AI features. Full advanced reasoning coming in {eta}.",
                    suggestion: "Feel free to ask questions - I can provide good responses with current capabilities."
                },
                full: {
                    title: "Full AI Chat Ready",
                    message: "All AI capabilities are loaded and ready for complex conversations and analysis.",
                    suggestion: "Ask me anything! I'm ready for complex questions, analysis, and reasoning."
                }
            },

            document_analysis: {
                basic: {
                    title: "Document Upload Available",
                    message: "You can upload documents, but analysis features are still loading. Full processing ready in {eta}.",
                    suggestion: "Upload documents now - they'll be processed as soon as analysis capabilities are ready."
                },
                enhanced: {
                    title: "Basic Document Processing Ready",
                    message: "I can process documents with basic analysis. Advanced document understanding coming in {eta}.",
                    suggestion: "Upload documents for basic processing. Advanced features will enhance results automatically."
                },
                full: {
                    title: "Full Document Analysis Ready",
                    message: "Complete document analysis capabilities are available including advanced understanding and insights.",
                    suggestion: "Upload any document type for comprehensive analysis and insights."
                }
            },

            search: {
                basic: {
                    title: "Basic Search Available",
                    message: "Simple text search is working. Semantic search and advanced features loading in {eta}.",
                    suggestion: "Try basic keyword searches while advanced semantic search loads."
                },
                enhanced: {
                    title: "Enhanced Search Ready",
                    message: "Good search capabilities available with some semantic understanding. Full features coming in {eta}.",
                    suggestion: "Search works well now with natural language queries and basic semantic matching."
                },
                full: {
                    title: "Advanced Search Ready",
                    message: "Full semantic search with advanced understanding and context-aware results is available.",
                    suggestion: "Use natural language queries for the best search experience with full semantic understanding."
                }
            },

            complex_analysis: {
                basic: {
                    title: "Analysis Features Loading",
                    message: "Complex analysis capabilities are not yet available. Basic responses only. Full analysis ready in {eta}.",
                    suggestion: "I can provide basic information now. Complex analysis will be available shortly."
                },
                enhanced: {
                    title: "Some Analysis Available",
                    message: "Basic analysis features are working. Advanced reasoning and complex analysis coming in {eta}.",
                    suggestion: "I can handle moderate complexity analysis. Advanced features will enhance results soon."
                },
                full: {
                    title: "Full Analysis Ready",
                    message: "All analysis capabilities including complex reasoning, multi-step analysis, and advanced insights are ready.",
                    suggestion: "Ask for any type of analysis - I'm ready for complex, multi-step reasoning tasks."
                }
            }
        };
    }

    setupEventListeners() {
        // Listen for input focus to show contextual help
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.addEventListener('focus', () => {
                this.showContextualHelp();
            });

            messageInput.addEventListener('input', (e) => {
                this.analyzeUserInput(e.target.value);
            });
        }

        // Listen for form submission to provide feedback
        const chatForm = document.getElementById('chatForm');
        if (chatForm) {
            chatForm.addEventListener('submit', (e) => {
                this.handleRequestSubmission(e);
            });
        }

        // File upload feedback is handled by the upload handler after actual upload completes
        // (not on file selection)

        // Listen for capability updates from loading states manager
        if (window.loadingStatesManager) {
            // Update immediately
            this.updateCapabilities();

            // Check for updates periodically
            setInterval(() => {
                this.updateCapabilities();
            }, 3000);
        }

        // Listen for capabilitiesLoaded event to update immediately
        window.addEventListener('capabilitiesLoaded', () => {
            console.log('ExpectationManager: capabilitiesLoaded event received');
            this.updateCapabilities();
        });
    }

    initializeTooltips() {
        // Add tooltips to existing elements
        this.addTooltipToElement('sendBtn', 'Send your message. Response quality depends on current AI capabilities.');
        this.addTooltipToElement('uploadBtn', 'Upload documents. Processing capabilities depend on current system status.');
        this.addTooltipToElement('newChatBtn', 'Start a new conversation. All current capabilities will be available.');

        // Add dynamic tooltips that update based on system state
        this.setupDynamicTooltips();

        // Initialize tooltip event listeners
        this.setupTooltipEventListeners();
    }

    addTooltipToElement(elementId, tooltipText, dynamic = false) {
        const element = document.getElementById(elementId);
        if (element) {
            element.classList.add('tooltip');
            if (dynamic) {
                element.setAttribute('data-tooltip-dynamic', 'true');
                element.setAttribute('data-tooltip-base', tooltipText);
            } else {
                element.setAttribute('data-tooltip', tooltipText);
            }
        }
    }

    setupDynamicTooltips() {
        // Add dynamic tooltips that change based on system state
        this.addTooltipToElement('messageInput', 'Type your message here. Response quality will match current system capabilities.', true);
        this.addTooltipToElement('fileInput', 'Upload documents for analysis. Processing speed depends on current capabilities.', true);

        // Add tooltips to quality indicators if they exist
        const qualityIndicators = document.querySelectorAll('.quality-indicator');
        qualityIndicators.forEach(indicator => {
            this.addQualityIndicatorTooltip(indicator);
        });

        // Add tooltips to capability items
        const capabilityItems = document.querySelectorAll('.capability-item');
        capabilityItems.forEach(item => {
            this.addCapabilityItemTooltip(item);
        });
    }

    addQualityIndicatorTooltip(indicator) {
        const level = indicator.classList.contains('basic') ? 'basic' :
            indicator.classList.contains('enhanced') ? 'enhanced' : 'full';

        const tooltips = {
            basic: 'Basic mode: Simple responses and text processing. Enhanced features loading...',
            enhanced: 'Enhanced mode: Good AI capabilities with some advanced features. Full AI loading...',
            full: 'Full mode: All AI capabilities available including complex reasoning and analysis.'
        };

        indicator.classList.add('tooltip');
        indicator.setAttribute('data-tooltip', tooltips[level]);
    }

    addCapabilityItemTooltip(item) {
        const capabilityName = item.querySelector('.capability-name')?.textContent || 'Feature';
        const isAvailable = item.classList.contains('available');
        const isLoading = item.classList.contains('loading');

        let tooltip = '';
        if (isAvailable) {
            tooltip = `${capabilityName} is ready and fully functional.`;
        } else if (isLoading) {
            tooltip = `${capabilityName} is currently loading. Progress shown below.`;
        } else {
            tooltip = `${capabilityName} is not yet available. Will load after prerequisites are ready.`;
        }

        item.classList.add('tooltip');
        item.setAttribute('data-tooltip', tooltip);
    }

    setupTooltipEventListeners() {
        // Enhanced tooltip behavior with hover delays and positioning
        document.addEventListener('mouseover', (e) => {
            if (e.target.classList.contains('tooltip')) {
                this.showTooltip(e.target, e);
            }
        });

        document.addEventListener('mouseout', (e) => {
            if (e.target.classList.contains('tooltip')) {
                this.hideTooltip(e.target);
            }
        });

        // Update dynamic tooltips periodically
        setInterval(() => {
            this.updateDynamicTooltips();
        }, 5000);
    }

    showTooltip(element, event) {
        // Remove any existing tooltip
        this.hideAllTooltips();

        const isDynamic = element.getAttribute('data-tooltip-dynamic') === 'true';
        let tooltipText = '';

        if (isDynamic) {
            tooltipText = this.generateDynamicTooltip(element);
        } else {
            tooltipText = element.getAttribute('data-tooltip');
        }

        if (!tooltipText) return;

        // Create tooltip element
        const tooltip = document.createElement('div');
        tooltip.className = 'expectation-tooltip';
        tooltip.innerHTML = tooltipText;

        // Position tooltip
        document.body.appendChild(tooltip);
        this.positionTooltip(tooltip, element, event);

        // Store reference for cleanup
        element._tooltip = tooltip;

        // Auto-hide after delay for mobile
        if (this.isMobileDevice()) {
            setTimeout(() => {
                this.hideTooltip(element);
            }, 3000);
        }
    }

    hideTooltip(element) {
        if (element._tooltip) {
            element._tooltip.remove();
            element._tooltip = null;
        }
    }

    hideAllTooltips() {
        document.querySelectorAll('.expectation-tooltip').forEach(tooltip => {
            tooltip.remove();
        });

        // Clear references
        document.querySelectorAll('.tooltip').forEach(element => {
            element._tooltip = null;
        });
    }

    positionTooltip(tooltip, element, event) {
        const rect = element.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
        let top = rect.top - tooltipRect.height - 10;

        // Adjust horizontal position if tooltip goes off screen
        if (left < 10) {
            left = 10;
        } else if (left + tooltipRect.width > viewportWidth - 10) {
            left = viewportWidth - tooltipRect.width - 10;
        }

        // Adjust vertical position if tooltip goes off screen
        if (top < 10) {
            top = rect.bottom + 10;
            tooltip.classList.add('tooltip-below');
        } else {
            tooltip.classList.add('tooltip-above');
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    generateDynamicTooltip(element) {
        const baseTooltip = element.getAttribute('data-tooltip-base');
        const level = this.currentCapabilities.level || 'basic';
        const readiness = this.currentCapabilities.readiness || 0;

        let dynamicContent = '';

        // Add current status information
        if (level === 'basic') {
            dynamicContent = `<br><small>Current: Basic mode (${Math.round(readiness)}% ready)</small>`;
        } else if (level === 'enhanced') {
            dynamicContent = `<br><small>Current: Enhanced mode (${Math.round(readiness)}% ready)</small>`;
        } else {
            dynamicContent = `<br><small>Current: Full AI mode ready</small>`;
        }

        // Add specific guidance based on element
        const elementId = element.id;
        if (elementId === 'messageInput') {
            const guidance = this.getInputGuidanceForCurrentState();
            if (guidance) {
                dynamicContent += `<br><small><strong>Tip:</strong> ${guidance}</small>`;
            }
        } else if (elementId === 'fileInput') {
            const guidance = this.getFileUploadGuidanceForCurrentState();
            if (guidance) {
                dynamicContent += `<br><small><strong>Tip:</strong> ${guidance}</small>`;
            }
        }

        return baseTooltip + dynamicContent;
    }

    getInputGuidanceForCurrentState() {
        const level = this.currentCapabilities.level || 'basic';

        const guidance = {
            basic: 'Try simple questions while advanced AI loads.',
            enhanced: 'Most questions work well. Complex analysis coming soon.',
            full: 'Ask anything! Full AI capabilities are ready.'
        };

        return guidance[level];
    }

    getFileUploadGuidanceForCurrentState() {
        const level = this.currentCapabilities.level || 'basic';

        const guidance = {
            basic: 'Upload now - files will be processed as capabilities load.',
            enhanced: 'Basic document processing available. Advanced analysis loading.',
            full: 'Full document analysis ready for comprehensive insights.'
        };

        return guidance[level];
    }

    updateDynamicTooltips() {
        // Update tooltips for elements that are currently visible
        document.querySelectorAll('[data-tooltip-dynamic="true"]').forEach(element => {
            if (element._tooltip) {
                // Update the tooltip content if it's currently shown
                const newContent = this.generateDynamicTooltip(element);
                element._tooltip.innerHTML = newContent;
            }
        });

        // Update capability item tooltips
        document.querySelectorAll('.capability-item').forEach(item => {
            this.addCapabilityItemTooltip(item);
        });
    }

    isMobileDevice() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
            window.innerWidth <= 768;
    }

    updateCapabilities() {
        if (window.loadingStatesManager) {
            const level = window.loadingStatesManager.getCurrentLevel();
            const readiness = window.loadingStatesManager.getReadinessPercent();

            // Only update if we have valid data (not defaults)
            if (level && readiness !== undefined) {
                this.currentCapabilities = {
                    level: level,
                    readiness: readiness,
                    capabilities: window.loadingStatesManager.capabilities
                };
                console.log('ExpectationManager: Updated capabilities from loadingStatesManager', this.currentCapabilities);
            }
        }
    }

    showContextualHelp() {
        // First, try to get the latest capabilities
        this.updateCapabilities();

        const level = this.currentCapabilities.level || 'basic';
        const readiness = this.currentCapabilities.readiness || 0;

        // Don't show help when fully ready or at full level
        if (readiness >= 100 || level === 'full') {
            console.log('showContextualHelp: System is ready, not showing help', { level, readiness });
            return;
        }

        // If we still don't have valid data, fetch from API before showing
        if (!this.currentCapabilities.level || this.currentCapabilities.readiness === 0) {
            // Fetch capabilities asynchronously and then decide
            fetch('/api/loading/capabilities')
                .then(response => response.json())
                .then(data => {
                    const summary = data.summary || data;
                    const apiLevel = summary.overall?.current_level || 'basic';
                    const apiReadiness = summary.overall?.readiness_percent || 0;

                    // Update cached capabilities
                    this.currentCapabilities = {
                        level: apiLevel,
                        readiness: apiReadiness,
                        capabilities: data
                    };

                    // Only show if not ready
                    if (apiReadiness < 100 && apiLevel !== 'full') {
                        const helpMessage = this.generateContextualHelpMessage(apiLevel, apiReadiness);
                        const specificIndicators = this.getSpecificCapabilityIndicators(apiLevel, apiReadiness);
                        this.showTemporaryMessage(helpMessage + specificIndicators, 'info', 5000);
                    }
                })
                .catch(error => console.error('Failed to fetch capabilities:', error));
            return;
        }

        // Show help based on current capabilities with specific indicators
        const helpMessage = this.generateContextualHelpMessage(level, readiness);
        const specificIndicators = this.getSpecificCapabilityIndicators(level, readiness);

        this.showTemporaryMessage(helpMessage + specificIndicators, 'info', 5000);
    }

    generateContextualHelpMessage(level, readiness) {
        const messages = {
            basic: `⚡ Basic mode active (${Math.round(readiness)}% ready). I can handle simple questions and text processing. Advanced AI features are loading...`,
            enhanced: `🔄 Enhanced mode active (${Math.round(readiness)}% ready). I can handle most requests with good AI capabilities. Full features loading...`,
            full: `🧠 Full AI mode ready! All capabilities are available for complex analysis and reasoning.`
        };

        return messages[level] || messages.basic;
    }

    getSpecificCapabilityIndicators(level, readiness) {
        let indicators = '<br><br><strong>Current Capabilities:</strong><br>';

        if (level === 'basic') {
            indicators += '✅ Simple text responses<br>';
            indicators += '✅ Basic status updates<br>';
            indicators += '🔄 Chat AI loading...<br>';
            indicators += '⏳ Document processing loading...<br>';
            indicators += '⏳ Advanced search loading...';
        } else if (level === 'enhanced') {
            indicators += '✅ Simple text responses<br>';
            indicators += '✅ Basic chat AI<br>';
            indicators += '✅ Simple search<br>';
            indicators += '🔄 Advanced AI loading...<br>';
            indicators += '🔄 Document analysis loading...<br>';
            indicators += '⏳ Complex reasoning loading...';
        } else {
            indicators += '✅ All capabilities ready!<br>';
            indicators += '🧠 Advanced AI, 📊 Document analysis, 🎯 Semantic search';
        }

        return indicators;
    }

    analyzeUserInput(input) {
        if (!input || input.length < 10) return;

        // Analyze input to determine request type
        const requestType = this.classifyRequest(input);
        const level = this.currentCapabilities.level || 'basic';

        // Show appropriate expectation message
        this.showRequestTypeGuidance(requestType, level);
    }

    classifyRequest(input) {
        const lowerInput = input.toLowerCase();

        // Document analysis keywords
        if (lowerInput.includes('analyze') || lowerInput.includes('document') ||
            lowerInput.includes('pdf') || lowerInput.includes('file')) {
            return 'document_analysis';
        }

        // Search keywords
        if (lowerInput.includes('search') || lowerInput.includes('find') ||
            lowerInput.includes('look for') || lowerInput.includes('query')) {
            return 'search';
        }

        // Complex analysis keywords
        if (lowerInput.includes('complex') || lowerInput.includes('detailed') ||
            lowerInput.includes('comprehensive') || lowerInput.includes('in-depth') ||
            lowerInput.includes('reasoning') || lowerInput.includes('analysis')) {
            return 'complex_analysis';
        }

        // Default to chat
        return 'chat';
    }

    showRequestTypeGuidance(requestType, level) {
        const template = this.messageTemplates[requestType]?.[level];
        if (!template) return;

        // Calculate ETA for next level
        const eta = this.calculateETAForNextLevel(level);
        const message = template.message.replace('{eta}', eta);

        // Get capability-specific indicators for this request type
        const specificIndicators = this.getRequestTypeIndicators(requestType, level);

        // Show guidance tooltip near input
        this.showInputGuidance(template.title, message, template.suggestion, specificIndicators);
    }

    getRequestTypeIndicators(requestType, level) {
        const indicators = {
            chat: {
                basic: '💬 Basic text chat ready',
                enhanced: '🤖 AI chat with reasoning ready',
                full: '🧠 Advanced AI with full reasoning ready'
            },
            document_analysis: {
                basic: '📄 Document upload ready, analysis pending',
                enhanced: '📊 Basic document processing ready',
                full: '🎯 Full document analysis with insights ready'
            },
            search: {
                basic: '🔍 Basic text search ready',
                enhanced: '🔎 Enhanced search with some semantic understanding',
                full: '🎯 Full semantic search with context awareness'
            },
            complex_analysis: {
                basic: '⚡ Simple responses only',
                enhanced: '🔄 Some analytical capabilities ready',
                full: '🧮 Full complex reasoning and analysis ready'
            }
        };

        return indicators[requestType]?.[level] || '⚡ Basic functionality ready';
    }

    calculateETAForNextLevel(currentLevel) {
        // Simplified ETA calculation
        const etas = {
            basic: '30-60 seconds',
            enhanced: '1-2 minutes',
            full: 'ready now'
        };

        if (currentLevel === 'basic') return etas.basic;
        if (currentLevel === 'enhanced') return etas.enhanced;
        return etas.full;
    }

    showInputGuidance(title, message, suggestion, specificIndicators = '') {
        // Remove existing guidance
        const existingGuidance = document.getElementById('inputGuidance');
        if (existingGuidance) {
            existingGuidance.remove();
        }

        // Get current progress for relevant capabilities
        const progressInfo = this.getRelevantProgressInfo(title);

        // Create guidance popup
        const guidance = document.createElement('div');
        guidance.id = 'inputGuidance';
        guidance.className = 'expectation-notice';
        guidance.style.cssText = `
            position: absolute;
            bottom: 100%;
            left: 0;
            right: 0;
            margin-bottom: 0.5rem;
            z-index: 1000;
            animation: fadeIn 0.3s ease;
        `;

        guidance.innerHTML = `
            <div class="expectation-notice-header">
                <span class="icon">💡</span>
                <span>${title}</span>
                <button class="close-btn" onclick="this.parentElement.parentElement.remove()" style="margin-left: auto; background: none; border: none; cursor: pointer; color: inherit;">×</button>
            </div>
            <div class="expectation-notice-content">
                <p>${message}</p>
                ${specificIndicators ? `<div class="capability-indicators"><strong>Current Status:</strong> ${specificIndicators}</div>` : ''}
                ${progressInfo ? this.createProgressInfoHTML(progressInfo) : ''}
                <p><strong>Tip:</strong> ${suggestion}</p>
            </div>
        `;

        // Add to input container
        const inputContainer = document.querySelector('.chat-input-container');
        if (inputContainer) {
            inputContainer.style.position = 'relative';
            inputContainer.appendChild(guidance);

            // Auto-remove after 8 seconds
            setTimeout(() => {
                if (guidance.parentNode) {
                    guidance.remove();
                }
            }, 8000);
        }
    }

    /**
     * Get relevant progress information for a capability type
     */
    getRelevantProgressInfo(title) {
        if (!window.loadingStatesManager || !window.loadingStatesManager.capabilities) {
            return null;
        }

        const capabilities = window.loadingStatesManager.capabilities;
        const progressData = window.loadingStatesManager.loadingProgress;

        // Map titles to capability types
        const titleMappings = {
            'Basic Chat Available': ['basic_chat', 'simple_text'],
            'Enhanced Chat Ready': ['advanced_chat', 'basic_chat'],
            'Full AI Chat Ready': ['complex_reasoning', 'advanced_chat'],
            'Document Upload Available': ['document_upload'],
            'Basic Document Processing Ready': ['document_analysis'],
            'Full Document Analysis Ready': ['document_analysis', 'complex_reasoning'],
            'Basic Search Available': ['simple_search'],
            'Enhanced Search Ready': ['semantic_search'],
            'Advanced Search Ready': ['semantic_search', 'complex_reasoning'],
            'Analysis Features Loading': ['complex_reasoning'],
            'Some Analysis Available': ['complex_reasoning'],
            'Full Analysis Ready': ['complex_reasoning', 'multimodal_processing']
        };

        const relevantCapabilities = titleMappings[title] || [];
        if (relevantCapabilities.length === 0) return null;

        // Find progress info for relevant capabilities
        const progressInfo = [];
        for (const capName of relevantCapabilities) {
            // Look through all capability levels
            for (const level of ['basic', 'enhanced', 'full']) {
                const levelData = capabilities[level];
                if (!levelData) continue;

                // Check loading capabilities
                const loading = levelData.loading || [];
                const loadingCap = loading.find(cap => cap.name === capName);
                if (loadingCap) {
                    // Use progress_percent if available, otherwise estimate from ETA
                    const progressPercent = loadingCap.progress_percent || this.estimateProgressFromETA(loadingCap.eta_seconds);

                    progressInfo.push({
                        name: capName,
                        displayName: this.formatCapabilityName(capName),
                        progress: progressPercent,
                        eta: loadingCap.eta_seconds,
                        eta_confidence: loadingCap.eta_confidence || 0.5,
                        eta_range: loadingCap.eta_range || null,
                        status: 'loading'
                    });
                }

                // Check available capabilities
                const available = levelData.available || [];
                const availableCap = available.find(cap => cap.name === capName);
                if (availableCap) {
                    progressInfo.push({
                        name: capName,
                        displayName: this.formatCapabilityName(capName),
                        progress: 100,
                        eta: 0,
                        eta_confidence: 1.0,
                        eta_range: null,
                        status: 'ready'
                    });
                }
            }
        }

        return progressInfo.length > 0 ? progressInfo : null;
    }

    /**
     * Create HTML for progress information
     */
    createProgressInfoHTML(progressInfo) {
        if (!progressInfo || progressInfo.length === 0) return '';

        const progressHTML = progressInfo.map(info => {
            const progressPercent = Math.round(info.progress);
            const confidence = info.eta_confidence || 0.5;
            const etaRange = info.eta_range;

            // Format ETA with confidence
            let etaText = '';
            if (info.eta > 0) {
                const etaDisplay = this.formatDuration(info.eta);

                // Show confidence indicator
                const confidenceIndicator = confidence >= 0.8 ? '✓' : confidence >= 0.5 ? '~' : '?';
                const confidenceClass = confidence >= 0.8 ? 'high-confidence' : confidence >= 0.5 ? 'medium-confidence' : 'low-confidence';

                etaText = `<span class="eta-with-confidence ${confidenceClass}">${confidenceIndicator} ${etaDisplay}</span>`;

                // Add range if available and confidence is not high
                if (etaRange && confidence < 0.8) {
                    const minEta = this.formatDuration(etaRange.min_seconds);
                    const maxEta = this.formatDuration(etaRange.max_seconds);
                    etaText += `<span class="eta-range"> (${minEta}-${maxEta})</span>`;
                }
            }

            return `
                <div class="progress-info-item">
                    <div class="progress-info-header">
                        <span class="progress-info-name">${info.displayName}</span>
                        <span class="progress-info-percent">${progressPercent}%</span>
                    </div>
                    <div class="progress-info-bar">
                        <div class="progress-info-fill ${info.status}" style="width: ${progressPercent}%"></div>
                    </div>
                    ${info.eta > 0 ? `<div class="progress-info-eta">Ready in ${etaText}</div>` : ''}
                </div>
            `;
        }).join('');

        return `
            <div class="progress-info-container">
                <strong>Loading Progress:</strong>
                ${progressHTML}
                <div class="confidence-legend">
                    <small>
                        <span class="high-confidence">✓ High confidence</span>
                        <span class="medium-confidence">~ Estimated</span>
                        <span class="low-confidence">? Approximate</span>
                    </small>
                </div>
            </div>
        `;
    }

    /**
     * Estimate progress from ETA (helper method)
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
     * Format capability name (helper method)
     */
    formatCapabilityName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    /**
     * Format duration (helper method)
     */
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

    handleRequestSubmission(event) {
        const input = document.getElementById('messageInput');
        if (!input) return;

        const message = input.value.trim();
        if (!message) return;

        // Analyze the request
        const requestType = this.classifyRequest(message);
        const level = this.currentCapabilities.level || 'basic';

        // Track user interaction
        this.userInteractions.push({
            timestamp: Date.now(),
            requestType,
            level,
            message: message.substring(0, 100) // First 100 chars for analysis
        });

        // Show appropriate feedback
        this.showRequestFeedback(requestType, level);
    }

    showRequestFeedback(requestType, level) {
        const readiness = this.currentCapabilities.readiness || 0;

        if (readiness >= 100) {
            return; // No feedback needed when fully ready
        }

        let feedbackMessage = '';

        if (level === 'basic') {
            feedbackMessage = `⚡ Processing with basic capabilities. Enhanced features will improve this response automatically as they load.`;
        } else if (level === 'enhanced') {
            feedbackMessage = `🔄 Processing with enhanced capabilities. Full AI features will provide even better results shortly.`;
        }

        if (feedbackMessage) {
            this.showTemporaryMessage(feedbackMessage, 'info', 4000);
        }
    }

    handleFileUpload() {
        const level = this.currentCapabilities.level || 'basic';
        const readiness = this.currentCapabilities.readiness || 0;

        let message = '';

        if (level === 'basic') {
            message = '📄 File uploaded! Basic processing available now. Advanced document analysis will enhance results as capabilities load.';
        } else if (level === 'enhanced') {
            message = '📄 File uploaded! Good processing capabilities available. Full document analysis features will enhance results shortly.';
        } else {
            message = '📄 File uploaded! Full document analysis capabilities are ready for comprehensive processing.';
        }

        this.showTemporaryMessage(message, 'success', 5000);
    }

    showTemporaryMessage(message, type = 'info', duration = 5000) {
        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = `temporary-message ${type}`;
        messageEl.style.cssText = `
            position: fixed;
            top: 1rem;
            right: 1rem;
            background: ${type === 'success' ? '#d1fae5' : type === 'warning' ? '#fef3c7' : '#f0f9ff'};
            border: 1px solid ${type === 'success' ? '#10b981' : type === 'warning' ? '#f59e0b' : '#0ea5e9'};
            color: ${type === 'success' ? '#065f46' : type === 'warning' ? '#92400e' : '#0c4a6e'};
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            max-width: 300px;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        `;

        messageEl.innerHTML = `
            <div style="display: flex; align-items: flex-start; gap: 0.5rem;">
                <span style="font-size: 1.25rem;">${type === 'success' ? '✅' : type === 'warning' ? '⚠️' : 'ℹ️'}</span>
                <div style="flex: 1; font-size: 0.875rem; line-height: 1.4;">${message}</div>
                <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; cursor: pointer; color: inherit; font-size: 1.25rem; line-height: 1; padding: 0;">×</button>
            </div>
        `;

        // Add CSS animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        document.body.appendChild(messageEl);

        // Auto-remove
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => {
                    if (messageEl.parentNode) {
                        messageEl.remove();
                    }
                }, 300);
            }
        }, duration);
    }

    // Public API methods

    /**
     * Show a custom expectation message
     */
    showCustomMessage(title, message, type = 'info') {
        this.showTemporaryMessage(`<strong>${title}</strong><br>${message}`, type, 6000);
    }

    /**
     * Get user interaction analytics
     */
    getInteractionAnalytics() {
        const now = Date.now();
        const recentInteractions = this.userInteractions.filter(
            interaction => now - interaction.timestamp < 300000 // Last 5 minutes
        );

        return {
            total_interactions: this.userInteractions.length,
            recent_interactions: recentInteractions.length,
            request_types: this.analyzeRequestTypes(recentInteractions),
            capability_levels: this.analyzeCapabilityLevels(recentInteractions)
        };
    }

    analyzeRequestTypes(interactions) {
        const types = {};
        interactions.forEach(interaction => {
            types[interaction.requestType] = (types[interaction.requestType] || 0) + 1;
        });
        return types;
    }

    analyzeCapabilityLevels(interactions) {
        const levels = {};
        interactions.forEach(interaction => {
            levels[interaction.level] = (levels[interaction.level] || 0) + 1;
        });
        return levels;
    }

    /**
     * Reset interaction tracking
     */
    resetAnalytics() {
        this.userInteractions = [];
    }

    /**
     * Destroy the manager and clean up
     */
    destroy() {
        // Remove event listeners
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.removeEventListener('focus', this.showContextualHelp);
            messageInput.removeEventListener('input', this.analyzeUserInput);
        }

        // Remove any temporary messages
        document.querySelectorAll('.temporary-message').forEach(el => el.remove());
        document.querySelectorAll('#inputGuidance').forEach(el => el.remove());

        console.log('Expectation Manager destroyed');
    }
}

// Global instance
let expectationManager = null;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        expectationManager = new ExpectationManager();
        // Export instance after creation
        window.expectationManager = expectationManager;
    });
} else {
    expectationManager = new ExpectationManager();
    // Export instance after creation
    window.expectationManager = expectationManager;
}

// Export class for use in other scripts
window.ExpectationManager = ExpectationManager;