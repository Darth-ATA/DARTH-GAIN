import { test, expect } from '@playwright/test';

// Viewport: iPhone 12 mini (375px)
const VIEWPORT = { width: 375, height: 667 };

const TEST_USER = { username: 'testuser', password: 'testpass' };

// Helper to ensure test user exists and login
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

// Helper to open mobile menu
async function openMobileMenu(page) {
    const hamburger = page.locator('.nav-toggle-btn');
    await hamburger.click();
    await expect(hamburger).toHaveAttribute('aria-expanded', 'true', { timeout: 5000 });
    await expect(page.locator('.nav-menu')).toHaveClass(/is-open/, { timeout: 5000 });
    await page.waitForTimeout(200);
}

// Helper to go to first exercise detail page
async function goToFirstExerciseDetail(page) {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    const firstCardLink = page.locator('.card-title a').first();
    if (await firstCardLink.isVisible().catch(() => false)) {
        await firstCardLink.click();
        await page.waitForURL(/\/exercises\//, { timeout: 10000 });
        await page.waitForLoadState('networkidle');
        return true;
    }
    return false;
}

// Helper to check if dashboard has exercises
async function dashboardHasExercises(page) {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    return await page.locator('.card-title a').first().isVisible().catch(() => false);
}

// Helper to get computed styles for an element (even if not visible)
async function getComputedStyles(page, selector) {
    return await page.locator(selector).first().evaluate(el => getComputedStyle(el));
}

test.describe('Mobile touch targets @ 375px', () => {
    test.use({ viewport: VIEWPORT });

    // Test 1: Primary button (on login page - Login button)
    test('Primary button meets touch target requirements', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');
        
        const primaryBtn = page.locator('.btn-primary').first();
        await expect(primaryBtn).toBeVisible();
        const styles = await primaryBtn.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 2: Secondary button (on exercise detail)
    test('Secondary button meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const secondaryBtn = page.locator('.btn-secondary').first();
        if (!(await secondaryBtn.isVisible().catch(() => false))) test.skip();
        
        await expect(secondaryBtn).toBeVisible();
        const styles = await secondaryBtn.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 3: Small button (on exercise detail)
    test('Small button meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const smallBtn = page.locator('.btn-sm').first();
        if (!(await smallBtn.isVisible().catch(() => false))) test.skip();
        
        await expect(smallBtn).toBeVisible();
        const styles = await smallBtn.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 4: Nav link (base) - in mobile menu when open (check computed styles)
    test('Nav link (base) meets touch target requirements', async ({ page }) => {
        await ensureLoggedIn(page);
        await openMobileMenu(page);
        
        // Get computed styles even if Playwright doesn't consider it "visible"
        const styles = await getComputedStyles(page, '.nav-menu .nav-link');
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
        expect(styles.display).toBe('block');
    });

    // Test 5: Nav menu link (check computed styles)
    test('Nav menu link meets touch target requirements', async ({ page }) => {
        await ensureLoggedIn(page);
        await openMobileMenu(page);
        
        const styles = await getComputedStyles(page, '.nav-menu .nav-link');
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
        expect(styles.display).toBe('block');
    });

    // Test 6: Card title link (on dashboard - only if exercises exist)
    test('Card title link meets touch target requirements', async ({ page }) => {
        const hasExercises = await dashboardHasExercises(page);
        if (!hasExercises) test.skip();
        
        const cardTitleLink = page.locator('.card-title a').first();
        await expect(cardTitleLink).toBeVisible();
        const styles = await cardTitleLink.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
        expect(styles.display).toBe('block');
    });

    // Test 7: Back link (on exercise detail)
    test('Back link meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const backLink = page.locator('.back-link').first();
        await expect(backLink).toBeVisible();
        
        const styles = await backLink.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
        expect(styles.display).toBe('inline-flex');
    });

    // Test 8: Details summary (on exercise detail)
    test('Details summary meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const detailsSummary = page.locator('details summary').first();
        if (!(await detailsSummary.isVisible().catch(() => false))) test.skip();
        
        await expect(detailsSummary).toBeVisible();
        const styles = await detailsSummary.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 9: History toggle (on exercise detail)
    test('History toggle meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const historyToggle = page.locator('.history-details-toggle').first();
        if (!(await historyToggle.isVisible().catch(() => false))) test.skip();
        
        await expect(historyToggle).toBeVisible();
        const styles = await historyToggle.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 10: Text input (on login page)
    test('Text input meets touch target requirements', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');
        
        const textInput = page.locator('input[name="username"]').first();
        await expect(textInput).toBeVisible();
        
        const styles = await textInput.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 11: Password input (on login page)
    test('Password input meets touch target requirements', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');
        
        const passwordInput = page.locator('input[name="password"]').first();
        await expect(passwordInput).toBeVisible();
        
        const styles = await passwordInput.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 12: Number input (on exercise detail config form)
    test('Number input meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const numberInput = page.locator('.form-group input[type="number"]').first();
        if (!(await numberInput.isVisible().catch(() => false))) test.skip();
        
        await expect(numberInput).toBeVisible();
        const styles = await numberInput.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
    });

    // Test 13: Checkbox label (on exercise detail config form)
    test('Checkbox label meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const checkboxLabel = page.locator('.checkbox-label').first();
        if (!(await checkboxLabel.isVisible().catch(() => false))) test.skip();
        
        await expect(checkboxLabel).toBeVisible();
        const styles = await checkboxLabel.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.minHeight)).toBeGreaterThanOrEqual(44);
        expect(styles.display).toBe('flex');
        expect(styles.alignItems).toBe('center');
    });

    // Test 14: Checkbox input (on exercise detail config form)
    test('Checkbox input meets touch target requirements', async ({ page }) => {
        const hasExercises = await goToFirstExerciseDetail(page);
        if (!hasExercises) test.skip();
        
        const checkboxInput = page.locator('.checkbox-label input[type="checkbox"]').first();
        if (!(await checkboxInput.isVisible().catch(() => false))) test.skip();
        
        await expect(checkboxInput).toBeVisible();
        const styles = await checkboxInput.evaluate(el => getComputedStyle(el));
        expect(parseFloat(styles.width)).toBeCloseTo(24, 0);
        expect(parseFloat(styles.height)).toBeCloseTo(24, 0);
    });

    // Focus state verification at 375px
    test('Focus visible on all interactive elements at 375px', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');

        await page.keyboard.press('Tab');
        const focusedHandle = await page.evaluateHandle(() => document.activeElement);
        const focused = await focusedHandle.asElement();
        
        if (focused) {
            const styles = await focused.evaluate(el => getComputedStyle(el));
            expect(styles.outline).not.toBe('none');
            expect(styles.outlineWidth).not.toBe('0px');
        }
    });

    // Verify no horizontal layout shift on focus at 375px
    test('No horizontal layout shift on input focus at 375px', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');

        const usernameInput = page.locator('input[name="username"]').first();
        const initialBox = await usernameInput.boundingBox();
        
        await usernameInput.focus();
        const focusedBox = await usernameInput.boundingBox();

        // Width should not change on focus (no horizontal shift)
        expect(focusedBox.width).toBeCloseTo(initialBox.width, 1);
    });
});