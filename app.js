/**
 * Email Scraper Frontend Application
 * Vanilla JavaScript implementation
 */

// Application State
const state = {
    userInfo: null,
    wsConnected: false,
    backendAvailable: null,
    currentJob: null,
    jobs: [],
    ws: null,
    reconnectTimeout: null
};

// Configuration - Auto-detect environment
const config = (() => {
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = isLocalhost ? 'localhost:8000' : window.location.host;
    
    return {
        backendUrl: isLocalhost ? 'http://localhost:8000' : `${protocol}//${window.location.host}`,
        wsUrl: isLocalhost ? 'ws://localhost:8000/ws' : `${wsProtocol}//${window.location.host}/ws`
    };
})();

// Utility Functions
const utils = {
    generateUserId() {
        return `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    },
    
    formatDate(dateString) {
        return new Date(dateString).toLocaleDateString();
    },
    
    formatDateTime(dateString) {
        return new Date(dateString).toLocaleString();
    },
    
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icons = {
            success: 'check-circle',
            error: 'x-circle',
            info: 'info',
            warning: 'alert-triangle'
        };
        
        toast.innerHTML = `
            <i data-lucide="${icons[type]}" class="w-5 h-5 toast-icon"></i>
            <div class="toast-message">${message}</div>
        `;
        
        container.appendChild(toast);
        lucide.createIcons();
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => {
                container.removeChild(toast);
            }, 300);
        }, 5000);
    },
    
    async checkUserBlocked(userId) {
        try {
            const response = await fetch(`${config.backendUrl}/api/check-blocked`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ user_id: userId }),
            });
            
            if (response.ok) {
                const data = await response.json();
                return data.is_blocked;
            }
        } catch (err) {
            console.warn('Failed to check user status:', err);
        }
        return false;
    },
    
    async logActivity(jobId, urls, totalEmails, status) {
        if (!state.userInfo) return;
        
        try {
            await fetch(`${config.backendUrl}/api/activity`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: state.userInfo.id,
                    user_name: state.userInfo.name,
                    job_id: jobId,
                    urls: JSON.stringify(urls),
                    total_emails: totalEmails,
                    status: status,
                }),
            });
        } catch (err) {
            console.warn('Failed to log activity:', err);
        }
    }
};

// User Management
const userManager = {
    async init() {
        const storedUser = localStorage.getItem('emailScraperUser');
        if (storedUser) {
            try {
                state.userInfo = JSON.parse(storedUser);
                
                // Check if user is blocked
                const isBlocked = await utils.checkUserBlocked(state.userInfo.id);
                if (isBlocked) {
                    utils.showToast('Your account has been blocked. Please contact the administrator.', 'error');
                    localStorage.removeItem('emailScraperUser');
                    state.userInfo = null;
                    this.showDialog();
                    return;
                }
                
                this.updateUserDisplay();
                utils.showToast(`Welcome back, ${state.userInfo.name}!`, 'success');
            } catch (err) {
                this.showDialog();
            }
        } else {
            this.showDialog();
        }
    },
    
    showDialog(isEdit = false) {
        const dialog = document.getElementById('user-dialog');
        const title = document.getElementById('dialog-title');
        const description = document.getElementById('dialog-description');
        const input = document.getElementById('user-name-input');
        const cancelBtn = document.getElementById('cancel-user-dialog');
        const submitBtn = document.getElementById('submit-user-dialog');
        const userInfoDisplay = document.getElementById('user-info-display');
        
        if (isEdit && state.userInfo) {
            title.textContent = 'Update Your Name';
            description.textContent = 'Update your name for the dashboard.';
            input.value = state.userInfo.name;
            cancelBtn.classList.remove('hidden');
            submitBtn.textContent = 'Update';
            
            // Show user info
            userInfoDisplay.classList.remove('hidden');
            document.getElementById('display-user-id').textContent = state.userInfo.id;
            document.getElementById('display-user-date').textContent = utils.formatDate(state.userInfo.createdAt);
        } else {
            title.textContent = 'Welcome to Email Scraper';
            description.textContent = 'Please enter your name to get started. This helps us manage users on our dashboard.';
            input.value = '';
            cancelBtn.classList.add('hidden');
            submitBtn.textContent = 'Continue';
            userInfoDisplay.classList.add('hidden');
        }
        
        dialog.classList.add('active');
        input.focus();
    },
    
    hideDialog() {
        const dialog = document.getElementById('user-dialog');
        dialog.classList.remove('active');
        document.getElementById('user-name-input').value = '';
    },
    
    async register() {
        const input = document.getElementById('user-name-input');
        const name = input.value.trim();
        
        if (!name) {
            utils.showToast('Please enter your name', 'error');
            return;
        }
        
        const isUpdate = state.userInfo !== null;
        const userId = state.userInfo?.id || utils.generateUserId();
        
        const updatedUser = {
            id: userId,
            name: name,
            createdAt: state.userInfo?.createdAt || new Date().toISOString(),
        };
        
        // Register with backend
        try {
            const response = await fetch(`${config.backendUrl}/api/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: userId,
                    name: name,
                    created_at: updatedUser.createdAt,
                }),
            });
            
            if (!response.ok) {
                throw new Error('Failed to register');
            }
        } catch (err) {
            console.warn('Backend registration failed:', err);
        }
        
        // Store locally
        localStorage.setItem('emailScraperUser', JSON.stringify(updatedUser));
        state.userInfo = updatedUser;
        this.hideDialog();
        this.updateUserDisplay();
        
        utils.showToast(
            isUpdate ? `Name updated to ${updatedUser.name}` : `Welcome, ${updatedUser.name}! You can now start scraping.`,
            'success'
        );
    },
    
    updateUserDisplay() {
        if (state.userInfo) {
            document.getElementById('user-info-header').classList.remove('hidden');
            document.getElementById('user-name-display').textContent = state.userInfo.name;
        } else {
            document.getElementById('user-info-header').classList.add('hidden');
        }
    }
};

// Backend Connection Manager
const backendManager = {
    async checkAvailability() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 3000);
            
            const response = await fetch(`${config.backendUrl}/health`, {
                signal: controller.signal,
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                state.backendAvailable = true;
                this.updateStatus();
                this.connectWebSocket();
            } else {
                state.backendAvailable = false;
                this.updateStatus();
            }
        } catch (err) {
            state.backendAvailable = false;
            this.updateStatus();
            console.warn('Backend not available. Make sure the Python backend is running on port 8000.');
        }
    },
    
    connectWebSocket() {
        try {
            const ws = new WebSocket(config.wsUrl);
            
            ws.onopen = () => {
                state.wsConnected = true;
                state.backendAvailable = true;
                this.updateStatus();
                if (state.reconnectTimeout) {
                    clearTimeout(state.reconnectTimeout);
                    state.reconnectTimeout = null;
                }
                
                // Send user ID to establish context
                if (state.userInfo) {
                    ws.send('user_id:' + JSON.stringify({ user_id: state.userInfo.id }));
                }
                
                utils.showToast('Connected to scraper backend', 'success');
            };
            
            ws.onclose = () => {
                state.wsConnected = false;
                this.updateStatus();
                // Attempt reconnect after 5 seconds
                if (state.reconnectTimeout) {
                    clearTimeout(state.reconnectTimeout);
                }
                state.reconnectTimeout = setTimeout(() => {
                    console.log('Attempting to reconnect...');
                    this.connectWebSocket();
                }, 5000);
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                state.backendAvailable = false;
                this.updateStatus();
            };
            
            ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };
            
            state.ws = ws;
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            state.backendAvailable = false;
            this.updateStatus();
        }
    },
    
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'job_created':
                    jobManager.handleJobCreated(message);
                    break;
                case 'progress':
                    jobManager.handleProgress(message);
                    break;
                case 'finished':
                    jobManager.handleFinished(message);
                    break;
                case 'cancelled':
                    jobManager.handleCancelled(message);
                    break;
                case 'error':
                    jobManager.handleError(message);
                    break;
            }
        } catch (err) {
            console.error('Failed to parse message:', err);
        }
    },
    
    updateStatus() {
        const indicator = document.getElementById('status-indicator');
        const statusText = document.getElementById('status-text');
        const backendWarning = document.getElementById('backend-warning');
        const startBtn = document.getElementById('start-scraping-btn');
        const startBtnText = document.getElementById('start-btn-text');
        
        if (state.wsConnected) {
            indicator.className = 'w-2 h-2 rounded-full bg-green-500';
            statusText.textContent = 'Connected';
            backendWarning.classList.add('hidden');
            startBtn.disabled = false;
            startBtnText.textContent = 'Start Scraping';
        } else if (state.backendAvailable === false) {
            indicator.className = 'w-2 h-2 rounded-full bg-red-500';
            statusText.textContent = 'Backend Offline';
            backendWarning.classList.remove('hidden');
            startBtn.disabled = true;
            startBtnText.textContent = 'Backend Offline';
        } else {
            indicator.className = 'w-2 h-2 rounded-full bg-yellow-500 status-connecting';
            statusText.textContent = 'Connecting...';
            backendWarning.classList.add('hidden');
            startBtn.disabled = true;
            startBtnText.textContent = 'Connecting...';
        }
        
        lucide.createIcons();
    }
};

// Job Manager
const jobManager = {
    async fetchJobs() {
        if (state.backendAvailable !== true) return;
        
        try {
            const response = await fetch(`${config.backendUrl}/jobs`, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            state.jobs = data.reverse();
            this.renderJobHistory();
        } catch (err) {
            console.error('Failed to fetch jobs:', err);
        }
    },
    
    async startScraping() {
        const urlsInput = document.getElementById('urls-input');
        const urls = urlsInput.value.trim();
        
        if (!urls) {
            utils.showToast('Please enter at least one URL', 'error');
            return;
        }
        
        if (!state.userInfo) {
            utils.showToast('User information not found', 'error');
            userManager.showDialog();
            return;
        }
        
        // Check if user is blocked
        const isBlocked = await utils.checkUserBlocked(state.userInfo.id);
        if (isBlocked) {
            utils.showToast('Your account has been blocked. Please contact the administrator.', 'error');
            return;
        }
        
        if (!state.ws || !state.wsConnected) {
            utils.showToast('Backend not connected. Please wait or check if the Python server is running.', 'error');
            return;
        }
        
        const urlList = urls.split('\n').filter(u => u.trim());
        
        state.ws.send('start' + JSON.stringify(urlList));
        urlsInput.value = '';
        
        // Log activity
        await utils.logActivity(null, urlList, 0, 'started');
    },
    
    cancelJob() {
        if (state.currentJob && state.ws && state.wsConnected) {
            state.ws.send('cancel' + state.currentJob.id);
        }
    },
    
    handleJobCreated(message) {
        state.currentJob = {
            id: message.job_id,
            status: 'queued',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            count: message.count,
            progress: { done: 0, total: message.count },
            results: {}
        };
        
        this.renderCurrentJob();
        utils.showToast(`Job created: ${message.count} URLs`, 'success');
    },
    
    handleProgress(message) {
        if (state.currentJob && state.currentJob.id === message.job_id) {
            state.currentJob.status = 'running';
            state.currentJob.updated_at = new Date().toISOString();
            state.currentJob.progress = {
                done: message.done,
                total: message.total,
                current: message.current
            };
            
            if (!state.currentJob.results) {
                state.currentJob.results = {};
            }
            state.currentJob.results[message.current] = message.emails;
            
            this.renderCurrentJob();
        }
    },
    
    handleFinished(message) {
        if (state.currentJob && state.currentJob.id === message.job_id) {
            state.currentJob.status = 'finished';
            state.currentJob.updated_at = new Date().toISOString();
            state.currentJob.results = message.results;
            
            this.renderCurrentJob();
            utils.showToast('Scraping completed!', 'success');
            this.fetchJobs();
            
            // Log activity
            if (state.userInfo) {
                const totalEmails = Object.values(message.results || {}).reduce(
                    (sum, emails) => sum + emails.length,
                    0
                );
                
                const urls = Object.keys(message.results || {});
                utils.logActivity(message.job_id, urls, totalEmails, 'completed');
            }
        }
    },
    
    handleCancelled(message) {
        if (state.currentJob && state.currentJob.id === message.job_id) {
            state.currentJob.status = 'cancelled';
            state.currentJob.updated_at = new Date().toISOString();
            this.renderCurrentJob();
            utils.showToast('Job cancelled', 'info');
        }
    },
    
    handleError(message) {
        utils.showToast(message.msg || 'An error occurred', 'error');
        if (message.job_id && state.currentJob && state.currentJob.id === message.job_id) {
            state.currentJob.status = 'failed';
            state.currentJob.updated_at = new Date().toISOString();
            this.renderCurrentJob();
        }
    },
    
    renderCurrentJob() {
        const card = document.getElementById('current-job-card');
        const jobId = document.getElementById('job-id');
        const statusBadge = document.getElementById('job-status-badge');
        const statusIcon = document.getElementById('job-status-icon');
        const cancelBtn = document.getElementById('cancel-job-btn');
        
        if (!state.currentJob) {
            card.classList.add('hidden');
            return;
        }
        
        card.classList.remove('hidden');
        jobId.textContent = state.currentJob.id;
        
        // Update status badge
        statusBadge.textContent = state.currentJob.status;
        statusBadge.className = `px-3 py-1 rounded-full text-xs font-medium status-${state.currentJob.status}`;
        
        // Update icon
        const icons = {
            running: 'loader-2',
            finished: 'check-circle',
            failed: 'x-circle',
            cancelled: 'stop-circle',
            queued: 'clock'
        };
        statusIcon.setAttribute('data-lucide', icons[state.currentJob.status] || 'clock');
        
        // Show/hide cancel button
        if (state.currentJob.status === 'running') {
            cancelBtn.classList.remove('hidden');
        } else {
            cancelBtn.classList.add('hidden');
        }
        
        // Update progress
        if (state.currentJob.progress) {
            const progressSection = document.getElementById('progress-section');
            const progressText = document.getElementById('progress-text');
            const emailsFoundText = document.getElementById('emails-found-text');
            const progressBar = document.getElementById('progress-bar');
            const currentUrlText = document.getElementById('current-url-text');
            
            const totalEmails = state.currentJob.results ? 
                Object.values(state.currentJob.results).reduce((sum, emails) => sum + emails.length, 0) : 0;
            
            progressText.textContent = `Progress: ${state.currentJob.progress.done} / ${state.currentJob.progress.total}`;
            emailsFoundText.textContent = `${totalEmails} emails found`;
            
            const percentage = (state.currentJob.progress.done / state.currentJob.progress.total) * 100;
            progressBar.style.width = `${percentage}%`;
            
            if (state.currentJob.progress.current) {
                currentUrlText.textContent = `Currently scraping: ${state.currentJob.progress.current}`;
            }
        }
        
        // Update results
        if (state.currentJob.results && Object.keys(state.currentJob.results).length > 0) {
            const resultsSection = document.getElementById('results-section');
            const resultsContainer = document.getElementById('results-container');
            
            resultsSection.classList.remove('hidden');
            resultsContainer.innerHTML = '';
            
            Object.entries(state.currentJob.results).forEach(([url, emails]) => {
                const resultItem = document.createElement('div');
                resultItem.className = 'result-item space-y-2';
                
                const header = document.createElement('div');
                header.className = 'flex items-start gap-2';
                header.innerHTML = `
                    <i data-lucide="search" class="w-4 h-4 mt-1 text-slate-400 flex-shrink-0"></i>
                    <div class="flex-1 min-w-0">
                        <p class="font-medium text-slate-900 truncate">${url}</p>
                        <p class="text-sm text-slate-500">${emails.length} email${emails.length !== 1 ? 's' : ''}</p>
                    </div>
                `;
                
                resultItem.appendChild(header);
                
                if (emails.length > 0) {
                    const emailList = document.createElement('div');
                    emailList.className = 'ml-6 space-y-1';
                    emails.forEach(email => {
                        const emailItem = document.createElement('p');
                        emailItem.className = 'email-item';
                        emailItem.textContent = email;
                        emailList.appendChild(emailItem);
                    });
                    resultItem.appendChild(emailList);
                }
                
                resultsContainer.appendChild(resultItem);
            });
        }
        
        lucide.createIcons();
    },
    
    renderJobHistory() {
        const container = document.getElementById('job-history-container');
        
        if (state.jobs.length === 0) {
            container.innerHTML = '<p class="text-center text-slate-500 py-8">No jobs yet</p>';
            return;
        }
        
        container.innerHTML = '';
        
        state.jobs.forEach(job => {
            const jobItem = document.createElement('div');
            jobItem.className = 'job-history-item flex items-center justify-between p-3 rounded-lg border border-slate-200';
            
            const icons = {
                running: 'loader-2',
                finished: 'check-circle',
                failed: 'x-circle',
                cancelled: 'stop-circle',
                queued: 'clock'
            };
            
            jobItem.innerHTML = `
                <div class="flex items-center gap-3">
                    <i data-lucide="${icons[job.status] || 'clock'}" class="w-4 h-4 text-slate-600"></i>
                    <div>
                        <p class="font-medium text-slate-900">${job.id}</p>
                        <p class="text-sm text-slate-500">
                            ${job.count} URLs • ${utils.formatDateTime(job.created_at)}
                        </p>
                    </div>
                </div>
                <span class="px-3 py-1 rounded-full text-xs font-medium status-${job.status}">
                    ${job.status}
                </span>
            `;
            
            container.appendChild(jobItem);
        });
        
        lucide.createIcons();
    },
    
    exportToCSV() {
        if (!state.currentJob || !state.currentJob.results) return;
        
        const rows = [['URL', 'Email Addresses']];
        
        Object.entries(state.currentJob.results).forEach(([url, emails]) => {
            rows.push([url, emails.join(', ')]);
        });
        
        const csv = rows.map(row => 
            row.map(cell => `"${cell.replace(/"/g, '""')}`).join(',')
        ).join('\n');
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `emails_${Date.now()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        
        utils.showToast('Exported to CSV', 'success');
    }
};

// Event Listeners
function initializeEventListeners() {
    // User Dialog
    document.getElementById('submit-user-dialog').addEventListener('click', () => {
        userManager.register();
    });
    
    document.getElementById('cancel-user-dialog').addEventListener('click', () => {
        if (state.userInfo) {
            userManager.hideDialog();
        }
    });
    
    document.getElementById('user-name-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            userManager.register();
        }
    });
    
    document.getElementById('edit-profile-btn').addEventListener('click', () => {
        userManager.showDialog(true);
    });
    
    // Scraping
    document.getElementById('start-scraping-btn').addEventListener('click', () => {
        jobManager.startScraping();
    });
    
    document.getElementById('cancel-job-btn').addEventListener('click', () => {
        jobManager.cancelJob();
    });
    
    // Export
    document.getElementById('export-csv-btn').addEventListener('click', () => {
        jobManager.exportToCSV();
    });
}

// Application Initialization
function initializeApp() {
    console.log('Email Scraper initializing...');
    
    // Initialize user
    userManager.init();
    
    // Check backend availability
    backendManager.checkAvailability();
    
    // Fetch jobs when backend is available
    setTimeout(() => {
        if (state.backendAvailable) {
            jobManager.fetchJobs();
        }
    }, 1000);
    
    // Initialize event listeners
    initializeEventListeners();
    
    // Initialize icons
    lucide.createIcons();
    
    console.log('Email Scraper initialized');
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}
