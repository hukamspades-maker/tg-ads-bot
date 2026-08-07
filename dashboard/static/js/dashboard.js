/**
 * Dashboard Alpine.js application — real-time SPA with WebSocket.
 */
function dashboard() {
    return {
        // State
        currentPage: 'dashboard',
        sidebarOpen: false,
        token: localStorage.getItem('token') || '',
        ws: null,
        wsReconnectTimer: null,
        toasts: [],

        // Data
        overviewStats: [],
        accounts: [],
        logs: [],
        system: {
            cpu_percent: 0, ram_percent: 0, ram_used_mb: 0, ram_total_mb: 0,
            disk_percent: 0, disk_used_gb: 0, disk_total_gb: 0,
            net_sent_mb: 0, net_recv_mb: 0, uptime_seconds: 0,
        },
        periodStats: { sent: 0, failed: 0, success_rate: 0, flood_waits: 0, queue_processed: 0 },
        selectedPeriod: 'today',
        schedulerJobs: [],
        importStatus: { active: false, imported: 0, failed: 0, progress: 0, speed: 0 },
        logFilter: { category: '', level: '' },

        // Premium data
        premiumUsers: [],
        premiumPlans: [],
        premiumGrantForm: { user_id: '', duration: '' },

        // Force Join data
        forceJoinChannels: [],
        fjAddForm: { channel: '', title: '' },

        // Broadcast data
        broadcastStatus: { message: '', media_type: '', interval: 0, delay: 0, loop_running: false },

        // Charts
        hourlyChart: null,
        dailyChart: null,
        successFailChart: null,

        // Navigation items
        navItems: [
            { id: 'dashboard', icon: '📊', label: 'Dashboard' },
            { id: 'accounts', icon: '👤', label: 'Accounts' },
            { id: 'premium', icon: '⭐', label: 'Premium' },
            { id: 'forcejoin', icon: '🔗', label: 'Force Join' },
            { id: 'broadcast', icon: '📢', label: 'Broadcast' },
            { id: 'logs', icon: '⚡', label: 'Live Logs' },
            { id: 'analytics', icon: '📈', label: 'Analytics' },
            { id: 'imports', icon: '📥', label: 'Imports' },
            { id: 'exports', icon: '📤', label: 'Exports' },
            { id: 'scheduler', icon: '📅', label: 'Scheduler' },
        ],

        // Init
        init() {
            // Detect the current page from the URL on initial load
            this._syncPageFromUrl();

            // Handle browser back/forward navigation
            window.addEventListener('popstate', () => this._syncPageFromUrl());

            this.connectWebSocket();
            this.fetchOverview();
            this.fetchAccounts();
            this.fetchLogs();
            this.fetchPeriodStats('today');

            // Auto-refresh every 5s
            setInterval(() => {
                if (this.currentPage === 'dashboard') this.fetchOverview();
                if (this.currentPage === 'accounts') this.fetchAccounts();
            }, 5000);

            // Init charts after DOM ready
            this.$nextTick(() => {
                setTimeout(() => this.initCharts(), 500);
            });
        },

        _syncPageFromUrl() {
            const path = window.location.pathname.replace(/^\/+/, '').split('/')[0] || 'dashboard';
            const validPages = this.navItems.map(n => n.id);
            this.currentPage = validPages.includes(path) ? path : 'dashboard';

            if (this.currentPage === 'dashboard') {
                this.fetchOverview();
                this.$nextTick(() => this.initCharts());
            }
            if (this.currentPage === 'accounts') this.fetchAccounts();
            if (this.currentPage === 'logs') this.fetchLogs();
            if (this.currentPage === 'scheduler') this.fetchScheduler();
            if (this.currentPage === 'premium') this.fetchPremium();
            if (this.currentPage === 'forcejoin') this.fetchForceJoin();
            if (this.currentPage === 'broadcast') this.fetchBroadcast();
        },

        // WebSocket
        connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/api/ws?token=${this.token}`;

            try {
                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    console.log('WebSocket connected');
                    if (this.wsReconnectTimer) {
                        clearTimeout(this.wsReconnectTimer);
                        this.wsReconnectTimer = null;
                    }
                };

                this.ws.onmessage = (event) => {
                    const msg = JSON.parse(event.data);
                    this.handleWsMessage(msg);
                };

                this.ws.onclose = () => {
                    console.log('WebSocket disconnected, reconnecting...');
                    this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
                };

                this.ws.onerror = () => {
                    this.ws.close();
                };

                // Keepalive ping every 30s
                setInterval(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send('ping');
                    }
                }, 30000);
            } catch (e) {
                console.error('WebSocket error:', e);
                this.wsReconnectTimer = setTimeout(() => this.connectWebSocket(), 5000);
            }
        },

        handleWsMessage(msg) {
            switch (msg.type) {
                case 'init':
                    this.updateOverview(msg.data);
                    break;
                case 'system_metric':
                    this.system = { ...this.system, ...msg.data };
                    break;
                case 'log':
                    this.logs.unshift(msg.data);
                    if (this.logs.length > 500) this.logs.pop();
                    break;
                case 'message_sent':
                case 'message_failed':
                    this.fetchOverview();
                    break;
                case 'account_status':
                    this.fetchAccounts();
                    break;
                case 'import_progress':
                    this.importStatus = msg.data;
                    break;
            }
        },

        // API calls
        async apiFetch(url, options = {}) {
            const headers = { 'Authorization': `Bearer ${this.token}`, ...options.headers };
            try {
                const res = await fetch(url, { ...options, headers });
                if (res.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                return await res.json();
            } catch (e) {
                console.error('API error:', e);
                return null;
            }
        },

        async fetchOverview() {
            const data = await this.apiFetch('/api/overview');
            if (data) this.updateOverview(data);
        },

        updateOverview(data) {
            const accs = data.accounts || {};
            this.overviewStats = [
                { label: 'Total Accounts', value: accs.total || 0, color: 'text-white' },
                { label: 'Active', value: accs.active || 0, color: 'text-green-400' },
                { label: 'Online', value: accs.online || 0, color: 'text-cyan-400' },
                { label: 'Messages Sent', value: data.total_sent || 0, color: 'text-indigo-400' },
                { label: 'Failed', value: data.total_failed || 0, color: 'text-red-400' },
                { label: 'Success Rate', value: (data.success_rate || 0) + '%', color: 'text-green-400' },
                { label: 'Flood Waits', value: data.flood_count || 0, color: 'text-yellow-400' },
                { label: 'Queue Size', value: data.queue_size || 0, color: 'text-purple-400' },
                { label: 'Tasks Running', value: data.total_tasks || 0, color: 'text-cyan-400' },
                { label: 'Schedulers', value: data.active_schedulers || 0, color: 'text-amber-400' },
                { label: 'Msg/min', value: data.messages_per_minute ? data.messages_per_minute.sent : 0, color: 'text-indigo-400' },
                { label: 'Spam Blocks', value: data.spam_blocks || 0, color: 'text-red-400' },
            ];
            if (data.system) this.system = data.system;
        },

        async fetchAccounts() {
            const data = await this.apiFetch('/api/accounts');
            if (data) this.accounts = data;
        },

        async fetchLogs() {
            const params = new URLSearchParams();
            params.set('limit', '200');
            if (this.logFilter.category) params.set('category', this.logFilter.category);
            if (this.logFilter.level) params.set('level', this.logFilter.level);
            const data = await this.apiFetch(`/api/logs?${params}`);
            if (data) this.logs = data.reverse();
        },

        async fetchPeriodStats(period) {
            this.selectedPeriod = period;
            const data = await this.apiFetch(`/api/stats/time/${period}`);
            if (data) this.periodStats = data;
        },

        async fetchSystem() {
            const data = await this.apiFetch('/api/system');
            if (data) this.system = data;
        },

        async accountAction(phone, action) {
            const data = await this.apiFetch(`/api/accounts/${phone}/action/${action}`, { method: 'POST' });
            if (data) {
                this.showToast(data.message || 'Action completed', 'success');
                this.fetchAccounts();
            }
        },

        async clearLogs() {
            await this.apiFetch('/api/logs', { method: 'DELETE' });
            this.logs = [];
            this.showToast('Logs cleared', 'success');
        },

        // Navigation
        navigate(page) {
            this.currentPage = page;
            this.sidebarOpen = false;
            window.history.pushState({}, '', '/' + (page === 'dashboard' ? '' : page));

            if (page === 'dashboard') {
                this.fetchOverview();
                this.$nextTick(() => this.initCharts());
            }
            if (page === 'accounts') this.fetchAccounts();
            if (page === 'logs') this.fetchLogs();
            if (page === 'scheduler') this.fetchScheduler();
            if (page === 'premium') this.fetchPremium();
            if (page === 'forcejoin') this.fetchForceJoin();
            if (page === 'broadcast') this.fetchBroadcast();
        },

        async fetchScheduler() {
            const data = await this.apiFetch('/api/scheduler');
            if (data) this.schedulerJobs = data;
        },

        // Premium
        async fetchPremium() {
            const [users, plans] = await Promise.all([
                this.apiFetch('/api/premium/users'),
                this.apiFetch('/api/premium/plans'),
            ]);
            if (users) this.premiumUsers = users;
            if (plans) this.premiumPlans = plans;
        },

        async grantPremium() {
            if (!this.premiumGrantForm.user_id || !this.premiumGrantForm.duration) {
                this.showToast('Fill in User ID and Duration', 'error'); return;
            }
            const data = await this.apiFetch('/api/premium/grant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.premiumGrantForm),
            });
            if (data && data.status === 'ok') {
                this.showToast('Premium granted!', 'success');
                this.premiumGrantForm = { user_id: '', duration: '' };
                this.fetchPremium();
            } else {
                this.showToast(data?.detail || 'Failed', 'error');
            }
        },

        async grantPremiumPlan(planId) {
            if (!this.premiumGrantForm.user_id) {
                this.showToast('Enter User ID first', 'error'); return;
            }
            const plan = this.premiumPlans.find(p => p.id === planId);
            if (!plan) return;
            const data = await this.apiFetch('/api/premium/grant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: this.premiumGrantForm.user_id, duration: plan.days + 'd' }),
            });
            if (data && data.status === 'ok') {
                this.showToast(`${plan.label} granted!`, 'success');
                this.premiumGrantForm = { user_id: '', duration: '' };
                this.fetchPremium();
            } else {
                this.showToast(data?.detail || 'Failed', 'error');
            }
        },

        async revokePremium(userId) {
            const data = await this.apiFetch('/api/premium/revoke', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId }),
            });
            if (data && data.status === 'ok') {
                this.showToast('Premium revoked', 'success');
                this.fetchPremium();
            }
        },

        premiumTimeLeft(expiresAt) {
            if (!expiresAt) return 'N/A';
            const exp = new Date(expiresAt);
            const now = new Date();
            const diff = exp - now;
            if (diff <= 0) return 'Expired';
            const d = Math.floor(diff / 86400000);
            const h = Math.floor((diff % 86400000) / 3600000);
            return `${d}d ${h}h`;
        },

        // Force Join
        async fetchForceJoin() {
            const data = await this.apiFetch('/api/forcejoin/channels');
            if (data) this.forceJoinChannels = data;
        },

        async addForceJoinChannel() {
            if (!this.fjAddForm.channel) {
                this.showToast('Enter channel username or ID', 'error'); return;
            }
            const data = await this.apiFetch('/api/forcejoin/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.fjAddForm),
            });
            if (data && data.status === 'ok') {
                this.showToast('Channel added!', 'success');
                this.fjAddForm = { channel: '', title: '' };
                this.fetchForceJoin();
            } else {
                this.showToast(data?.message || 'Already exists or failed', 'error');
            }
        },

        async removeForceJoinChannel(channel) {
            const data = await this.apiFetch('/api/forcejoin/remove', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel }),
            });
            if (data && data.status === 'ok') {
                this.showToast('Channel removed', 'success');
                this.fetchForceJoin();
            }
        },

        // Broadcast
        async fetchBroadcast() {
            const data = await this.apiFetch('/api/broadcast/status');
            if (data) this.broadcastStatus = data;
        },

        // Charts
        initCharts() {
            this.initHourlyChart();
            this.initDailyChart();
        },

        initHourlyChart() {
            const el = document.getElementById('chart-hourly');
            if (!el) return;
            if (this.hourlyChart) this.hourlyChart.destroy();

            this.hourlyChart = new ApexCharts(el, {
                chart: { type: 'area', height: 250, background: 'transparent', toolbar: { show: false },
                    animations: { enabled: true, speed: 800 } },
                series: [
                    { name: 'Sent', data: new Array(24).fill(0) },
                    { name: 'Failed', data: new Array(24).fill(0) },
                ],
                xaxis: { categories: Array.from({length: 24}, (_, i) => `${i}:00`),
                    labels: { style: { colors: '#6b7280' } } },
                yaxis: { labels: { style: { colors: '#6b7280' } } },
                colors: ['#818cf8', '#f87171'],
                stroke: { curve: 'smooth', width: 2 },
                fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05 } },
                grid: { borderColor: 'rgba(255,255,255,0.05)' },
                theme: { mode: 'dark' },
                legend: { labels: { colors: '#9ca3af' } },
            });
            this.hourlyChart.render();
            this.updateCharts();
        },

        initDailyChart() {
            const el = document.getElementById('chart-daily');
            if (!el) return;
            if (this.dailyChart) this.dailyChart.destroy();

            this.dailyChart = new ApexCharts(el, {
                chart: { type: 'bar', height: 250, background: 'transparent', toolbar: { show: false } },
                series: [
                    { name: 'Sent', data: new Array(7).fill(0) },
                    { name: 'Failed', data: new Array(7).fill(0) },
                ],
                xaxis: { categories: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                    labels: { style: { colors: '#6b7280' } } },
                yaxis: { labels: { style: { colors: '#6b7280' } } },
                colors: ['#22d3ee', '#f59e0b'],
                plotOptions: { bar: { borderRadius: 4, columnWidth: '60%' } },
                grid: { borderColor: 'rgba(255,255,255,0.05)' },
                theme: { mode: 'dark' },
                legend: { labels: { colors: '#9ca3af' } },
            });
            this.dailyChart.render();
        },

        async updateCharts() {
            const data = await this.apiFetch('/api/stats/charts');
            if (!data) return;
            if (this.hourlyChart && data.hourly) {
                this.hourlyChart.updateSeries([
                    { name: 'Sent', data: data.hourly.sent },
                    { name: 'Failed', data: data.hourly.failed },
                ]);
            }
            if (this.dailyChart && data.daily) {
                this.dailyChart.updateOptions({ xaxis: { categories: data.daily.labels } });
                this.dailyChart.updateSeries([
                    { name: 'Sent', data: data.daily.sent },
                    { name: 'Failed', data: data.daily.failed },
                ]);
            }
        },

        // Utilities
        formatUptime(seconds) {
            if (!seconds) return '0s';
            const d = Math.floor(seconds / 86400);
            const h = Math.floor((seconds % 86400) / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            if (d > 0) return `${d}d ${h}h`;
            if (h > 0) return `${h}h ${m}m`;
            return `${m}m`;
        },

        formatTime(ts) {
            if (!ts) return '';
            const d = new Date(ts * 1000);
            return d.toLocaleTimeString();
        },

        statusClass(status) {
            const map = {
                active: 'bg-green-500/20 text-green-400',
                paused: 'bg-yellow-500/20 text-yellow-400',
                banned: 'bg-red-500/20 text-red-400',
                floodwait: 'bg-orange-500/20 text-orange-400',
                dead: 'bg-gray-500/20 text-gray-400',
            };
            return map[status] || 'bg-gray-500/20 text-gray-400';
        },

        logLevelClass(level) {
            if (level === 'error' || level === 'critical') return 'bg-red-500/5';
            if (level === 'warning') return 'bg-yellow-500/5';
            return '';
        },

        logLevelColor(level) {
            const map = { info: 'text-blue-400', warning: 'text-yellow-400', error: 'text-red-400', critical: 'text-red-600', debug: 'text-gray-500' };
            return map[level] || 'text-gray-400';
        },

        showToast(message, type = 'success') {
            const id = Date.now();
            this.toasts.push({ id, message, type });
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 3000);
        },

        async logout() {
            await fetch('/api/logout', { method: 'POST' });
            localStorage.removeItem('token');
            window.location.href = '/login';
        },
    };
}
