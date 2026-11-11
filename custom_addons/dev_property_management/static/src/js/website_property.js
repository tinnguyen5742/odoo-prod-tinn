/**
 * Property Website JavaScript
 * Handles interactions, animations, and AJAX functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // ==========================================
    // Smooth Scroll
    // ==========================================
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href === '#') return;
            
            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // ==========================================
    // Search Tab Toggle
    // ==========================================
    const searchTabs = document.querySelectorAll('.search-tab');
    const purposeInput = document.getElementById('searchPurpose');
    
    if (searchTabs.length && purposeInput) {
        searchTabs.forEach(tab => {
            tab.addEventListener('click', function() {
                searchTabs.forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                purposeInput.value = this.getAttribute('data-purpose');
            });
        });
    }

    // ==========================================
    // Mobile Filter Toggle
    // ==========================================
    const filtersSidebar = document.getElementById('filtersSidebar');
    const filterOverlay = document.getElementById('filterOverlay');
    const mobileFilterBtns = document.querySelectorAll('.mobile-filter-btn');
    
    if (filtersSidebar && filterOverlay) {
        mobileFilterBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                filtersSidebar.classList.toggle('active');
                filterOverlay.classList.toggle('active');
                document.body.style.overflow = filtersSidebar.classList.contains('active') ? 'hidden' : '';
            });
        });
        
        filterOverlay.addEventListener('click', function() {
            filtersSidebar.classList.remove('active');
            filterOverlay.classList.remove('active');
            document.body.style.overflow = '';
        });
    }

    // ==========================================
    // Property Card Wishlist Toggle
    // ==========================================
    document.querySelectorAll('.property-card-wishlist').forEach(wishlist => {
        wishlist.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            this.classList.toggle('active');
            
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-heart-o');
                icon.classList.toggle('fa-heart');
            }
        });
    });

    // ==========================================
    // Image Gallery
    // ==========================================
    const galleryMain = document.getElementById('galleryMain');
    const mainImage = document.getElementById('mainImage');
    const galleryThumbs = document.querySelectorAll('.gallery-thumb');
    
    if (galleryMain && mainImage && galleryThumbs.length) {
        let images = [];
        let currentIndex = 0;
        
        galleryThumbs.forEach((thumb, index) => {
            const src = thumb.getAttribute('data-src');
            if (src) {
                images.push(src);
            }
            
            thumb.addEventListener('click', function() {
                const newSrc = this.getAttribute('data-src');
                if (newSrc) {
                    mainImage.src = newSrc;
                    currentIndex = index;
                    
                    galleryThumbs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                }
            });
        });
        
        // Expose functions globally for inline onclick handlers
        window.setMainImage = function(element) {
            const src = element.getAttribute('data-src');
            if (src && mainImage) {
                mainImage.src = src;
                
                galleryThumbs.forEach((t, i) => {
                    t.classList.remove('active');
                    if (t.getAttribute('data-src') === src) {
                        currentIndex = i;
                    }
                });
                element.classList.add('active');
            }
        };
        
        window.changeGalleryImage = function(direction) {
            if (images.length === 0) return;
            
            currentIndex += direction;
            if (currentIndex < 0) currentIndex = images.length - 1;
            if (currentIndex >= images.length) currentIndex = 0;
            
            mainImage.src = images[currentIndex];
            
            galleryThumbs.forEach((t, i) => {
                t.classList.toggle('active', i === currentIndex);
            });
        };
        
        // Keyboard navigation
        document.addEventListener('keydown', function(e) {
            if (e.key === 'ArrowLeft') {
                window.changeGalleryImage(-1);
            } else if (e.key === 'ArrowRight') {
                window.changeGalleryImage(1);
            }
        });
    }

    // ==========================================
    // Filter Form Auto Submit
    // ==========================================
    const filterForm = document.getElementById('filterForm');
    if (filterForm) {
        const selects = filterForm.querySelectorAll('select');
        selects.forEach(select => {
            select.addEventListener('change', function() {
                // Optional: Auto-submit on select change
                // filterForm.submit();
            });
        });
    }

    // ==========================================
    // Scroll to Top Button
    // ==========================================
    const scrollTopBtn = document.createElement('button');
    scrollTopBtn.innerHTML = '<i class="fa fa-arrow-up"></i>';
    scrollTopBtn.className = 'scroll-top-btn';
    scrollTopBtn.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: var(--primary-color, #0078db);
        color: white;
        border: none;
        cursor: pointer;
        opacity: 0;
        visibility: hidden;
        transition: all 0.3s ease;
        z-index: 999;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    document.body.appendChild(scrollTopBtn);
    
    scrollTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
    
    window.addEventListener('scroll', function() {
        if (window.pageYOffset > 300) {
            scrollTopBtn.style.opacity = '1';
            scrollTopBtn.style.visibility = 'visible';
        } else {
            scrollTopBtn.style.opacity = '0';
            scrollTopBtn.style.visibility = 'hidden';
        }
    });

    // ==========================================
    // Lazy Load Images
    // ==========================================
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    if (img.dataset.src) {
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                    }
                    observer.unobserve(img);
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }

    // ==========================================
    // Animate on Scroll
    // ==========================================
    if ('IntersectionObserver' in window) {
        const animateObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('fade-in');
                }
            });
        }, {
            threshold: 0.1
        });
        
        document.querySelectorAll('.property-card, .category-card').forEach(el => {
            animateObserver.observe(el);
        });
    }

    // ==========================================
    // Price Formatting
    // ==========================================
    window.formatPrice = function(price) {
        if (price >= 10000000) {
            return '₹' + (price / 10000000).toFixed(2) + ' Cr';
        } else if (price >= 100000) {
            return '₹' + (price / 100000).toFixed(2) + ' Lac';
        } else {
            return '₹' + price.toLocaleString('en-IN');
        }
    };

    // ==========================================
    // Form Validation
    // ==========================================
    const contactForms = document.querySelectorAll('.contact-form');
    contactForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            let isValid = true;
            const requiredFields = this.querySelectorAll('[required]');
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    isValid = false;
                    field.style.borderColor = '#dc3545';
                    
                    // Remove error style on input
                    field.addEventListener('input', function() {
                        this.style.borderColor = '';
                    }, { once: true });
                }
            });
            
            // Email validation
            const emailField = this.querySelector('input[type="email"]');
            if (emailField && emailField.value) {
                const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailPattern.test(emailField.value)) {
                    isValid = false;
                    emailField.style.borderColor = '#dc3545';
                }
            }
            
            if (!isValid) {
                e.preventDefault();
            }
        });
    });

    // ==========================================
    // View Toggle (Grid/List)
    // ==========================================
    const viewBtns = document.querySelectorAll('.view-btn');
    const propertyGrid = document.querySelector('.property-grid');
    
    if (viewBtns.length && propertyGrid) {
        viewBtns.forEach(btn => {
            btn.addEventListener('click', function() {
                viewBtns.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                const view = this.getAttribute('data-view');
                if (view === 'list') {
                    propertyGrid.style.gridTemplateColumns = '1fr';
                } else {
                    propertyGrid.style.gridTemplateColumns = '';
                }
            });
        });
    }

    // ==========================================
    // Number Counter Animation
    // ==========================================
    function animateCounter(element, target, duration = 2000) {
        let start = 0;
        const increment = target / (duration / 16);
        
        function updateCounter() {
            start += increment;
            if (start < target) {
                element.textContent = Math.floor(start).toLocaleString('en-IN');
                requestAnimationFrame(updateCounter);
            } else {
                element.textContent = target.toLocaleString('en-IN');
            }
        }
        
        updateCounter();
    }

    // ==========================================
    // Sticky Header
    // ==========================================
    const header = document.querySelector('.o_header_standard, header');
    if (header) {
        let lastScrollTop = 0;
        
        window.addEventListener('scroll', function() {
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
            
            if (scrollTop > 100) {
                header.classList.add('scrolled');
            } else {
                header.classList.remove('scrolled');
            }
            
            lastScrollTop = scrollTop;
        });
    }

    // ==========================================
    // Print Property
    // ==========================================
    window.printProperty = function() {
        window.print();
    };

    // ==========================================
    // Copy Share Link
    // ==========================================
    window.copyShareLink = function() {
        const url = window.location.href;
        
        if (navigator.clipboard) {
            navigator.clipboard.writeText(url).then(() => {
                alert('Link copied to clipboard!');
            });
        } else {
            // Fallback
            const input = document.createElement('input');
            input.value = url;
            document.body.appendChild(input);
            input.select();
            document.execCommand('copy');
            document.body.removeChild(input);
            alert('Link copied to clipboard!');
        }
    };

    // ==========================================
    // Initialize
    // ==========================================
    console.log('Property Website JavaScript loaded successfully');
});

// ==========================================
// AJAX Property Search (for future use)
// ==========================================
class PropertySearch {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/properties/api/search';
        this.container = options.container;
        this.filters = options.filters || {};
    }
    
    async search(params = {}) {
        try {
            const response = await fetch(this.apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: { ...this.filters, ...params }
                })
            });
            
            const data = await response.json();
            return data.result;
        } catch (error) {
            console.error('Search error:', error);
            return { success: false, error: error.message };
        }
    }
    
    renderProperties(properties) {
        if (!this.container) return;
        
        const html = properties.map(prop => this.renderPropertyCard(prop)).join('');
        this.container.innerHTML = html;
    }
    
    renderPropertyCard(property) {
        const price = property.property_purpose === 'sell' 
            ? property.price_amount 
            : property.rent_amount;
        
        return `
            <div class="property-card">
                <a href="/properties/detail/${property.id}">
                    <div class="property-card-image">
                        <img src="${property.image_url}" alt="${property.name}"/>
                        <div class="property-card-badges">
                            <span class="property-badge ${property.property_purpose === 'sell' ? 'badge-sale' : 'badge-rent'}">
                                ${property.property_purpose === 'sell' ? 'For Sale' : 'For Rent'}
                            </span>
                        </div>
                    </div>
                    <div class="property-card-content">
                        <div class="property-card-price">
                            ${window.formatPrice ? window.formatPrice(price) : '₹' + price.toLocaleString('en-IN')}
                            ${property.property_purpose === 'rent' ? '<span>/month</span>' : ''}
                        </div>
                        <h3 class="property-card-title">${property.name}</h3>
                        <div class="property-card-location">
                            <i class="fa fa-map-marker"></i>
                            <span>${property.street || ''} ${property.city ? ', ' + property.city : ''}</span>
                        </div>
                        <div class="property-card-features">
                            ${property.bedroom ? `<div class="property-feature"><i class="fa fa-bed"></i><span>${property.bedroom} Beds</span></div>` : ''}
                            ${property.bathroom ? `<div class="property-feature"><i class="fa fa-bath"></i><span>${property.bathroom} Baths</span></div>` : ''}
                        </div>
                    </div>
                </a>
            </div>
        `;
    }
}

// Export for use
window.PropertySearch = PropertySearch;
