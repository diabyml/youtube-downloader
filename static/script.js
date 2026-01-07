/**
 * YouTube Downloader - Frontend JavaScript
 * Handles form submission, progress tracking, and file download
 */

class YouTubeDownloader {
    constructor() {
        this.form = document.getElementById('download-form');
        this.submitBtn = document.getElementById('submit-btn');
        this.progressContainer = document.getElementById('progress-container');
        this.progressFill = document.getElementById('progress-fill');
        this.progressStatus = document.getElementById('progress-status');
        this.progressPercent = document.getElementById('progress-percent');
        this.progressInfo = document.getElementById('progress-info');
        this.errorContainer = document.getElementById('error-container');
        this.errorMessage = document.getElementById('error-message');
        this.resultContainer = document.getElementById('result-container');
        this.resultFilename = document.getElementById('result-filename');
        this.downloadBtn = document.getElementById('download-btn');
        
        // Store last displayed percentage for animation
        this.lastPercent = 0;
        this.currentTaskId = null;
        this.pollInterval = null;
        
        this.init();
    }
    
    init() {
        // Form submission handler
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Download button handler
        this.downloadBtn.addEventListener('click', (e) => this.handleDownload(e));
    }
    
    /**
     * Handle form submission
     */
    async handleSubmit(e) {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(this.form);
        const url = formData.get('url');
        const formatType = formData.get('format_type');
        const quality = document.getElementById('quality').value;
        
        // Validate URL
        if (!this.isValidYouTubeUrl(url)) {
            this.showError('Please enter a valid YouTube URL');
            return;
        }
        
        // Reset UI
        this.resetUI();
        this.setLoadingState(true);
        
        try {
            // Start download
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    format_type: formatType,
                    quality: quality
                })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.message || data.error || 'Download failed');
            }
            
            // Store task ID and start polling
            this.currentTaskId = data.task_id;
            this.showProgress();
            this.startPolling();
            
        } catch (error) {
            this.showError(error.message);
            this.setLoadingState(false);
        }
    }
    
    /**
     * Start polling for progress updates
     */
    startPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
        
        this.pollInterval = setInterval(async () => {
            if (!this.currentTaskId) {
                this.stopPolling();
                return;
            }
            
            try {
                const response = await fetch(`/api/status/${this.currentTaskId}`);
                const data = await response.json();
                
                if (response.ok) {
                    this.updateProgress(data);
                    
                    if (data.status === 'completed') {
                        this.stopPolling();
                        this.showResult(data);
                        this.setLoadingState(false);
                    } else if (data.status === 'error') {
                        this.stopPolling();
                        this.showError(data.error || 'Download failed');
                        this.setLoadingState(false);
                    }
                } else {
                    // Task not found or expired
                    this.stopPolling();
                    this.showError('Download task expired');
                    this.setLoadingState(false);
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 500); // Poll every 500ms for more responsive updates
    }
    
    /**
     * Stop polling for updates
     */
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }
    
    /**
     * Update progress UI with animated percentage
     */
    updateProgress(data) {
        const progress = Math.min(data.progress || 0, 100);
        
        // Animate the percentage number
        this.animatePercentage(progress);
        
        // Update progress bar
        this.progressFill.style.width = progress + '%';
        
        // Update status text
        let statusText = data.status || 'processing';
        if (statusText === 'downloading') {
            statusText = 'Downloading...';
        } else if (statusText === 'processing') {
            statusText = 'Processing...';
        }
        this.progressStatus.textContent = statusText;
        
        // Update speed info if available
        if (data.speed && data.speed > 0) {
            const speed = this.formatSpeed(data.speed);
            const eta = data.eta ? this.formatTime(data.eta) : '';
            this.progressInfo.textContent = eta ? `${speed} • ${eta} remaining` : speed;
        } else {
            this.progressInfo.textContent = '';
        }
    }
    
    /**
     * Animate percentage number counting up/down
     */
    animatePercentage(targetPercent) {
        const startPercent = this.lastPercent;
        const duration = 300; // Animation duration in ms
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Easing function for smooth animation
            const easeOut = 1 - Math.pow(1 - progress, 3);
            
            const currentPercent = Math.round(startPercent + (targetPercent - startPercent) * easeOut);
            this.progressPercent.textContent = currentPercent;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                this.lastPercent = targetPercent;
            }
        };
        
        requestAnimationFrame(animate);
    }
    
    /**
     * Handle download button click
     */
    handleDownload(e) {
        e.preventDefault();
        if (this.currentTaskId) {
            window.location.href = `/download/${this.currentTaskId}`;
        }
    }
    
    /**
     * Show error message
     */
    showError(message) {
        this.hideAllContainers();
        this.errorContainer.style.display = 'flex';
        this.errorContainer.classList.add('fade-in');
        this.errorMessage.textContent = message;
    }
    
    /**
     * Show progress container
     */
    showProgress() {
        this.hideAllContainers();
        this.progressContainer.style.display = 'block';
        this.progressContainer.classList.add('fade-in');
    }
    
    /**
     * Show result container
     */
    showResult(data) {
        this.hideAllContainers();
        this.resultContainer.style.display = 'block';
        this.resultContainer.classList.add('fade-in');
        this.resultFilename.textContent = data.filename || 'Download ready';
        
        // Update download button href
        this.downloadBtn.href = `/download/${this.currentTaskId}`;
    }
    
    /**
     * Hide all containers
     */
    hideAllContainers() {
        this.progressContainer.style.display = 'none';
        this.errorContainer.style.display = 'none';
        this.resultContainer.style.display = 'none';
    }
    
    /**
     * Reset UI to initial state
     */
    resetUI() {
        this.hideAllContainers();
        this.progressFill.style.width = '0%';
        this.progressStatus.textContent = 'Preparing...';
        this.progressPercent.textContent = '0';
        this.progressInfo.textContent = '';
        this.lastPercent = 0;
        this.currentTaskId = null;
        this.stopPolling();
    }
    
    /**
     * Set loading state for submit button
     */
    setLoadingState(loading) {
        const btnText = this.submitBtn.querySelector('.btn-text');
        const btnLoader = this.submitBtn.querySelector('.btn-loader');
        
        if (loading) {
            btnText.style.display = 'none';
            btnLoader.style.display = 'flex';
            this.submitBtn.disabled = true;
        } else {
            btnText.style.display = 'inline';
            btnLoader.style.display = 'none';
            this.submitBtn.disabled = false;
        }
    }
    
    /**
     * Validate YouTube URL
     */
    isValidYouTubeUrl(url) {
        if (!url || !url.trim()) return false;
        
        const patterns = [
            /^https?:\/\/(www\.)?youtube\.com\/watch\?v=[\w-]+/,
            /^https?:\/\/youtu\.be\/[\w-]+/,
            /^https?:\/\/(www\.)?youtube\.com\/shorts\/[\w-]+/,
            /^https?:\/\/(www\.)?youtube\.com\/embed\/[\w-]+/
        ];
        
        return patterns.some(pattern => pattern.test(url));
    }
    
    /**
     * Format speed from bytes/second
     */
    formatSpeed(bytesPerSecond) {
        if (!bytesPerSecond) return '0 B/s';
        
        const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
        let unitIndex = 0;
        let speed = bytesPerSecond;
        
        while (speed >= 1024 && unitIndex < units.length - 1) {
            speed /= 1024;
            unitIndex++;
        }
        
        return speed.toFixed(1) + ' ' + units[unitIndex];
    }
    
    /**
     * Format time in seconds to readable string
     */
    formatTime(seconds) {
        if (!seconds || seconds < 0) return '0s';
        
        if (seconds < 60) {
            return Math.ceil(seconds) + 's';
        } else if (seconds < 3600) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.ceil(seconds % 60);
            return mins + 'm ' + secs + 's';
        } else {
            const hours = Math.floor(seconds / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            return hours + 'h ' + mins + 'm';
        }
    }
}

// Initialize the downloader when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new YouTubeDownloader();
});
