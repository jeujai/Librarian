/**
 * Citation Renderer Module
 * 
 * Transforms citation references in response text (e.g., "[Source 1]") 
 * into clickable elements that display citation popups.
 * 
 * Requirements: 1.1, 1.2, 1.3, 6.3
 */

const CitationRenderer = {
    /**
     * Citation pattern regex - matches "[Source N]" or "[Source N, Source M, ...]"
     * @type {RegExp}
     */
    CITATION_PATTERN: /\[Source\s+(\d+)\]/gi,

    /**
     * Multi-citation pattern - matches "[Source N, Source M, ...]"
     * @type {RegExp}
     */
    MULTI_CITATION_PATTERN: /\[Source\s+\d+(?:,\s*Source\s+\d+)+\]/gi,

    /**
     * Reference to the CitationPopup instance (set by ChatApp)
     * @type {CitationPopup|null}
     */
    citationPopup: null,

    /**
     * Find all citation matches in text
     * @param {string} text - Text to search for citation patterns
     * @returns {Array<{match: string, sourceNumber: number, index: number}>} Array of matches
     */
    findCitationMatches(text) {
        if (!text || typeof text !== 'string') {
            return [];
        }

        const matches = [];
        // Reset regex lastIndex for global matching
        this.CITATION_PATTERN.lastIndex = 0;

        let match;
        while ((match = this.CITATION_PATTERN.exec(text)) !== null) {
            const sourceNumber = parseInt(match[1], 10);
            // Only include valid positive source numbers
            if (sourceNumber > 0) {
                matches.push({
                    match: match[0],
                    sourceNumber: sourceNumber,
                    index: match.index
                });
            }
        }

        return matches;
    },

    /**
     * Parse source number from citation text
     * @param {string} citationText - Citation text like "[Source 1]"
     * @returns {number|null} Source number or null if invalid
     */
    parseSourceNumber(citationText) {
        if (!citationText || typeof citationText !== 'string') {
            return null;
        }

        // Reset regex for single match
        const pattern = /\[Source\s+(\d+)\]/i;
        const match = citationText.match(pattern);

        if (match && match[1]) {
            const num = parseInt(match[1], 10);
            return num > 0 ? num : null;
        }

        return null;
    },

    /**
     * Create a clickable citation element
     * @param {number} sourceNumber - The source number (1-indexed)
     * @param {Object|null} citationData - Citation data for popup display
     * @returns {HTMLElement} Clickable span element
     */
    createCitationElement(sourceNumber, citationData) {
        const span = document.createElement('span');
        span.className = 'citation-link';
        span.textContent = `[Source ${sourceNumber}]`;
        span.setAttribute('role', 'button');
        span.setAttribute('tabindex', '0');

        // Build aria-label with available information
        let ariaLabel = `Source ${sourceNumber}`;
        if (citationData) {
            const title = citationData.document_title || citationData.documentTitle;
            if (title) {
                ariaLabel += `: ${title}`;
            }
            const score = citationData.relevance_score || citationData.relevanceScore;
            if (score !== undefined && score !== null) {
                ariaLabel += `, ${Math.round(score * 100)}% relevant`;
            }
        }
        span.setAttribute('aria-label', ariaLabel);

        // Store citation data on element for popup access
        if (citationData) {
            span.dataset.citationData = JSON.stringify(citationData);
            span.dataset.sourceNumber = sourceNumber;
        }

        // Add click handler
        span.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            this._handleCitationClick(span, citationData);
        });

        // Add keyboard handler for Enter and Space
        span.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.stopPropagation();
                this._handleCitationClick(span, citationData);
            }
        });

        return span;
    },

    /**
     * Handle citation click - show popup
     * @param {HTMLElement} element - The clicked citation element
     * @param {Object|null} citationData - Citation data for popup
     * @private
     */
    _handleCitationClick(element, citationData) {
        if (!citationData) {
            // Log warning for debugging (Requirements: 1.4, 9.2)
            const sourceNumber = element.dataset.sourceNumber || 'unknown';
            console.warn(
                `[CitationRenderer] Citation clicked but no data available for Source ${sourceNumber}. ` +
                `This may indicate a mismatch between inline citations and the citations array.`
            );
            return;
        }

        // Use the shared CitationPopup instance
        if (this.citationPopup) {
            this.citationPopup.show(citationData, element);
        } else if (window.citationPopup) {
            window.citationPopup.show(citationData, element);
        } else {
            console.warn('[CitationRenderer] CitationPopup not initialized - cannot display popup');
        }
    },

    /**
     * Render citations in text, replacing patterns with clickable elements
     * @param {string} text - Text containing citation patterns
     * @param {Array<Object>} citations - Array of citation data objects (1-indexed by position)
     * @returns {DocumentFragment} Document fragment with text and clickable citations
     */
    renderCitations(text, citations) {
        const fragment = document.createDocumentFragment();

        if (!text || typeof text !== 'string') {
            return fragment;
        }

        // Normalize citations array - ensure it's an array
        const citationsArray = Array.isArray(citations) ? citations : [];

        // Pre-process: expand multi-citation patterns like "[Source 1, Source 3]"
        // into separate "[Source 1] [Source 3]" so the single-citation regex can match
        this.MULTI_CITATION_PATTERN.lastIndex = 0;
        let processedText = text.replace(this.MULTI_CITATION_PATTERN, (match) => {
            const numbers = [];
            const numPattern = /\d+/g;
            let numMatch;
            while ((numMatch = numPattern.exec(match)) !== null) {
                numbers.push(numMatch[0]);
            }
            return numbers.map(n => `[Source ${n}]`).join(' ');
        });

        // Find all citation matches
        const matches = this.findCitationMatches(processedText);

        if (matches.length === 0) {
            // No citations found, return plain text
            fragment.appendChild(document.createTextNode(processedText));
            return fragment;
        }

        // Sort matches by index to process in order
        matches.sort((a, b) => a.index - b.index);

        let lastIndex = 0;

        matches.forEach(matchInfo => {
            // Add text before this citation
            if (matchInfo.index > lastIndex) {
                const textBefore = processedText.substring(lastIndex, matchInfo.index);
                fragment.appendChild(document.createTextNode(textBefore));
            }

            // Get citation data (source numbers are 1-indexed, array is 0-indexed)
            const citationIndex = matchInfo.sourceNumber - 1;
            const citationData = citationsArray[citationIndex] || null;

            if (citationData) {
                // Create clickable citation element
                const citationElement = this.createCitationElement(
                    matchInfo.sourceNumber,
                    citationData
                );
                fragment.appendChild(citationElement);
            } else {
                // No citation data available - render as plain text
                // This handles invalid source numbers gracefully (Requirements: 1.4, 9.2)
                console.warn(
                    `[CitationRenderer] Invalid citation reference: "${matchInfo.match}" - ` +
                    `Source ${matchInfo.sourceNumber} not found in citations array ` +
                    `(available: ${citationsArray.length} sources). Rendering as plain text.`
                );
                fragment.appendChild(document.createTextNode(matchInfo.match));
            }

            lastIndex = matchInfo.index + matchInfo.match.length;
        });

        // Add remaining text after last citation
        if (lastIndex < processedText.length) {
            fragment.appendChild(document.createTextNode(processedText.substring(lastIndex)));
        }

        return fragment;
    },

    /**
     * Set the CitationPopup instance to use for displaying popups
     * @param {CitationPopup} popup - CitationPopup instance
     */
    setCitationPopup(popup) {
        this.citationPopup = popup;
    }
};

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.CitationRenderer = CitationRenderer;
}
