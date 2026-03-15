/**
 * ToastNotification — lightweight, self-contained toast notification system.
 * No external dependencies.
 *
 * Usage:
 *   const toast = new ToastNotification();
 *   toast.show({ id: 'op-1', message: 'Working...', type: 'loading' });
 *   toast.update('op-1', { message: 'Done', type: 'success', autoDismissMs: 5000 });
 *   toast.dismiss('op-1');
 */
class ToastNotification {
    constructor() {
        /** @type {HTMLElement|null} */
        this.container = null;
        /** @type {Map<string, {element: HTMLElement, timer: number|null}>} */
        this.toasts = new Map();
    }

    /**
     * Show a new toast.
     * @param {Object} opts
     * @param {string}  opts.id
     * @param {string}  opts.message
     * @param {'loading'|'success'|'error'} [opts.type='loading']
     * @param {number|null} [opts.autoDismissMs=null]
     * @returns {string} the toast id
     */
    show({ id, message, type = 'loading', autoDismissMs = null }) {
        this._ensureContainer();

        if (this.toasts.has(id)) {
            this.update(id, { message, type, autoDismissMs });
            return id;
        }

        const el = document.createElement('div');
        el.className = `toast toast--${type}`;
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.dataset.toastId = id;

        el.innerHTML = `
            <span class="toast__icon">${this._iconFor(type)}</span>
            <span class="toast__message">${this._escapeHtml(message)}</span>
            <button class="toast__close" aria-label="Dismiss notification">&times;</button>
        `;

        el.querySelector('.toast__close').addEventListener('click', () => this.dismiss(id));

        this.container.appendChild(el);
        // Trigger reflow so the fade-in transition plays
        void el.offsetWidth;
        el.classList.add('toast--visible');

        const timer = this._scheduleAutoDismiss(id, autoDismissMs);
        this.toasts.set(id, { element: el, timer });
        return id;
    }

    /**
     * Update an existing toast.
     * @param {string} id
     * @param {Object} updates
     * @param {string}  [updates.message]
     * @param {'loading'|'success'|'error'} [updates.type]
     * @param {number|null} [updates.autoDismissMs]
     */
    update(id, { message, type, autoDismissMs } = {}) {
        const entry = this.toasts.get(id);
        if (!entry) return;

        const { element } = entry;

        if (type !== undefined) {
            element.className = `toast toast--${type} toast--visible`;
            element.querySelector('.toast__icon').innerHTML = this._iconFor(type);
        }
        if (message !== undefined) {
            element.querySelector('.toast__message').innerHTML = this._escapeHtml(message);
        }

        // Clear any previous auto-dismiss and reschedule
        if (entry.timer !== null) {
            clearTimeout(entry.timer);
            entry.timer = null;
        }
        if (autoDismissMs !== undefined) {
            entry.timer = this._scheduleAutoDismiss(id, autoDismissMs);
        }
    }

    /**
     * Dismiss (remove) a toast by id.
     * @param {string} id
     */
    dismiss(id) {
        const entry = this.toasts.get(id);
        if (!entry) return;

        if (entry.timer !== null) clearTimeout(entry.timer);

        const el = entry.element;
        el.classList.remove('toast--visible');
        el.classList.add('toast--exiting');

        el.addEventListener('transitionend', () => {
            el.remove();
            this.toasts.delete(id);
            this._removeContainerIfEmpty();
        }, { once: true });

        // Fallback removal if transitionend doesn't fire
        setTimeout(() => {
            if (this.toasts.has(id)) {
                el.remove();
                this.toasts.delete(id);
                this._removeContainerIfEmpty();
            }
        }, 400);
    }

    /* ------------------------------------------------------------------ */
    /*  Private helpers                                                    */
    /* ------------------------------------------------------------------ */

    _ensureContainer() {
        if (this.container && document.body.contains(this.container)) return;
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        this.container.setAttribute('aria-label', 'Notifications');
        document.body.appendChild(this.container);
    }

    _removeContainerIfEmpty() {
        if (this.container && this.toasts.size === 0) {
            this.container.remove();
            this.container = null;
        }
    }

    /**
     * @param {string} id
     * @param {number|null} ms
     * @returns {number|null}
     */
    _scheduleAutoDismiss(id, ms) {
        if (ms == null || ms <= 0) return null;
        return setTimeout(() => this.dismiss(id), ms);
    }

    _iconFor(type) {
        switch (type) {
            case 'loading':
                return '<span class="toast__spinner" aria-hidden="true"></span>';
            case 'success':
                return '<span aria-hidden="true">&#10003;</span>';
            case 'error':
                return '<span aria-hidden="true">&#10007;</span>';
            default:
                return '';
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}
