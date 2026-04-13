/**
 * Model Failure Breakdown Popup
 *
 * Displays a popup with per-model failure rate breakdown when the user
 * clicks on the composite rate value in the throughput report table.
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

class ModelFailurePopup {
    constructor() {
        this.popupElement = null;
        this.isOpen = false;

        this.handleKeydown = this.handleKeydown.bind(this);
        this.handleClickOutside = this.handleClickOutside.bind(this);
    }

    /**
     * Attach click handlers to Model column cells in the most recently
     * rendered throughput report table.
     *
     * @param {HTMLElement} container - The message container holding the table
     * @param {Array<Object|null>} qualityData - Quality gate data per row
     */
    attachToTable(container, qualityData) {
        if (!container || !qualityData || qualityData.length === 0) return;

        const table = container.querySelector('table.status-table');
        if (!table) return;

        // Find the "Model" column index from the header row
        const headers = table.querySelectorAll('thead th');
        let modelColIdx = -1;
        headers.forEach((th, idx) => {
            if (th.textContent.trim() === 'Model') {
                modelColIdx = idx;
            }
        });
        if (modelColIdx === -1) return;

        // Attach handlers to each body row's Model cell
        const bodyRows = table.querySelectorAll('tbody tr');
        bodyRows.forEach((tr, rowIdx) => {
            const cells = tr.querySelectorAll('td');
            const cell = cells[modelColIdx];
            if (!cell) return;

            const qg = qualityData[rowIdx];
            if (!qg) return; // No data for this row (pre-feature document)

            cell.classList.add('model-cell--clickable');
            cell.setAttribute('role', 'button');
            cell.setAttribute('tabindex', '0');
            cell.setAttribute('aria-label', 'Show model failure breakdown');

            cell.addEventListener('click', (e) => {
                e.stopPropagation();
                this.show(qg, cell);
            });
            cell.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    e.stopPropagation();
                    this.show(qg, cell);
                }
            });
        });
    }

    /**
     * Show the breakdown popup anchored to a trigger element.
     *
     * @param {Object} qg - Quality gate data dict
     * @param {HTMLElement} triggerElement - The cell that was clicked
     */
    show(qg, triggerElement) {
        if (this.isOpen) this.hide();

        this.popupElement = this._buildPopup(qg);
        document.body.appendChild(this.popupElement);
        this._position(triggerElement);

        document.addEventListener('keydown', this.handleKeydown);
        // Delay click-outside so the current click doesn't immediately close
        requestAnimationFrame(() => {
            document.addEventListener('click', this.handleClickOutside, true);
        });

        this.isOpen = true;

        requestAnimationFrame(() => {
            this.popupElement.classList.add('model-failure-popup--visible');
        });
    }

    /** Hide and clean up the popup. */
    hide() {
        if (!this.isOpen || !this.popupElement) return;

        document.removeEventListener('keydown', this.handleKeydown);
        document.removeEventListener('click', this.handleClickOutside, true);

        this.popupElement.classList.remove('model-failure-popup--visible');
        const el = this.popupElement;
        setTimeout(() => {
            if (el && el.parentNode) el.parentNode.removeChild(el);
        }, 150);

        this.popupElement = null;
        this.isOpen = false;
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    /** @private */
    handleKeydown(e) {
        if (e.key === 'Escape') this.hide();
    }

    /** @private */
    handleClickOutside(e) {
        if (this.popupElement && !this.popupElement.contains(e.target)) {
            this.hide();
        }
    }

    /**
     * Build the popup DOM.
     * @private
     * @param {Object} qg - Quality gate data
     * @returns {HTMLElement}
     */
    _buildPopup(qg) {
        const popup = document.createElement('div');
        popup.className = 'model-failure-popup';
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-label', 'Model failure breakdown');

        // Header
        const header = document.createElement('div');
        header.className = 'model-failure-popup__header';

        const title = document.createElement('span');
        title.className = 'model-failure-popup__title';
        title.textContent = 'Model Failure Breakdown';
        header.appendChild(title);

        const closeBtn = document.createElement('button');
        closeBtn.className = 'model-failure-popup__close';
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.textContent = '×';
        closeBtn.addEventListener('click', () => this.hide());
        header.appendChild(closeBtn);

        popup.appendChild(header);

        // Body
        const body = document.createElement('div');
        body.className = 'model-failure-popup__body';

        const nerPct = this._fmtPct(qg.ner_rate);
        const llmPct = this._fmtPct(qg.llm_rate);
        const bridgePct = this._fmtPct(qg.bridge_rate);

        body.appendChild(this._makeRow(
            'NER (spaCy)',
            nerPct,
            `(${qg.ner_failures}/${qg.ner_total} chunks)`,
            qg.worst_model === 'ner'
        ));
        body.appendChild(this._makeRow(
            'LLM (Ollama)',
            llmPct,
            `(${qg.llm_failures}/${qg.llm_total} chunks)`,
            qg.worst_model === 'llm'
        ));
        body.appendChild(this._makeRow(
            'Bridges (Ollama→Gemini)',
            bridgePct,
            `(${qg.bridge_failures}/${qg.bridge_total} bridges)`,
            qg.worst_model === 'bridge'
        ));

        const hr = document.createElement('hr');
        hr.className = 'model-failure-popup__divider';
        body.appendChild(hr);

        const formula = document.createElement('div');
        formula.className = 'model-failure-popup__formula';
        const compositePct = this._fmtPct(qg.composite_rate);
        const kgPct = Math.round((qg.kg_weight ?? 0.7) * 100);
        const brPct = Math.round((qg.bridge_weight ?? 0.3) * 100);
        formula.textContent =
            `KG (NER/LLM) × ${kgPct}% + Bridges × ${brPct}% = ${compositePct}`;
        body.appendChild(formula);

        popup.appendChild(body);
        return popup;
    }

    /**
     * Create a single breakdown row.
     * @private
     */
    _makeRow(label, pctStr, countsStr, isFail) {
        const row = document.createElement('div');
        row.className = 'model-failure-popup__row';
        if (isFail) row.classList.add('model-failure-popup__row--fail');

        const lbl = document.createElement('span');
        lbl.className = 'model-failure-popup__label';
        lbl.textContent = label;
        row.appendChild(lbl);

        const valWrap = document.createElement('span');
        const val = document.createElement('span');
        val.className = 'model-failure-popup__value';
        val.textContent = pctStr;
        valWrap.appendChild(val);

        const counts = document.createElement('span');
        counts.className = 'model-failure-popup__counts';
        counts.textContent = countsStr;
        valWrap.appendChild(counts);

        row.appendChild(valWrap);
        return row;
    }

    /**
     * Format a 0–1 rate as a percentage string.
     * @private
     */
    _fmtPct(rate) {
        if (rate == null) return '—';
        return `${(rate * 100).toFixed(0)}%`;
    }

    /**
     * Position the popup below (or above) the trigger element.
     * @private
     */
    _position(trigger) {
        const rect = trigger.getBoundingClientRect();
        const popup = this.popupElement;
        const margin = 6;

        // Default: below the trigger, left-aligned
        let top = rect.bottom + margin;
        let left = rect.left;

        // Measure popup dimensions
        popup.style.visibility = 'hidden';
        popup.style.display = 'block';
        const popupRect = popup.getBoundingClientRect();
        popup.style.visibility = '';

        // Flip above if not enough room below
        if (top + popupRect.height > window.innerHeight - margin) {
            top = rect.top - popupRect.height - margin;
        }

        // Clamp horizontally
        if (left + popupRect.width > window.innerWidth - margin) {
            left = window.innerWidth - popupRect.width - margin;
        }
        if (left < margin) left = margin;

        // Clamp vertically
        if (top < margin) top = margin;

        popup.style.top = `${top}px`;
        popup.style.left = `${left}px`;
    }
}

// Singleton instance
if (typeof window !== 'undefined') {
    window.ModelFailurePopup = new ModelFailurePopup();
}
