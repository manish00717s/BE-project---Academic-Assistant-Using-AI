// File: static/js/main.js

// Global variables
let currentPage = 1;
const rowsPerPage = 20;
let sortDirection = 'asc';
let currentSortColumn = -1;

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

// Main initialization function
function initializeApp() {
    // Initialize common components
    initializeAnimations();
    initializeFormValidation();
    initializeTooltips();
    initializeModals();
    
    // Page-specific initializations
    const currentPage = getCurrentPage();
    
    switch(currentPage) {
        case 'upload_video':
            initializeVideoUpload();
            break;
        case 'manage_students':
            initializeStudentManagement();
            break;
        case 'attendance_report':
            initializeReports();
            break;
        case 'dashboard':
            initializeDashboard();
            break;
    }
}

// Get current page from URL or body class
function getCurrentPage() {
    const path = window.location.pathname;
    if (path.includes('upload_video')) return 'upload_video';
    if (path.includes('manage_students')) return 'manage_students';
    if (path.includes('attendance_report')) return 'attendance_report';
    if (path.includes('dashboard')) return 'dashboard';
    return 'general';
}

// Initialize animations
function initializeAnimations() {
    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('fade-in');
    });
    
    // Add hover effects to buttons
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px) scale(1.05)';
        });
        
        button.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
    });
}

// Initialize form validation
function initializeFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
                showNotification('Please fill in all required fields correctly.', 'error');
            }
        });
        
        // Add real-time validation
        const inputs = form.querySelectorAll('input[required], select[required], textarea[required]');
        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                validateField(this);
            });
            
            input.addEventListener('input', function() {
                clearFieldError(this);
            });
        });
    });
}

// Validate individual form
function validateForm(form) {
    let isValid = true;
    const requiredFields = form.querySelectorAll('input[required], select[required], textarea[required]');
    
    requiredFields.forEach(field => {
        if (!validateField(field)) {
            isValid = false;
        }
    });
    
    return isValid;
}

// Validate individual field
function validateField(field) {
    const value = field.value.trim();
    const fieldName = field.name;
    let isValid = true;
    let errorMessage = '';
    
    // Check if field is empty
    if (!value && field.hasAttribute('required')) {
        isValid = false;
        errorMessage = 'This field is required.';
    }
    
    // Specific validation rules
    switch(field.type) {
        case 'email':
            if (value && !isValidEmail(value)) {
                isValid = false;
                errorMessage = 'Please enter a valid email address.';
            }
            break;
        case 'file':
            if (field.hasAttribute('required') && field.files.length === 0) {
                isValid = false;
                errorMessage = 'Please select a file.';
            }
            break;
    }
    
    // Student ID validation
    if (fieldName === 'student_id' && value) {
        if (!/^[A-Z]{3}\d{3}$/.test(value)) {
            isValid = false;
            errorMessage = 'Student ID should be in format: ABC123';
        }
    }
    
    // Display validation result
    if (!isValid) {
        showFieldError(field, errorMessage);
    } else {
        clearFieldError(field);
    }
    
    return isValid;
}

// Show field error
function showFieldError(field, message) {
    clearFieldError(field);
    
    field.classList.add('is-invalid');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    
    field.parentNode.appendChild(errorDiv);
}

// Clear field error
function clearFieldError(field) {
    field.classList.remove('is-invalid');
    
    const errorDiv = field.parentNode.querySelector('.invalid-feedback');
    if (errorDiv) {
        errorDiv.remove();
    }
}

// Email validation
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// Initialize tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize modals
function initializeModals() {
    // Add modal functionality if needed
    const modalTriggers = document.querySelectorAll('[data-bs-toggle="modal"]');
    modalTriggers.forEach(trigger => {
        trigger.addEventListener('click', function() {
            const targetModal = document.querySelector(this.getAttribute('data-bs-target'));
            if (targetModal) {
                const modal = new bootstrap.Modal(targetModal);
                modal.show();
            }
        });
    });
}

// Video Upload Page Functions
function initializeVideoUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const videoInput = document.getElementById('videoInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const videoPreview = document.getElementById('videoPreview');
    const previewVideo = document.getElementById('previewVideo');
    const submitBtn = document.getElementById('submitBtn');
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');

    if (!uploadArea) return;

    // Drag and drop functionality
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    uploadArea.addEventListener('click', () => videoInput.click());

    // File input change
    videoInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            handleFileSelect(this.files[0]);
        }
    });

    // Form submission
    uploadForm.addEventListener('submit', function(e) {
        if (videoInput.files.length === 0) {
            e.preventDefault();
            showNotification('Please select a video file first.', 'error');
            return;
        }
        
        showUploadProgress();
        simulateUploadProgress();
    });

    function handleDragOver(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    }

    function handleDragLeave(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    }

    function handleDrop(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const file = files[0];
            if (isValidVideoFile(file)) {
                videoInput.files = files;
                handleFileSelect(file);
            } else {
                showNotification('Please select a valid video file (MP4, AVI, MOV, MKV).', 'error');
            }
        }
    }

    function handleFileSelect(file) {
        // Validate file
        if (!isValidVideoFile(file)) {
            showNotification('Invalid file type. Please select a video file.', 'error');
            return;
        }

        if (file.size > 100 * 1024 * 1024) { // 100MB
            showNotification('File size too large. Maximum size is 100MB.', 'error');
            return;
        }

        // Display file info
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.style.display = 'block';
        
        // Show video preview
        const videoURL = URL.createObjectURL(file);
        previewVideo.src = videoURL;
        videoPreview.style.display = 'block';
        
        // Enable submit button
        submitBtn.disabled = false;
        
        showNotification('Video file selected successfully!', 'success');
    }

    function isValidVideoFile(file) {
        const validTypes = ['video/mp4', 'video/avi', 'video/mov', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'];
        return validTypes.includes(file.type) || /\.(mp4|avi|mov|mkv)$/i.test(file.name);
    }

    function showUploadProgress() {
        uploadProgress.style.display = 'block';
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
    }

    function simulateUploadProgress() {
        const progressBar = uploadProgress.querySelector('.progress-bar');
        let progress = 0;
        
        const interval = setInterval(() => {
            progress += Math.random() * 10;
            if (progress > 100) progress = 100;
            
            progressBar.style.width = progress + '%';
            progressBar.setAttribute('aria-valuenow', progress);
            
            if (progress >= 100) {
                clearInterval(interval);
            }
        }, 500);
    }
}

// Student Management Page Functions
function initializeStudentManagement() {
    const photoUploadArea = document.getElementById('photoUploadArea');
    const photoInput = document.getElementById('photo');
    const photoPreview = document.getElementById('photoPreview');
    const previewImg = document.getElementById('previewImg');
    const resetBtn = document.getElementById('resetBtn');
    const searchInput = document.getElementById('searchInput');

    if (!photoUploadArea) return;

    // Photo upload functionality
    photoUploadArea.addEventListener('click', () => photoInput.click());

    photoInput.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            const file = this.files[0];
            
            if (!isValidImageFile(file)) {
                showNotification('Please select a valid image file (JPG, PNG, JPEG).', 'error');
                return;
            }
            
            const reader = new FileReader();
            reader.onload = function(e) {
                previewImg.src = e.target.result;
                photoPreview.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }
    });

    // Reset form
    if (resetBtn) {
        resetBtn.addEventListener('click', function() {
            photoPreview.style.display = 'none';
            previewImg.src = '';
        });
    }

    // Search functionality
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            const searchTerm = this.value.toLowerCase();
            const studentItems = document.querySelectorAll('.student-item');
            
            studentItems.forEach(function(item) {
                const name = item.dataset.name || '';
                const id = item.dataset.id || '';
                const classSection = item.dataset.class || '';
                
                if (name.includes(searchTerm) || id.includes(searchTerm) || classSection.includes(searchTerm)) {
                    item.style.display = 'block';
                    item.classList.add('fade-in');
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }

    function isValidImageFile(file) {
        const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp'];
        return validTypes.includes(file.type);
    }
}

// Reports Page Functions
function initializeReports() {
    initializeTableSorting();
    initializePagination();
    initializeExportFunctions();
    initializeDateFilters();
}

// Table sorting functionality
function initializeTableSorting() {
    const table = document.getElementById('attendanceTable');
    if (!table) return;

    const headers = table.querySelectorAll('th[onclick]');
    headers.forEach((header, index) => {
        header.addEventListener('click', () => sortTable(index));
        header.style.cursor = 'pointer';
    });
}

function sortTable(columnIndex) {
    const table = document.getElementById('attendanceTable');
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows);
    
    // Toggle sort direction
    if (currentSortColumn === columnIndex) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortDirection = 'asc';
        currentSortColumn = columnIndex;
    }
    
    // Sort rows
    rows.sort((a, b) => {
        const cellA = a.cells[columnIndex].textContent.trim();
        const cellB = b.cells[columnIndex].textContent.trim();
        
        let comparison = 0;
        
        // Check if values are dates
        if (isDate(cellA) && isDate(cellB)) {
            comparison = new Date(cellA) - new Date(cellB);
        } else if (isNumeric(cellA) && isNumeric(cellB)) {
            comparison = parseFloat(cellA) - parseFloat(cellB);
        } else {
            comparison = cellA.localeCompare(cellB);
        }
        
        return sortDirection === 'asc' ? comparison : -comparison;
    });
    
    // Re-append sorted rows
    rows.forEach(row => tbody.appendChild(row));
    
    // Update sort indicators
    updateSortIndicators(columnIndex);
}

function updateSortIndicators(columnIndex) {
    const headers = document.querySelectorAll('#attendanceTable th[onclick]');
    
    headers.forEach((header, index) => {
        const icon = header.querySelector('i');
        if (icon) {
            if (index === columnIndex) {
                icon.className = sortDirection === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down';
            } else {
                icon.className = 'fas fa-sort';
            }
        }
    });
}

// Pagination functionality
function initializePagination() {
    const table = document.getElementById('attendanceTable');
    if (!table) return;

    showPage(1);
    updatePaginationInfo();
}

function showPage(page) {
    const table = document.getElementById('attendanceTable');
    const tbody = table.tBodies[0];
    const rows = tbody.rows;
    const startIndex = (page - 1) * rowsPerPage;
    const endIndex = startIndex + rowsPerPage;
    
    for (let i = 0; i < rows.length; i++) {
        if (i >= startIndex && i < endIndex) {
            rows[i].style.display = '';
        } else {
            rows[i].style.display = 'none';
        }
    }
    
    currentPage = page;
    updatePaginationInfo();
}

function updatePaginationInfo() {
    const currentPageElement = document.getElementById('currentPage');
    if (currentPageElement) {
        currentPageElement.textContent = currentPage;
    }
}

function previousPage() {
    if (currentPage > 1) {
        showPage(currentPage - 1);
    }
}

function nextPage() {
    const table = document.getElementById('attendanceTable');
    const tbody = table.tBodies[0];
    const totalPages = Math.ceil(tbody.rows.length / rowsPerPage);
    
    if (currentPage < totalPages) {
        showPage(currentPage + 1);
    }
}

// Export functions
function initializeExportFunctions() {
    // These functions would integrate with backend APIs
    window.exportToExcel = function() {
        showNotification('Preparing Excel export...', 'info');
        // Implementation would call backend API
        setTimeout(() => {
            showNotification('Excel export feature coming soon!', 'warning');
        }, 1000);
    };

    window.exportToPDF = function() {
        showNotification('Preparing PDF export...', 'info');
        // Implementation would use jsPDF or similar
        setTimeout(() => {
            showNotification('PDF export feature coming soon!', 'warning');
        }, 1000);
    };

    window.sendEmail = function() {
        showNotification('Preparing email...', 'info');
        // Implementation would call backend email service
        setTimeout(() => {
            showNotification('Email feature coming soon!', 'warning');
        }, 1000);
    };
}

// Date filter functionality
function initializeDateFilters() {
    const startDateInput = document.getElementById('start_date');
    const endDateInput = document.getElementById('end_date');
    
    if (startDateInput && endDateInput) {
        // Set default dates if empty
        if (!startDateInput.value) {
            startDateInput.value = getCurrentDate();
        }
        if (!endDateInput.value) {
            endDateInput.value = getCurrentDate();
        }
        
        // Add validation
        startDateInput.addEventListener('change', validateDateRange);
        endDateInput.addEventListener('change', validateDateRange);
    }
}

function validateDateRange() {
    const startDate = document.getElementById('start_date').value;
    const endDate = document.getElementById('end_date').value;
    
    if (startDate && endDate && startDate > endDate) {
        showNotification('Start date cannot be later than end date.', 'error');
        document.getElementById('end_date').value = startDate;
    }
}

// Dashboard Functions
function initializeDashboard() {
    initializeStatCards();
    initializeQuickActions();
    refreshDashboardData();
}

function initializeStatCards() {
    const statCards = document.querySelectorAll('.card .fa-3x');
    
    statCards.forEach((icon, index) => {
        setTimeout(() => {
            icon.classList.add('pulse');
        }, index * 200);
    });
}

function initializeQuickActions() {
    const quickActionBtns = document.querySelectorAll('.card-body .btn');
    
    quickActionBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // Add click animation
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = 'scale(1)';
            }, 150);
        });
    });
}

function refreshDashboardData() {
    // This would typically fetch fresh data from the server
    // For now, we'll just add some visual feedback
    const statNumbers = document.querySelectorAll('.card h4');
    
    statNumbers.forEach(number => {
        number.style.transition = 'all 0.3s ease';
        number.style.transform = 'scale(1.1)';
        
        setTimeout(() => {
            number.style.transform = 'scale(1)';
        }, 300);
    });
}

// Utility Functions
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function getCurrentDate() {
    const today = new Date();
    return today.toISOString().split('T')[0];
}

function isDate(value) {
    return !isNaN(Date.parse(value));
}

function isNumeric(value) {
    return !isNaN(parseFloat(value)) && isFinite(value);
}

// Notification system
function showNotification(message, type = 'info', duration = 5000) {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.notification-toast');
    existingNotifications.forEach(notification => notification.remove());
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} notification-toast`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        animation: slideInRight 0.3s ease-out;
    `;
    
    notification.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-${getNotificationIcon(type)} me-2"></i>
            <span>${message}</span>
            <button type="button" class="btn-close ms-auto" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto remove after duration
    setTimeout(() => {
        if (notification.parentElement) {
            notification.style.animation = 'slideOutRight 0.3s ease-in';
            setTimeout(() => notification.remove(), 300);
        }
    }, duration);
}

function getNotificationIcon(type) {
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

// Student management functions (called from templates)
function editStudent(studentId) {
    showNotification('Edit student functionality would be implemented here.', 'info');
    // In a real application, this would open an edit modal or redirect to edit page
}

function deleteStudent(studentId, studentName) {
    if (confirm(`Are you sure you want to delete ${studentName}? This action cannot be undone.`)) {
        // In a real application, this would make an API call to delete the student
        showNotification('Delete student functionality would be implemented here.', 'warning');
    }
}

function viewVideo(filename) {
    showNotification('Video viewer functionality would be implemented here.', 'info');
    // In a real application, this would open a modal with the video player
}

// Add CSS animations for notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
    
    .notification-toast {
        animation: slideInRight 0.3s ease-out !important;
    }
`;
document.head.appendChild(style);

// Global error handler
window.addEventListener('error', function(e) {
    console.error('JavaScript Error:', e.error);
    showNotification('An unexpected error occurred. Please refresh the page.', 'error');
});
 
// Service worker registration (for offline functionality)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/js/sw.js')
        .then(function(registration) {
            console.log('ServiceWorker registration successful');
        })
        .catch(function(err) {
            console.log('ServiceWorker registration failed');
        });
    });
}