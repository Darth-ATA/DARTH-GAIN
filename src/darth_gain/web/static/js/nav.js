// nav.js - Navigation module for responsive hamburger menu
// Progressive enhancement: <details>/<summary> fallback → JS enhances with ARIA/focus trap

export function initNavigation() {
  const details = document.getElementById('nav-toggle');
  const summary = details?.querySelector('.nav-toggle-btn');
  const menu = document.getElementById('nav-menu');
  
  if (!details || !summary || !menu) return;
  
  // Suppress native <details> toggle behavior
  summary.addEventListener('click', (e) => {
    e.preventDefault();
    const isOpen = summary.getAttribute('aria-expanded') === 'true';
    if (isOpen) {
      closeMenu(true);
    } else {
      openMenu();
    }
  });
  
  function openMenu() {
    summary.setAttribute('aria-expanded', 'true');
    menu.classList.add('is-open');
  }
  
  function closeMenu(returnFocus = true) {
    summary.setAttribute('aria-expanded', 'false');
    menu.classList.remove('is-open');
    if (returnFocus) {
      summary.focus();
    }
  }
  
  // Focus trap
  const focusableElements = menu.querySelectorAll('a, button, [tabindex]:not([tabindex="-1"])');
  let firstFocusable = focusableElements[0];
  let lastFocusable = focusableElements[focusableElements.length - 1];
  
  function handleKeyDown(e) {
    const isOpen = summary.getAttribute('aria-expanded') === 'true';
    
    if (e.key === 'Tab' && isOpen) {
      if (e.shiftKey) {
        if (document.activeElement === firstFocusable) {
          e.preventDefault();
          lastFocusable.focus();
        }
      } else {
        if (document.activeElement === lastFocusable) {
          e.preventDefault();
          firstFocusable.focus();
        }
      }
    }
    
    if (e.key === 'Escape' && isOpen) {
      closeMenu(true);
    }
  }
  
  // Focus trap on menu (for Tab cycling)
  menu.addEventListener('keydown', handleKeyDown);
  
  // ESC key handler on document (works regardless of focus position)
  document.addEventListener('keydown', handleKeyDown);
  
  function closeMenu(returnFocus = true) {
    summary.setAttribute('aria-expanded', 'false');
    menu.classList.remove('is-open');
    if (returnFocus) {
      summary.focus();
    }
  }
  
  // Close on outside click
  document.addEventListener('click', (e) => {
    if (summary.getAttribute('aria-expanded') === 'true' && 
        !details.contains(e.target)) {
      closeMenu(true);
    }
  });
  
  // Close on link click
  menu.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      closeMenu(true);
    });
  });
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initNavigation);
} else {
  initNavigation();
}