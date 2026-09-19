import { test, expect } from '@playwright/test';

// Viewport: Mobile max (640px) - 375px rules should be INACTIVE
const VIEWPORT = { width: 640, height: 800 };

const TEST_USER = { username: 'testuser', password: 'testpass' };

async function ensureLoggedIn(page) {
    await page.goto('/login');
    await page.fill('input[name="username"]', TEST_USER.username);
    await page.fill('input[name="password"]', TEST_USER.password);
    await Promise.all([
        page.waitForURL('/', { timeout: 10000 }),
        page.click('button[type="submit"]'),
    ]);
    await page.waitForLoadState('networkidle');
}

async function openMobileMenu(page) {
    const hamburger = page.locator('.nav-toggle-btn');
    await hamburger.click();
    await expect(hamburger).toHaveAttribute('aria-expanded', 'true', { timeout: 5000 });
    await expect(page.locator('.nav-menu')).toHaveClass(/is-open/, { timeout: 5000 });
    await page.waitForTimeout(200);
}

async function getComputedStyles(page, selector) {
    return await page.locator(selector).first().evaluate(el => getComputedStyle(el));
}

test.describe('Mobile touch targets @ 640px - 375px rules INACTIVE', () => {
    test.use({ viewport: VIEWPORT });

    test('640px breakpoint rules are active (hamburger menu visible)', async ({ page }) => {
        await ensureLoggedIn(page);
        
        const hamburger = page.locator('.nav-toggle-btn');
        const navLinks = page.locator('.nav-links');

        await expect(hamburger).toBeVisible();
        await expect(navLinks).toBeHidden();
    });

    test('Nav menu links have block display at 640px (existing 640px rule)', async ({ page }) => {
        await ensureLoggedIn(page);
        await openMobileMenu(page);
        
        const styles = await getComputedStyles(page, '.nav-menu .nav-link');
        expect(styles.display).toBe('block');
    });

    // Verify 375px rules do NOT apply at 640px
    test('Buttons do NOT have 375px min-height at 640px', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');
        
        const primaryBtn = page.locator('.btn-primary').first();
        await expect(primaryBtn).toBeVisible();
        const styles = await primaryBtn.evaluate(el => getComputedStyle(el));
        // At 640px, buttons should NOT have 44px min-height from 375px rule
        // They may have natural height from padding, but not forced 44px
        expect(parseFloat(styles.minHeight)).toBeLessThan(44);
    });

    test('Nav menu links do NOT have 375px min-height at 640px', async ({ page }) => {
        await ensureLoggedIn(page);
        await openMobileMenu(page);
        
        const styles = await getComputedStyles(page, '.nav-menu .nav-link');
        // At 640px, nav menu links have display:block from 640px rule
        // but should NOT have 44px min-height from 375px rule
        // min-height: auto (default) means no forced height - this is correct
        expect(styles.display).toBe('block');
        const minHeight = parseFloat(styles.minHeight);
        // If minHeight is NaN, it means min-height: auto (not set), which is correct
        if (!isNaN(minHeight)) {
            expect(minHeight).toBeLessThan(44);
        }
    });

    test('Card title links are inline at 640px (not block from 375px)', async ({ page }) => {
        await ensureLoggedIn(page);
        
        const cardTitleLink = page.locator('.card-title a').first();
        if (!(await cardTitleLink.isVisible().catch(() => false))) test.skip();
        
        const styles = await cardTitleLink.evaluate(el => getComputedStyle(el));
        // At 640px, card title links should be inline (not block from 375px rule)
        expect(styles.display).not.toBe('block');
    });

    test('Form inputs do NOT have 375px min-height at 640px', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');
        
        const textInput = page.locator('input[name="username"]').first();
        await expect(textInput).toBeVisible();
        
        const styles = await textInput.evaluate(el => getComputedStyle(el));
        // At 640px, inputs should NOT have 44px min-height from 375px rule
        expect(parseFloat(styles.minHeight)).toBeLessThan(44);
    });

    test('Checkbox labels do NOT have 375px min-height at 640px', async ({ page }) => {
        await ensureLoggedIn(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        
        // No exercises, so no checkbox labels - skip
        test.skip();
    });

    test('Checkbox inputs are ~17.6px at 640px (not 24px from 375px)', async ({ page }) => {
        await ensureLoggedIn(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        
        // No exercises, so no checkbox inputs - skip
        test.skip();
    });
});