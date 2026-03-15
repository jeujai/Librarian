/**
 * KGExplorerPanel — Knowledge Graph Explorer
 *
 * A D3.js force-directed graph viewer for exploring knowledge graph
 * concepts and relationships. Supports:
 * - Landing view (top 10 concepts by degree)
 * - Ego-graph neighborhood navigation
 * - Semantic search
 * - Cross-source color coding
 * - Navigation history with back button
 *
 * Requirements: 11.1–11.6, 12.1–12.5, 13.1–13.5, 14.1–14.4, 15.1–15.5
 */
class KGExplorerPanel {
    constructor() {
        this.panel = null;
        this.simulation = null;
        this.focusNode = null;
        this.sourceId = null;
        this.navigationHistory = [];
        this.maxNodes = 50;
        this._currentNodes = [];
        this._currentEdges = [];
        this._d3 = null;
        this._svg = null;
        this._searchTimeout = null;
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    /**
     * Open the explorer for a given knowledge source.
     * Fetches landing view (top 10 concepts by degree).
     * @param {string} sourceId - Document or conversation ID
     */
    async open(sourceId) {
        this.sourceId = sourceId;
        this.focusNode = null;
        this.navigationHistory = [];
        this._currentNodes = [];
        this._currentEdges = [];

        this._createPanel();
        this._showLoading('Loading concepts…');

        try {
            this._d3 = await this._loadD3();
        } catch {
            this._showError('Graph visualization unavailable');
            return;
        }

        try {
            const data = await this._fetchNeighborhood(sourceId, null);
            if (data.is_landing) {
                this._renderLandingView(data.nodes);
            } else {
                this._renderGraph(data.nodes, data.edges, data.focus_concept);
            }
        } catch (err) {
            this._showError(err.status === 503
                ? 'Knowledge graph service unavailable'
                : 'Error loading graph data');
        }
    }

    /**
     * Navigate to a concept's neighborhood.
     * @param {string} conceptName
     */
    async navigateTo(conceptName) {
        if (this.focusNode) {
            this.navigationHistory.push(this.focusNode);
        }
        this._updateBackButton();
        this._showLoading('Loading neighborhood…');

        try {
            const data = await this._fetchNeighborhood(this.sourceId, conceptName);
            if (!data.nodes || data.nodes.length === 0) {
                this._showError(`No neighborhood data found for "${conceptName}"`);
                // Pop the history entry we just pushed since navigation failed
                if (this.navigationHistory.length > 0) {
                    this.navigationHistory.pop();
                    this._updateBackButton();
                }
                return;
            }
            this._transitionGraph(data.nodes, data.edges, conceptName);
        } catch {
            this._showError('Error loading graph data');
            if (this.navigationHistory.length > 0) {
                this.navigationHistory.pop();
                this._updateBackButton();
            }
        }
    }

    /**
     * Go back to previous focus node.
     */
    async navigateBack() {
        if (this.navigationHistory.length === 0) {
            // Go back to landing view
            this.focusNode = null;
            this._showLoading('Loading concepts…');
            try {
                const data = await this._fetchNeighborhood(this.sourceId, null);
                if (data.is_landing) {
                    this._renderLandingView(data.nodes);
                } else {
                    this._renderGraph(data.nodes, data.edges, data.focus_concept);
                }
            } catch {
                this._showError('Error loading graph data');
            }
            this._updateBackButton();
            return;
        }

        const prev = this.navigationHistory.pop();
        this._updateBackButton();
        this._showLoading('Loading neighborhood…');

        try {
            const data = await this._fetchNeighborhood(this.sourceId, prev);
            this._transitionGraph(data.nodes, data.edges, prev);
        } catch {
            this._showError('Error loading graph data');
        }
    }

    /**
     * Search concepts by natural language query.
     * @param {string} query
     */
    async search(query) {
        if (!query || !query.trim()) return;

        this._showSearchResults([]);
        this._setSearchLoading(true);

        try {
            const params = new URLSearchParams({ query: query.trim() });
            if (this.sourceId) params.set('source_id', this.sourceId);

            const resp = await fetch(`/api/knowledge-graph/search/concepts?${params}`);
            if (!resp.ok) throw Object.assign(new Error(), { status: resp.status });
            const data = await resp.json();

            if (!data.matches || data.matches.length === 0) {
                this._showSearchResults([], 'No matching concepts found');
            } else {
                this._showSearchResults(data.matches);
            }
        } catch {
            this._showSearchResults([], 'Search failed');
        } finally {
            this._setSearchLoading(false);
        }
    }

    /** Close the explorer panel and clean up. */
    close() {
        if (this.simulation) {
            this.simulation.stop();
            this.simulation = null;
        }
        if (this.panel) {
            this.panel.remove();
            this.panel = null;
        }
        this._svg = null;
        this._d3 = null;
        this._currentNodes = [];
        this._currentEdges = [];
        this.navigationHistory = [];
    }

    // ------------------------------------------------------------------
    // Panel DOM creation
    // ------------------------------------------------------------------

    _createPanel() {
        // Remove existing panel if any
        if (this.panel) this.close();

        this.panel = document.createElement('div');
        this.panel.className = 'kg-explorer-panel';
        this.panel.setAttribute('role', 'dialog');
        this.panel.setAttribute('aria-label', 'Knowledge Graph Explorer');

        this.panel.innerHTML = `
            <div class="kg-explorer-header">
                <button class="kg-explorer-back-btn" aria-label="Go back" title="Go back" disabled>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2">
                        <polyline points="15,18 9,12 15,6"></polyline>
                    </svg>
                </button>
                <div class="kg-explorer-search-wrap">
                    <input type="text" class="kg-explorer-search"
                           placeholder="Search concepts…"
                           aria-label="Search concepts" />
                    <div class="kg-explorer-search-results" role="listbox"
                         aria-label="Search results"></div>
                </div>
                <button class="kg-explorer-close-btn" aria-label="Close explorer" title="Close">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="kg-explorer-body">
                <div class="kg-explorer-viewport"></div>
                <div class="kg-node-tooltip" aria-hidden="true"></div>
                <div class="kg-explorer-detail" aria-live="polite"></div>
            </div>
        `;

        // Wire header buttons
        this.panel.querySelector('.kg-explorer-close-btn')
            .addEventListener('click', () => this.close());
        this.panel.querySelector('.kg-explorer-back-btn')
            .addEventListener('click', () => this.navigateBack());

        // Wire search
        const searchInput = this.panel.querySelector('.kg-explorer-search');
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.search(searchInput.value);
            }
            if (e.key === 'Escape') {
                this._hideSearchResults();
                searchInput.blur();
            }
        });
        searchInput.addEventListener('input', () => {
            clearTimeout(this._searchTimeout);
            if (!searchInput.value.trim()) {
                this._hideSearchResults();
                return;
            }
            this._searchTimeout = setTimeout(() => this.search(searchInput.value), 400);
        });
        searchInput.addEventListener('blur', () => {
            // Delay so click on result fires first
            setTimeout(() => this._hideSearchResults(), 200);
        });

        document.body.appendChild(this.panel);
    }

    // ------------------------------------------------------------------
    // Landing view (top 10 concepts list)
    // ------------------------------------------------------------------

    _renderLandingView(nodes) {
        const viewport = this.panel.querySelector('.kg-explorer-viewport');
        this._hideDetail();

        if (!nodes || nodes.length === 0) {
            viewport.innerHTML = `<div class="kg-explorer-empty">No concepts found for this source.</div>`;
            return;
        }

        const list = document.createElement('div');
        list.className = 'kg-explorer-landing';
        list.innerHTML = `<h3 class="kg-explorer-landing-title">Top concepts</h3>`;

        const ul = document.createElement('ul');
        ul.className = 'kg-explorer-landing-list';
        ul.setAttribute('role', 'list');

        nodes.forEach(node => {
            const li = document.createElement('li');
            li.className = 'kg-explorer-landing-item';
            li.setAttribute('role', 'listitem');
            li.setAttribute('tabindex', '0');

            const color = this._nodeColor(node.source_type);
            li.innerHTML = `
                <span class="kg-landing-dot" style="background:${color}"></span>
                <span class="kg-landing-name">${this._esc(node.name)}</span>
                <span class="kg-landing-degree" title="Relationships">${node.degree}</span>
            `;

            li.addEventListener('click', () => this.navigateTo(node.name));
            li.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.navigateTo(node.name);
                }
            });
            ul.appendChild(li);
        });

        list.appendChild(ul);
        viewport.innerHTML = '';
        viewport.appendChild(list);
    }

    // ------------------------------------------------------------------
    // D3 force-directed graph rendering (Task 12.2)
    // ------------------------------------------------------------------

    /**
     * Render a fresh graph from scratch.
     * @param {Array} nodes
     * @param {Array} edges
     * @param {string|null} focusConcept
     */
    _renderGraph(nodes, edges, focusConcept) {
        const d3 = this._d3;
        if (!d3) return;

        this.focusNode = focusConcept;
        this._currentNodes = nodes;
        this._currentEdges = edges;
        this._hideDetail();

        const viewport = this.panel.querySelector('.kg-explorer-viewport');
        viewport.innerHTML = '';

        const rect = viewport.getBoundingClientRect();
        const width = rect.width || 600;
        const height = rect.height || 400;

        // Build SVG
        const svg = d3.select(viewport)
            .append('svg')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', `0 0 ${width} ${height}`)
            .attr('role', 'img')
            .attr('aria-label', 'Knowledge graph visualization');

        this._svg = svg;

        // Arrow marker for directed edges
        svg.append('defs').append('marker')
            .attr('id', 'kg-arrow')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 28)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', '#94a3b8');

        // Prepare data
        const nodeMap = new Map(nodes.map(n => [n.name, { ...n }]));
        const links = edges
            .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
            .map(e => ({
                source: e.source,
                target: e.target,
                relationship_type: e.relationship_type,
            }));
        const nodeData = Array.from(nodeMap.values());

        // Force simulation
        if (this.simulation) this.simulation.stop();

        this.simulation = d3.forceSimulation(nodeData)
            .force('link', d3.forceLink(links).id(d => d.name).distance(80).strength(0.5))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide(30));

        // Edge group
        const edgeG = svg.append('g').attr('class', 'kg-edges');
        const link = edgeG.selectAll('g')
            .data(links)
            .join('g')
            .attr('class', 'kg-edge-group');

        link.append('line')
            .attr('class', 'kg-edge')
            .attr('marker-end', 'url(#kg-arrow)');

        link.append('text')
            .attr('class', 'kg-edge-label')
            .text(d => d.relationship_type);

        // Node group
        const nodeG = svg.append('g').attr('class', 'kg-nodes');
        const node = nodeG.selectAll('g')
            .data(nodeData, d => d.name)
            .join('g')
            .attr('class', 'kg-node-group')
            .call(this._drag(d3));

        // Focus ring
        node.append('circle')
            .attr('class', 'kg-node-ring')
            .attr('r', 22)
            .attr('fill', 'none')
            .attr('stroke', d => d.name === focusConcept ? '#f59e0b' : 'none')
            .attr('stroke-width', 3);

        // Node circle
        node.append('circle')
            .attr('class', 'kg-node-circle')
            .attr('r', 16)
            .attr('fill', d => this._nodeColor(d.source_type));

        // Node label
        node.append('text')
            .attr('class', 'kg-node-label')
            .attr('dy', -22)
            .text(d => this._truncate(d.name, 20));

        // Source subtitle
        node.append('text')
            .attr('class', 'kg-node-subtitle')
            .attr('dy', 30)
            .text(d => this._truncate(d.source_title || d.source_document, 18));

        // Hover tooltip
        node.on('mouseover', (_event, d) => this._showTooltip(d))
            .on('mouseout', () => this._hideTooltip());

        // Click handlers
        node.on('click', (_event, d) => {
            this._hideTooltip();
            if (d.name === this.focusNode) {
                this._showConceptDetail(d);
            } else {
                this.navigateTo(d.name);
            }
        });

        // Tick
        this.simulation.on('tick', () => {
            link.select('line')
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            link.select('text')
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });
    }

    // ------------------------------------------------------------------
    // Neighborhood transition (Task 12.3)
    // ------------------------------------------------------------------

    /**
     * Transition from current graph to a new neighborhood.
     * Retained nodes stay in place; exiting fade out; entering fade in.
     * @param {Array} newNodes
     * @param {Array} newEdges
     * @param {string} newFocus
     */
    _transitionGraph(newNodes, newEdges, newFocus) {
        const d3 = this._d3;
        if (!d3 || !this._svg) {
            // No existing graph — render fresh
            this._renderGraph(newNodes, newEdges, newFocus);
            return;
        }

        const oldMap = new Map(this._currentNodes.map(n => [n.name, n]));
        const newMap = new Map(newNodes.map(n => [n.name, { ...n }]));

        // Carry over positions from retained nodes
        for (const [name, nd] of newMap) {
            const old = oldMap.get(name);
            if (old && old.x != null) {
                nd.x = old.x;
                nd.y = old.y;
                nd.vx = 0;
                nd.vy = 0;
            }
        }

        this.focusNode = newFocus;
        this._currentNodes = newNodes;
        this._currentEdges = newEdges;

        // Re-render with the merged position data
        const viewport = this.panel.querySelector('.kg-explorer-viewport');
        const rect = viewport.getBoundingClientRect();
        const width = rect.width || 600;
        const height = rect.height || 400;

        // Fade out old SVG
        this._svg.transition().duration(200).style('opacity', 0)
            .on('end', () => {
                this._svg.remove();
                this._svg = null;

                // Build new SVG
                const svg = d3.select(viewport)
                    .append('svg')
                    .attr('width', '100%')
                    .attr('height', '100%')
                    .attr('viewBox', `0 0 ${width} ${height}`)
                    .attr('role', 'img')
                    .attr('aria-label', 'Knowledge graph visualization')
                    .style('opacity', 0);

                this._svg = svg;

                svg.append('defs').append('marker')
                    .attr('id', 'kg-arrow')
                    .attr('viewBox', '0 -5 10 10')
                    .attr('refX', 28).attr('refY', 0)
                    .attr('markerWidth', 6).attr('markerHeight', 6)
                    .attr('orient', 'auto')
                    .append('path').attr('d', 'M0,-5L10,0L0,5').attr('fill', '#94a3b8');

                const nodeData = Array.from(newMap.values());
                const links = newEdges
                    .filter(e => newMap.has(e.source) && newMap.has(e.target))
                    .map(e => ({
                        source: e.source,
                        target: e.target,
                        relationship_type: e.relationship_type,
                    }));

                if (this.simulation) this.simulation.stop();

                this.simulation = d3.forceSimulation(nodeData)
                    .force('link', d3.forceLink(links).id(d => d.name).distance(80).strength(0.5))
                    .force('charge', d3.forceManyBody().strength(-200))
                    .force('center', d3.forceCenter(width / 2, height / 2))
                    .force('collide', d3.forceCollide(30));

                const edgeG = svg.append('g').attr('class', 'kg-edges');
                const link = edgeG.selectAll('g').data(links).join('g').attr('class', 'kg-edge-group');
                link.append('line').attr('class', 'kg-edge').attr('marker-end', 'url(#kg-arrow)');
                link.append('text').attr('class', 'kg-edge-label').text(d => d.relationship_type);

                const nodeG = svg.append('g').attr('class', 'kg-nodes');
                const node = nodeG.selectAll('g')
                    .data(nodeData, d => d.name)
                    .join('g')
                    .attr('class', 'kg-node-group')
                    .call(this._drag(d3));

                node.append('circle').attr('class', 'kg-node-ring')
                    .attr('r', 22).attr('fill', 'none')
                    .attr('stroke', d => d.name === newFocus ? '#f59e0b' : 'none')
                    .attr('stroke-width', 3);

                node.append('circle').attr('class', 'kg-node-circle')
                    .attr('r', 16)
                    .attr('fill', d => this._nodeColor(d.source_type));

                node.append('text').attr('class', 'kg-node-label')
                    .attr('dy', -22).text(d => this._truncate(d.name, 20));

                node.append('text').attr('class', 'kg-node-subtitle')
                    .attr('dy', 30).text(d => this._truncate(d.source_title || d.source_document, 18));

                node.on('mouseover', (_event, d) => this._showTooltip(d))
                    .on('mouseout', () => this._hideTooltip());

                node.on('click', (_event, d) => {
                    this._hideTooltip();
                    if (d.name === this.focusNode) {
                        this._showConceptDetail(d);
                    } else {
                        this.navigateTo(d.name);
                    }
                });

                this.simulation.on('tick', () => {
                    link.select('line')
                        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
                    link.select('text')
                        .attr('x', d => (d.source.x + d.target.x) / 2)
                        .attr('y', d => (d.source.y + d.target.y) / 2);
                    node.attr('transform', d => `translate(${d.x},${d.y})`);
                });

                // Fade in
                svg.transition().duration(300).style('opacity', 1);
            });
    }

    // ------------------------------------------------------------------
    // Concept detail panel
    // ------------------------------------------------------------------

    _showConceptDetail(concept) {
        const detail = this.panel.querySelector('.kg-explorer-detail');
        if (!detail) return;

        const relCount = this._currentEdges.filter(
            e => e.source === concept.name || e.target === concept.name
                || (e.source.name || e.source) === concept.name
                || (e.target.name || e.target) === concept.name
        ).length;

        detail.innerHTML = `
            <div class="kg-detail-content">
                <h4 class="kg-detail-title">${this._esc(concept.name)}</h4>
                <dl class="kg-detail-list">
                    <dt>Source</dt>
                    <dd>${this._esc(concept.source_title || concept.source_document)}</dd>
                    <dt>Type</dt>
                    <dd>${this._esc(concept.source_type)}</dd>
                    <dt>Relationships</dt>
                    <dd>${concept.degree ?? relCount}</dd>
                </dl>
                <button class="kg-detail-close" aria-label="Close detail">&times;</button>
            </div>
        `;
        detail.classList.add('kg-detail-visible');
        detail.querySelector('.kg-detail-close')
            .addEventListener('click', () => this._hideDetail());
    }

    _hideDetail() {
        const detail = this.panel?.querySelector('.kg-explorer-detail');
        if (detail) {
            detail.classList.remove('kg-detail-visible');
            detail.innerHTML = '';
        }
    }

    // ------------------------------------------------------------------
    // Search results UI (Task 12.4)
    // ------------------------------------------------------------------

    _showSearchResults(matches, emptyMsg) {
        const container = this.panel.querySelector('.kg-explorer-search-results');
        if (!container) return;

        container.innerHTML = '';

        if (emptyMsg) {
            container.innerHTML = `<div class="kg-search-empty">${this._esc(emptyMsg)}</div>`;
            container.classList.add('kg-search-visible');
            return;
        }

        if (!matches || matches.length === 0) {
            container.classList.remove('kg-search-visible');
            return;
        }

        matches.forEach(m => {
            const item = document.createElement('div');
            item.className = 'kg-search-result';
            item.setAttribute('role', 'option');
            item.setAttribute('tabindex', '0');
            item.innerHTML = `
                <span class="kg-search-result-name">${this._esc(m.name)}</span>
                <span class="kg-search-result-score">${(m.similarity_score * 100).toFixed(0)}%</span>
            `;
            item.addEventListener('click', () => {
                this._hideSearchResults();
                this.panel.querySelector('.kg-explorer-search').value = '';
                this.navigateTo(m.name);
            });
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    this._hideSearchResults();
                    this.panel.querySelector('.kg-explorer-search').value = '';
                    this.navigateTo(m.name);
                }
            });
            container.appendChild(item);
        });

        container.classList.add('kg-search-visible');
    }

    _hideSearchResults() {
        const container = this.panel?.querySelector('.kg-explorer-search-results');
        if (container) container.classList.remove('kg-search-visible');
    }

    _setSearchLoading(loading) {
        const input = this.panel?.querySelector('.kg-explorer-search');
        if (input) input.classList.toggle('kg-search-loading', loading);
    }

    /**
     * Show tooltip near a hovered node.
     * @param {Object} d - Node datum with x, y, name, source_document, source_type, degree
     */
    _showTooltip(d) {
        const tooltip = this.panel?.querySelector('.kg-node-tooltip');
        if (!tooltip) return;

        const relCount = this._currentEdges.filter(
            e => e.source === d.name || e.target === d.name
                || (e.source.name || e.source) === d.name
                || (e.target.name || e.target) === d.name
        ).length;

        const sourceLabel = d.source_title || d.source_document;

        tooltip.innerHTML = `
            <div class="kg-tooltip-name">${this._esc(d.name)}</div>
            <div class="kg-tooltip-row"><span>Source:</span><span>${this._esc(sourceLabel)}</span></div>
            <div class="kg-tooltip-row"><span>Type:</span><span>${this._esc(d.source_type)}</span></div>
            <div class="kg-tooltip-row"><span>Degree:</span><span>${d.degree ?? relCount}</span></div>
        `;

        // Position relative to the viewport using the SVG viewBox coordinates
        const viewport = this.panel.querySelector('.kg-explorer-viewport');
        const svg = viewport?.querySelector('svg');
        if (!svg) return;

        const svgRect = svg.getBoundingClientRect();
        const viewBox = svg.viewBox.baseVal;
        const scaleX = svgRect.width / viewBox.width;
        const scaleY = svgRect.height / viewBox.height;

        const vpRect = viewport.getBoundingClientRect();
        const left = (d.x * scaleX) + (svgRect.left - vpRect.left) + 20;
        const top = (d.y * scaleY) + (svgRect.top - vpRect.top) - 20;

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
        tooltip.classList.add('kg-tooltip-visible');
    }

    /** Hide the node tooltip. */
    _hideTooltip() {
        const tooltip = this.panel?.querySelector('.kg-node-tooltip');
        if (tooltip) tooltip.classList.remove('kg-tooltip-visible');
    }


    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    _nodeColor(sourceType) {
        if (sourceType === 'external') return '#50C878';   // green for external KBs
        if (sourceType === 'conversation') return '#9b59b6'; // purple for conversations
        return '#4A90D9'; // blue for documents (default)
    }

    _truncate(text, max) {
        if (!text) return '';
        return text.length > max ? text.substring(0, max) + '…' : text;
    }

    _esc(text) {
        if (!text) return '';
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    }

    _showLoading(msg) {
        const viewport = this.panel?.querySelector('.kg-explorer-viewport');
        if (viewport) {
            viewport.innerHTML = `<div class="kg-explorer-loading">${this._esc(msg)}</div>`;
        }
        // The innerHTML wipe destroys any existing SVG element,
        // so null out the reference to avoid stale D3 selections.
        if (this._svg) {
            this._svg = null;
        }
        if (this.simulation) {
            this.simulation.stop();
            this.simulation = null;
        }
    }

    _showError(msg) {
        const viewport = this.panel?.querySelector('.kg-explorer-viewport');
        if (viewport) {
            viewport.innerHTML = `<div class="kg-explorer-error">${this._esc(msg)}</div>`;
        }
    }

    _updateBackButton() {
        const btn = this.panel?.querySelector('.kg-explorer-back-btn');
        if (btn) {
            btn.disabled = this.navigationHistory.length === 0 && !this.focusNode;
        }
    }

    async _fetchNeighborhood(sourceId, focusConcept) {
        const params = new URLSearchParams({ max_nodes: String(this.maxNodes) });
        if (focusConcept) params.set('focus_concept', focusConcept);

        const resp = await fetch(
            `/api/knowledge-graph/${encodeURIComponent(sourceId)}/neighborhood?${params}`
        );
        if (!resp.ok) throw Object.assign(new Error(), { status: resp.status });
        return resp.json();
    }

    _loadD3() {
        if (window.d3) return Promise.resolve(window.d3);
        return new Promise((resolve, reject) => {
            const existing = document.querySelector('script[src*="d3.v7"]');
            if (existing) {
                existing.addEventListener('load', () => resolve(window.d3));
                existing.addEventListener('error', () => reject(new Error('D3 load failed')));
                return;
            }
            const script = document.createElement('script');
            script.src = 'https://d3js.org/d3.v7.min.js';
            script.onload = () => resolve(window.d3);
            script.onerror = () => reject(new Error('D3 load failed'));
            document.head.appendChild(script);
        });
    }

    _drag(d3) {
        return d3.drag()
            .on('start', (event, d) => {
                if (!event.active) this.simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
                this._hideTooltip();
            })
            .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
                this._hideTooltip();
            })
            .on('end', (event, d) => {
                if (!event.active) this.simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            });
    }
}

// Expose globally so DocumentListPanel can call window.kgExplorerPanel.open()
window.kgExplorerPanel = new KGExplorerPanel();
