/**
 * Citation Popup Component
 * 
 * Displays a popup with citation details including document title,
 * relevance score, and chunk excerpt when a source citation is clicked.
 * 
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 6.1, 6.2, 6.4, 6.5, 7.4
 */

class CitationPopup {
    constructor() {
        this.popupElement = null;
        this.triggerElement = null;
        this.isOpen = false;
        this.focusableElements = [];
        this.firstFocusableElement = null;
        this.lastFocusableElement = null;

        // Bind event handlers
        this.handleKeydown = this.handleKeydown.bind(this);
        this.handleClickOutside = this.handleClickOutside.bind(this);
    }

    /**
     * Show popup with citation data
     * @param {Object} citationData - Citation information to display
     * @param {HTMLElement} triggerElement - Element that triggered the popup
     */
    show(citationData, triggerElement) {
        // Close any existing popup first
        if (this.isOpen) {
            this.hide();
        }

        this.triggerElement = triggerElement;
        this.popupElement = this.createPopupElement(citationData);

        // Add to DOM
        document.body.appendChild(this.popupElement);

        // Position the popup
        this.position(triggerElement);

        // Set up event listeners
        document.addEventListener('keydown', this.handleKeydown);
        document.addEventListener('click', this.handleClickOutside, true);

        // Set up focus management
        this.setupFocusManagement();

        // Mark as open
        this.isOpen = true;

        // Animate in
        requestAnimationFrame(() => {
            this.popupElement.classList.add('citation-popup--visible');
            // Scroll excerpt to show relevant text near the trigger context
            this._scrollToRelevantText(triggerElement, citationData);
        });
    }

    /**
     * Hide and cleanup popup
     */
    hide() {
        if (!this.isOpen || !this.popupElement) {
            return;
        }

        // Remove event listeners
        document.removeEventListener('keydown', this.handleKeydown);
        document.removeEventListener('click', this.handleClickOutside, true);

        // Animate out
        this.popupElement.classList.remove('citation-popup--visible');

        // Remove from DOM after animation
        const popup = this.popupElement;
        setTimeout(() => {
            if (popup && popup.parentNode) {
                popup.parentNode.removeChild(popup);
            }
        }, 200);

        // Restore focus to trigger element
        this.restoreFocus();

        // Reset state
        this.popupElement = null;
        this.isOpen = false;
        this.focusableElements = [];
        this.firstFocusableElement = null;
        this.lastFocusableElement = null;
    }


    /**
     * Create popup DOM structure
     * @param {Object} citationData - Citation information
     * @returns {HTMLElement} Popup element
     */
    createPopupElement(citationData) {
        const popup = document.createElement('div');
        popup.className = 'citation-popup';
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-modal', 'true');
        popup.setAttribute('aria-labelledby', 'citation-popup-title');

        // Generate unique ID for title
        const titleId = 'citation-popup-title-' + Date.now();

        // Build popup content
        const content = document.createElement('div');
        content.className = 'citation-popup__content';

        // Header with title and close button
        const header = document.createElement('div');
        header.className = 'citation-popup__header';

        const title = document.createElement('h3');
        title.id = titleId;
        title.className = 'citation-popup__title';
        title.textContent = citationData.document_title || citationData.documentTitle || 'Unknown Document';

        const closeBtn = document.createElement('button');
        closeBtn.className = 'citation-popup__close';
        closeBtn.setAttribute('aria-label', 'Close citation popup');
        closeBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        `;
        closeBtn.addEventListener('click', () => this.hide());

        header.appendChild(title);

        // Download button for non-web sources; export button for conversation sources
        const isWebSource = citationData.url && citationData.source_type === 'web_search';
        const isConvSource = (citationData.knowledge_source_type || citationData.knowledgeSourceType) === 'conversation';
        const docId = citationData.document_id || citationData.documentId;
        if (!isWebSource && docId) {
            const docTitle = citationData.document_title || citationData.documentTitle || 'Document';
            if (isConvSource) {
                // Download conversation as PDF button
                const exportBtn = document.createElement('button');
                exportBtn.className = 'citation-popup__download';
                exportBtn.innerHTML = '⬇';
                exportBtn.title = `Download ${docTitle}`;
                exportBtn.setAttribute('aria-label', `Download ${docTitle}`);
                exportBtn.style.cssText = 'background:none;border:1px solid #cbd5e1;border-radius:4px;cursor:pointer;padding:2px 8px;margin-left:auto;margin-right:8px;font-size:0.85rem;color:#64748b;transition:all 0.2s ease;line-height:1;flex-shrink:0;';
                exportBtn.addEventListener('mouseenter', () => {
                    exportBtn.style.backgroundColor = '#3b82f6';
                    exportBtn.style.color = '#fff';
                    exportBtn.style.borderColor = '#3b82f6';
                });
                exportBtn.addEventListener('mouseleave', () => {
                    exportBtn.style.backgroundColor = '';
                    exportBtn.style.color = '#64748b';
                    exportBtn.style.borderColor = '#cbd5e1';
                });
                exportBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open(`/api/documents/${docId}/export-conversation`, '_blank');
                });
                header.appendChild(exportBtn);
            } else {
                // Regular document download button
                const downloadBtn = document.createElement('button');
                downloadBtn.className = 'citation-popup__download';
                downloadBtn.innerHTML = '⬇';
                downloadBtn.title = `Download ${docTitle}`;
                downloadBtn.setAttribute('aria-label', `Download ${docTitle}`);
                downloadBtn.style.cssText = 'background:none;border:1px solid #cbd5e1;border-radius:4px;cursor:pointer;padding:2px 8px;margin-left:auto;margin-right:8px;font-size:0.85rem;color:#64748b;transition:all 0.2s ease;line-height:1;flex-shrink:0;';
                downloadBtn.addEventListener('mouseenter', () => {
                    downloadBtn.style.backgroundColor = '#3b82f6';
                    downloadBtn.style.color = '#fff';
                    downloadBtn.style.borderColor = '#3b82f6';
                });
                downloadBtn.addEventListener('mouseleave', () => {
                    downloadBtn.style.backgroundColor = '';
                    downloadBtn.style.color = '#64748b';
                    downloadBtn.style.borderColor = '#cbd5e1';
                });
                downloadBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    window.open(`/api/documents/${docId}/download?redirect=true`, '_blank');
                });
                header.appendChild(downloadBtn);
            }
        }

        header.appendChild(closeBtn);
        content.appendChild(header);

        // Update aria-labelledby to use the actual title ID
        popup.setAttribute('aria-labelledby', titleId);

        // URL link for web search sources
        const url = citationData.url;
        if (url) {
            const urlContainer = document.createElement('div');
            urlContainer.className = 'citation-popup__url';
            urlContainer.style.padding = '0 1rem';
            urlContainer.style.marginBottom = '0.5rem';
            const urlLink = document.createElement('a');
            urlLink.href = url;
            urlLink.target = '_blank';
            urlLink.rel = 'noopener noreferrer';
            urlLink.textContent = url;
            urlLink.style.color = '#3b82f6';
            urlLink.style.fontSize = '0.8rem';
            urlLink.style.wordBreak = 'break-all';
            urlContainer.appendChild(urlLink);
            content.appendChild(urlContainer);
        }

        // Metadata section (relevance score, page number, section)
        const metadata = document.createElement('div');
        metadata.className = 'citation-popup__metadata';

        // Relevance score
        const relevanceScore = citationData.relevance_score || citationData.relevanceScore;
        if (relevanceScore !== undefined && relevanceScore !== null) {
            const scoreEl = document.createElement('span');
            scoreEl.className = 'citation-popup__score';
            const percentage = Math.round(relevanceScore * 100);
            scoreEl.textContent = `${percentage}% relevant`;
            scoreEl.setAttribute('aria-label', `Relevance score: ${percentage} percent`);
            metadata.appendChild(scoreEl);
        }

        // Section title
        const sectionTitle = citationData.section_title || citationData.sectionTitle;
        if (sectionTitle) {
            const sectionEl = document.createElement('span');
            sectionEl.className = 'citation-popup__section';
            sectionEl.textContent = sectionTitle;
            metadata.appendChild(sectionEl);
        }

        if (metadata.children.length > 0) {
            content.appendChild(metadata);
        }

        // Excerpt section
        const excerptContainer = document.createElement('div');
        excerptContainer.className = 'citation-popup__excerpt-container';

        const excerpt = citationData.excerpt;
        const excerptError = citationData.excerpt_error || citationData.excerptError;

        if (excerptError || !excerpt) {
            // Handle error or missing excerpt (Requirements: 1.4, 5.3)
            const errorEl = document.createElement('div');
            errorEl.className = 'citation-popup__excerpt-error-container';

            // Create error icon
            const errorIcon = document.createElement('span');
            errorIcon.className = 'citation-popup__error-icon';
            errorIcon.setAttribute('aria-hidden', 'true');
            errorIcon.textContent = '⚠️';

            // Create error message
            const errorMsg = document.createElement('p');
            errorMsg.className = 'citation-popup__excerpt citation-popup__excerpt--error';

            // Provide specific error messages based on error type
            if (excerptError === 'not_found') {
                errorMsg.textContent = 'Source content not found in database';
            } else if (excerptError === 'retrieval_failed') {
                errorMsg.textContent = 'Unable to retrieve source content';
            } else if (excerptError) {
                errorMsg.textContent = `Excerpt unavailable: ${excerptError}`;
            } else {
                errorMsg.textContent = 'Excerpt not available';
            }

            errorEl.appendChild(errorIcon);
            errorEl.appendChild(errorMsg);
            excerptContainer.appendChild(errorEl);
        } else {
            const excerptEl = document.createElement('p');
            excerptEl.className = 'citation-popup__excerpt';

            // Show the full chunk content — strip [Page N] markers that are
            // internal extraction artifacts, not meaningful to the user
            excerptEl.textContent = excerpt.replace(/\[Page\s+\d+\]/gi, '').replace(/\s{2,}/g, ' ').trim();
            excerptContainer.appendChild(excerptEl);
        }

        content.appendChild(excerptContainer);
        popup.appendChild(content);

        return popup;
    }


    /**
     * Position popup centered vertically on trigger element, scrollable for long content
     * @param {HTMLElement} triggerElement - Element that triggered the popup
     */
    position(triggerElement) {
        if (!this.popupElement || !triggerElement) {
            return;
        }

        const popup = this.popupElement;
        const triggerRect = triggerElement.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const padding = 16;

        // Fixed popup size — always the same compact bubble
        const popupWidth = 420;
        const popupHeight = 400;

        // Center vertically on the trigger element
        const triggerCenterY = triggerRect.top + triggerRect.height / 2;
        let top = triggerCenterY - popupHeight / 2;

        // Clamp to viewport
        if (top < padding) {
            top = padding;
        } else if (top + popupHeight > viewportHeight - padding) {
            top = viewportHeight - padding - popupHeight;
        }

        // Center horizontally on trigger, clamped to viewport
        let left = triggerRect.left + (triggerRect.width / 2) - (popupWidth / 2);
        if (left < padding) {
            left = padding;
        } else if (left + popupWidth > viewportWidth - padding) {
            left = viewportWidth - popupWidth - padding;
        }

        // Apply fixed size and position.
        // overflow is handled by CSS: outer container is hidden,
        // inner .citation-popup__content scrolls.
        popup.style.position = 'fixed';
        popup.style.top = `${top}px`;
        popup.style.left = `${left}px`;
        popup.style.width = `${popupWidth}px`;
        popup.style.maxWidth = `${popupWidth}px`;
        popup.style.height = `${popupHeight}px`;
        popup.style.maxHeight = `${popupHeight}px`;
    }

    /**
     * Scroll the popup so the relevant excerpt text is as close to
     * vertically centered as possible. Uses a DOM marker for pixel-precise
     * positioning rather than character-ratio estimation.
     */
    _scrollToRelevantText(triggerElement, citationData) {
        if (!this.popupElement || !triggerElement || !citationData || !citationData.excerpt) {
            return;
        }

        // Only highlight when triggered from an inline [Source N] link.
        // The sources list at the bottom has no surrounding AI response text
        // to match against, so highlighting would be arbitrary/wrong.
        if (!triggerElement.classList.contains('citation-link')) {
            return;
        }

        // Get surrounding text from the AI response near the citation link
        const parentEl = triggerElement.parentElement;
        if (!parentEl) return;
        const parentText = parentEl.textContent || '';
        const triggerText = triggerElement.textContent || '';
        const triggerIdx = parentText.indexOf(triggerText);
        if (triggerIdx <= 0) return;

        const contextBefore = parentText.substring(Math.max(0, triggerIdx - 80), triggerIdx).trim();
        const words = contextBefore.split(/\s+/).filter(w => w.length > 3);
        if (words.length === 0) return;

        // Find the best matching phrase in the excerpt
        const excerptLower = citationData.excerpt.toLowerCase();
        let matchIndex = -1;
        let matchLen = 0;

        for (let len = Math.min(words.length, 5); len >= 1; len--) {
            const phrase = words.slice(-len).join(' ').toLowerCase().replace(/[^\w\s]/g, '');
            if (phrase.length < 4) continue;
            const idx = excerptLower.indexOf(phrase);
            if (idx >= 0) {
                matchIndex = idx;
                matchLen = phrase.length;
                break;
            }
        }

        if (matchIndex < 0) return;

        // Expand match to the full sentence containing it
        const excerptEl = this.popupElement.querySelector('.citation-popup__excerpt');
        if (!excerptEl) return;

        const fullText = citationData.excerpt;

        // Find sentence start: scan backwards for sentence-ending punctuation
        let sentenceStart = matchIndex;
        for (let i = matchIndex - 1; i >= 0; i--) {
            const ch = fullText[i];
            if (ch === '.' || ch === '!' || ch === '?') {
                sentenceStart = i + 1;
                break;
            }
            if (i === 0) sentenceStart = 0;
        }
        // Skip leading whitespace
        while (sentenceStart < matchIndex && /\s/.test(fullText[sentenceStart])) {
            sentenceStart++;
        }

        // Find sentence end: scan forwards for sentence-ending punctuation
        let sentenceEnd = matchIndex + matchLen;
        for (let i = sentenceEnd; i < fullText.length; i++) {
            const ch = fullText[i];
            if (ch === '.' || ch === '!' || ch === '?') {
                sentenceEnd = i + 1;
                break;
            }
            if (i === fullText.length - 1) sentenceEnd = fullText.length;
        }

        const before = fullText.substring(0, sentenceStart);
        const matched = fullText.substring(sentenceStart, sentenceEnd);
        const after = fullText.substring(sentenceEnd);

        excerptEl.textContent = '';
        excerptEl.appendChild(document.createTextNode(before));
        const marker = document.createElement('span');
        marker.className = 'citation-popup__highlight';
        marker.textContent = matched;
        excerptEl.appendChild(marker);
        excerptEl.appendChild(document.createTextNode(after));

        // Scroll the inner __content container (not the outer popup)
        const scrollContainer = this.popupElement.querySelector('.citation-popup__content');
        if (!scrollContainer) return;

        const containerRect = scrollContainer.getBoundingClientRect();
        const markerRect = marker.getBoundingClientRect();
        const markerTopInScroll = markerRect.top - containerRect.top + scrollContainer.scrollTop;
        const visibleHeight = scrollContainer.clientHeight;

        // Ideal: marker vertically centered in the scroll container
        const idealScroll = markerTopInScroll - visibleHeight / 2;
        const maxScroll = scrollContainer.scrollHeight - visibleHeight;
        scrollContainer.scrollTop = Math.max(0, Math.min(idealScroll, maxScroll));
    }

    /**
     * Handle keyboard events (Escape to close, Tab for focus trapping)
     * @param {KeyboardEvent} event - Keyboard event
     */
    handleKeydown(event) {
        if (!this.isOpen) {
            return;
        }

        // Escape key closes popup
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            this.hide();
            return;
        }

        // Tab key for focus trapping
        if (event.key === 'Tab') {
            this.trapFocus(event);
        }
    }

    /**
     * Handle click outside to close popup
     * @param {MouseEvent} event - Click event
     */
    handleClickOutside(event) {
        if (!this.isOpen || !this.popupElement) {
            return;
        }

        // Check if click is outside popup
        if (!this.popupElement.contains(event.target)) {
            // Also check if click is on the trigger (don't close if clicking trigger again)
            if (this.triggerElement && this.triggerElement.contains(event.target)) {
                return;
            }
            this.hide();
        }
    }

    /**
     * Set up focus management for the popup
     */
    setupFocusManagement() {
        if (!this.popupElement) {
            return;
        }

        // Find all focusable elements within popup
        const focusableSelectors = [
            'button:not([disabled])',
            'a[href]',
            'input:not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(', ');

        this.focusableElements = Array.from(
            this.popupElement.querySelectorAll(focusableSelectors)
        );

        if (this.focusableElements.length > 0) {
            this.firstFocusableElement = this.focusableElements[0];
            this.lastFocusableElement = this.focusableElements[this.focusableElements.length - 1];

            // Focus the close button (first focusable element)
            this.firstFocusableElement.focus();
        }
    }

    /**
     * Trap focus within popup
     * @param {KeyboardEvent} event - Tab key event
     */
    trapFocus(event) {
        if (this.focusableElements.length === 0) {
            event.preventDefault();
            return;
        }

        const isShiftTab = event.shiftKey;

        if (isShiftTab) {
            // Shift + Tab: if on first element, go to last
            if (document.activeElement === this.firstFocusableElement) {
                event.preventDefault();
                this.lastFocusableElement.focus();
            }
        } else {
            // Tab: if on last element, go to first
            if (document.activeElement === this.lastFocusableElement) {
                event.preventDefault();
                this.firstFocusableElement.focus();
            }
        }
    }

    /**
     * Restore focus to trigger element
     */
    restoreFocus() {
        if (this.triggerElement && typeof this.triggerElement.focus === 'function') {
            // Use setTimeout to ensure focus happens after popup is removed
            setTimeout(() => {
                this.triggerElement.focus();
            }, 0);
        }
        this.triggerElement = null;
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.CitationPopup = CitationPopup;
}
