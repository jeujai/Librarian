/**
 * Limitation Messages Manager
 * 
 * Provides informative messages about current system limitations
 * and what users can expect during different loading phases.
 */

class LimitationMessagesManager {
    constructor() {
        this.currentLevel = 'basic';
        this.capabilities = {};
        this.messageContainer = null;
        this.activeMessages = new Set();

        // Message templates for different limitation scenarios
        this.limitationTemplates = {
            // Chat limitations
            chat_basic: {
                title: "Limited Chat Capabilities",
                message: "I can provide simple text responses but advanced AI reasoning is still loading.",
                limitations: [
                    "No complex analysis or multi-step reasoning",
                    "Limited context understanding",
                    "Basic text processing only"
                ],
                workarounds: [
                    "Ask simple, direct questions",
                    "Break complex requests into smaller parts",
                    "Use basic keywords for better results"
                ],
                eta_message: "Advanced chat AI will be ready in {eta}"
            },

            chat_enhanced: {
                title: "Partial Chat Capabilities",
                message: "I can handle most conversations with good AI features, but some advanced capabilities are still loading.",
                limitations: [
                    "Complex reasoning may be slower",
                    "Limited multimodal understanding",
                    "Some specialized knowledge areas unavailable"
                ],
                workarounds: [
                    "Most questions work well now",
                    "Try rephrasing if responses seem limited",
                    "Basic analysis and explanations available"
                ],
                eta_message: "Full AI capabilities ready in {eta}"
            },

            // Document processing limitations
            document_basic: {
                title: "Document Upload Only",
                message: "You can upload documents, but analysis features are not yet available.",
                limitations: [
                    "No document content analysis",
                    "No text extraction or summarization",
                    "No document-based Q&A"
                ],
                workarounds: [
                    "Upload documents now - they'll be queued for processing",
                    "Basic file information will be shown",
                    "Processing will start automatically when ready"
                ],
                eta_message: "Document analysis ready in {eta}"
            },

            document_enhanced: {
                title: "Basic Document Processing",
                message: "I can process documents with basic analysis, but advanced features are still loading.",
                limitations: [
                    "Limited content understanding",
                    "Basic summarization only",
                    "No complex document relationships"
                ],
                workarounds: [
                    "Upload any document type",
                    "Ask for basic summaries or key points",
                    "Advanced analysis will enhance results automatically"
                ],
                eta_message: "Full document analysis ready in {eta}"
            },

            // Search limitations
            search_basic: {
                title: "Basic Search Only",
                message: "Simple keyword search is available, but semantic search is still loading.",
                limitations: [
                    "Keyword matching only",
                    "No context understanding",
                    "Limited result relevance"
                ],
                workarounds: [
                    "Use specific keywords",
                    "Try multiple search terms",
                    "Results will improve as semantic search loads"
                ],
                eta_message: "Semantic search ready in {eta}"
            },

            search_enhanced: {
                title: "Enhanced Search Available",
                message: "Good search with some semantic understanding, but full features are still loading.",
                limitations: [
                    "Some context nuances may be missed",
                    "Limited cross-document connections",
                    "Advanced filtering not fully available"
                ],
                workarounds: [
                    "Natural language queries work well",
                    "Try different phrasings for better results",
                    "Most searches will return relevant results"
                ],
                eta_message: "Full semantic search ready in {eta}"
            },

            // Analysis limitations
            analysis_basic: {
                title: "No Complex Analysis",
                message: "Complex analysis and reasoning capabilities are not yet available.",
                limitations: [
                    "No multi-step reasoning",
                    "No data analysis or insights",
                    "No comparative analysis"
                ],
                workarounds: [
                    "Ask for basic information instead",
                    "Request simple explanations",
                    "Complex analysis will be available shortly"
                ],
                eta_message: "Analysis capabilities ready in {eta}"
            },

            analysis_enhanced: {
                title: "Basic Analysis Available",
                message: "I can perform basic analysis, but advanced reasoning is still loading.",
                limitations: [
                    "Limited depth of analysis",
                    "No advanced statistical processing",
                    "Simplified reasoning chains"
                ],
                workarounds: [
                    "Ask for step-by-step explanations",
                    "Request basic comparisons",
                    "Advanced insights will enhance results soon"
                ],
                eta_message: "Full analysis capabilities ready in {eta}"
            },

            // General system limitations
            system_startup: {
                title: "System Starting Up",
                message: "The AI system is initializing. Basic functionality will be available shortly.",
                limitations: [
                    "Most AI features unavailable",
                    "Limited processing capabilities",
                    "Responses may be delayed"
                ],
                workarounds: [
                    "Wait for basic features to load",
                    "Try simple text interactions",
                    "System will improve rapidly"
                ],
                eta_message: "Basic features ready in {eta}"
            },

            system_loading: {
                title: "AI Models Loading",
                message: "Core AI models are loading. Some features may be limited or slower than usual.",
                limitations: [
                    "Slower response times",
                    "Some features temporarily unavailable",
                    "Quality may vary during loading"
                ],
                workarounds: [
                    "Be patient with response times",
                    "Try again if responses seem limited",
                    "Performance will improve as loading completes"
                ],
                eta_message: "Full performance ready in {eta}"
            }
        };

        this.init();
    }

    init() {
        console.log('Initializing Limitation Messages Manager');

        // Create message container
        this.createMessageContainer();

        // Wait for capabilities to be loaded before setting up listeners
        window.addEventListener('capabilitiesLoaded', () => {
            console.log('Capabilities loaded, setting up limitation listeners');
            this.updateFromCapabilities();

            // Only set up interaction listeners after we know the system state
            // This prevents showing limitation messages when system is already ready
            if (this.currentLevel !== 'full') {
                this.setupInteractionListeners();
            }
        });

        // Listen for capability updates
        this.setupCapabilityListener();
    }

    createMessageContainer() {
        // Create a container for limitation messages
        const container = document.createElement('div');
        container.id = 'limitationMessages';
        container.className = 'limitation-messages-container';
        container.style.cssText = `
            position: fixed;
            top: 4rem;
            right: 1rem;
            max-width: 350px;
            z-index: 9999;
            pointer-events: none;
        `;

        document.body.appendChild(container);
        this.messageContainer = container;
    }

    setupCapabilityListener() {
        // Listen for capability updates from loading states manager
        if (window.loadingStatesManager) {
            // Check for updates periodically
            setInterval(() => {
                this.updateFromCapabilities();
            }, 3000);
        }
    }

    setupInteractionListeners() {
        // Listen for input focus to show relevant limitations
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.addEventListener('focus', () => {
                this.showContextualLimitations();
            });

            messageInput.addEventListener('input', (e) => {
                this.analyzeInputForLimitations(e.target.value);
            });
        }

        // Listen for file upload attempts
        const fileInput = document.getElementById('fileInput');
        if (fileInput) {
            fileInput.addEventListener('change', () => {
                this.showDocumentLimitations();
            });
        }

        // Listen for search attempts
        const searchInput = document.querySelector('input[type="search"]');
        if (searchInput) {
            searchInput.addEventListener('focus', () => {
                this.showSearchLimitations();
            });
        }
    }

    updateFromCapabilities() {
        if (window.loadingStatesManager) {
            this.currentLevel = window.loadingStatesManager.getCurrentLevel();
            this.capabilities = window.loadingStatesManager.capabilities || {};

            console.log('updateFromCapabilities - currentLevel:', this.currentLevel);

            // Update system-wide limitation messages
            this.updateSystemLimitations();
        }
    }

    updateSystemLimitations() {
        const readiness = window.loadingStatesManager?.getReadinessPercent() || 0;
        const level = window.loadingStatesManager?.getCurrentLevel() || 'basic';

        console.log('updateSystemLimitations - readiness:', readiness, 'level:', level);

        if (readiness >= 100 || level === 'full') {
            // System is ready, clear ALL limitation messages
            this.clearAllMessages();
            // Update current level so future checks know we're ready
            this.currentLevel = 'full';
        } else if (readiness < 30) {
            this.showLimitationMessage('system_startup', { eta: '30-60 seconds' });
        } else {
            this.showLimitationMessage('system_loading', { eta: this.calculateETA(readiness) });
        }
    }

    showContextualLimitations() {
        const level = this.currentLevel;
        const readiness = window.loadingStatesManager?.getReadinessPercent() || 0;

        // Don't show limitations if system is fully ready
        if (readiness >= 100 || level === 'full') {
            return;
        }

        // Show chat limitations based on current level
        if (level === 'basic') {
            this.showLimitationMessage('chat_basic', { eta: '1-2 minutes' });
        } else if (level === 'enhanced') {
            this.showLimitationMessage('chat_enhanced', { eta: '30-60 seconds' });
        }
    }

    analyzeInputForLimitations(input) {
        if (!input || input.length < 10) return;

        const lowerInput = input.toLowerCase();
        const level = this.currentLevel;

        // Check for document-related queries
        if (lowerInput.includes('analyze') || lowerInput.includes('document') ||
            lowerInput.includes('pdf') || lowerInput.includes('file')) {

            if (!this.isCapabilityAvailable('document_analysis')) {
                if (level === 'basic') {
                    this.showLimitationMessage('document_basic', { eta: '2-3 minutes' });
                } else if (level === 'enhanced') {
                    this.showLimitationMessage('document_enhanced', { eta: '1-2 minutes' });
                }
            }
        }

        // Check for search-related queries
        if (lowerInput.includes('search') || lowerInput.includes('find') ||
            lowerInput.includes('look for')) {

            if (!this.isCapabilityAvailable('semantic_search')) {
                if (level === 'basic') {
                    this.showLimitationMessage('search_basic', { eta: '1-2 minutes' });
                } else if (level === 'enhanced') {
                    this.showLimitationMessage('search_enhanced', { eta: '30-60 seconds' });
                }
            }
        }

        // Check for complex analysis queries
        if (lowerInput.includes('complex') || lowerInput.includes('detailed') ||
            lowerInput.includes('comprehensive') || lowerInput.includes('analysis')) {

            if (!this.isCapabilityAvailable('complex_reasoning')) {
                if (level === 'basic') {
                    this.showLimitationMessage('analysis_basic', { eta: '3-4 minutes' });
                } else if (level === 'enhanced') {
                    this.showLimitationMessage('analysis_enhanced', { eta: '1-2 minutes' });
                }
            }
        }
    }

    showDocumentLimitations() {
        const level = this.currentLevel;

        if (!this.isCapabilityAvailable('document_analysis')) {
            if (level === 'basic') {
                this.showLimitationMessage('document_basic', { eta: '2-3 minutes' });
            } else if (level === 'enhanced') {
                this.showLimitationMessage('document_enhanced', { eta: '1-2 minutes' });
            }
        }
    }

    showSearchLimitations() {
        const level = this.currentLevel;

        if (!this.isCapabilityAvailable('semantic_search')) {
            if (level === 'basic') {
                this.showLimitationMessage('search_basic', { eta: '1-2 minutes' });
            } else if (level === 'enhanced') {
                this.showLimitationMessage('search_enhanced', { eta: '30-60 seconds' });
            }
        }
    }

    showLimitationMessage(templateKey, variables = {}) {
        // Don't show duplicate messages
        if (this.activeMessages.has(templateKey)) {
            return;
        }

        const template = this.limitationTemplates[templateKey];
        if (!template) {
            console.warn('Unknown limitation template:', templateKey);
            return;
        }

        // Create message element
        const messageEl = document.createElement('div');
        messageEl.className = 'limitation-message';
        messageEl.dataset.templateKey = templateKey;
        messageEl.style.cssText = `
            background: #fef3c7;
            border: 1px solid #f59e0b;
            border-radius: 0.75rem;
            padding: 1rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            pointer-events: auto;
            animation: slideInRight 0.3s ease;
            position: relative;
        `;

        // Replace variables in template
        let message = template.message;
        let etaMessage = template.eta_message;

        Object.keys(variables).forEach(key => {
            const value = variables[key];
            message = message.replace(`{${key}}`, value);
            etaMessage = etaMessage.replace(`{${key}}`, value);
        });

        // Build message content
        let limitationsHTML = '';
        if (template.limitations && template.limitations.length > 0) {
            limitationsHTML = `
                <div class="limitations-section">
                    <strong>Current Limitations:</strong>
                    <ul style="margin: 0.5rem 0; padding-left: 1.25rem; font-size: 0.875rem;">
                        ${template.limitations.map(limitation => `<li>${limitation}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        let workaroundsHTML = '';
        if (template.workarounds && template.workarounds.length > 0) {
            workaroundsHTML = `
                <div class="workarounds-section">
                    <strong>What You Can Do:</strong>
                    <ul style="margin: 0.5rem 0; padding-left: 1.25rem; font-size: 0.875rem; color: #059669;">
                        ${template.workarounds.map(workaround => `<li>${workaround}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        messageEl.innerHTML = `
            <div class="limitation-header" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span style="font-size: 1.25rem;">⚠️</span>
                    <strong style="color: #92400e; font-size: 0.9375rem;">${template.title}</strong>
                </div>
                <button class="close-btn" onclick="this.closest('.limitation-message').remove(); window.limitationMessagesManager?.activeMessages.delete('${templateKey}')" 
                        style="background: none; border: none; cursor: pointer; color: #92400e; font-size: 1.25rem; line-height: 1; padding: 0;">×</button>
            </div>
            
            <div class="limitation-content" style="font-size: 0.875rem; color: #92400e; line-height: 1.4;">
                <p style="margin: 0 0 0.75rem 0;">${message}</p>
                
                ${limitationsHTML}
                ${workaroundsHTML}
                
                <div class="eta-section" style="background: rgba(245, 158, 11, 0.1); border-radius: 0.375rem; padding: 0.5rem; margin-top: 0.75rem; font-size: 0.8125rem;">
                    <strong>⏱️ ${etaMessage}</strong>
                </div>
            </div>
        `;

        // Add CSS animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideInRight {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOutRight {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        if (!document.head.querySelector('style[data-limitation-animations]')) {
            style.setAttribute('data-limitation-animations', 'true');
            document.head.appendChild(style);
        }

        // Add to container
        this.messageContainer.appendChild(messageEl);
        this.activeMessages.add(templateKey);

        // Auto-remove after 15 seconds for non-critical messages
        if (!templateKey.includes('system_')) {
            setTimeout(() => {
                this.clearLimitationMessage(templateKey);
            }, 15000);
        }
    }

    clearLimitationMessage(templateKey) {
        const messageEl = this.messageContainer.querySelector(`[data-template-key="${templateKey}"]`);
        if (messageEl) {
            messageEl.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => {
                if (messageEl.parentNode) {
                    messageEl.remove();
                }
            }, 300);
        }
        this.activeMessages.delete(templateKey);
    }

    isCapabilityAvailable(capabilityName) {
        if (window.loadingStatesManager) {
            return window.loadingStatesManager.isCapabilityAvailable(capabilityName);
        }
        return false;
    }

    calculateETA(readinessPercent) {
        // Simple ETA calculation based on readiness
        if (readinessPercent < 50) {
            return '2-3 minutes';
        } else if (readinessPercent < 80) {
            return '1-2 minutes';
        } else {
            return '30-60 seconds';
        }
    }

    // Public API methods

    /**
     * Show a custom limitation message
     */
    showCustomLimitation(title, message, limitations = [], workarounds = [], eta = null) {
        const customKey = `custom_${Date.now()}`;

        this.limitationTemplates[customKey] = {
            title,
            message,
            limitations,
            workarounds,
            eta_message: eta ? `Ready in ${eta}` : 'Ready soon'
        };

        this.showLimitationMessage(customKey, { eta: eta || 'soon' });
    }

    /**
     * Clear all limitation messages
     */
    clearAllMessages() {
        this.activeMessages.forEach(templateKey => {
            this.clearLimitationMessage(templateKey);
        });
    }

    /**
     * Show limitation for specific feature
     */
    showFeatureLimitation(feature, level = null) {
        const currentLevel = level || this.currentLevel;
        const templateKey = `${feature}_${currentLevel}`;

        if (this.limitationTemplates[templateKey]) {
            this.showLimitationMessage(templateKey, { eta: this.calculateETA(50) });
        }
    }

    /**
     * Get active limitation messages
     */
    getActiveMessages() {
        return Array.from(this.activeMessages);
    }

    /**
     * Destroy the manager and clean up
     */
    destroy() {
        // Clear all messages
        this.clearAllMessages();

        // Remove container
        if (this.messageContainer && this.messageContainer.parentNode) {
            this.messageContainer.remove();
        }

        // Remove event listeners
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.removeEventListener('focus', this.showContextualLimitations);
            messageInput.removeEventListener('input', this.analyzeInputForLimitations);
        }

        console.log('Limitation Messages Manager destroyed');
    }
}

// Global instance
let limitationMessagesManager = null;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        limitationMessagesManager = new LimitationMessagesManager();
        // Export instance after creation
        window.limitationMessagesManager = limitationMessagesManager;
    });
} else {
    limitationMessagesManager = new LimitationMessagesManager();
    // Export instance after creation
    window.limitationMessagesManager = limitationMessagesManager;
}

// Export class for use in other scripts
window.LimitationMessagesManager = LimitationMessagesManager;