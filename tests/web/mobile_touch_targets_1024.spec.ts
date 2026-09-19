import { test, expect } from '@playwright/test';

// Viewport: Desktop (1024px) - zero regression, 375px rules must not apply
const VIEWPORT = { width: 1024, height: 768 };

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

async function getComputedStyles(page, selector) {
    return await page.locator(selector).first().evaluate(el => getComputedStyle(el));
}

test.describe('Desktop baseline @ 1024px - zero regression', () => {
    test.use({ viewport: VIEWPORT });

    test('Desktop navbar: hamburger is hidden', async ({ page }) => {
        await ensureLoggedIn(page);

        const hamburger = page.locator('.nav-toggle-btn');
        await expect(hamburger).toBeHidden();
    });

    test('Buttons at desktop have original styling (no 44px min-height from 375px)', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');

        const primaryBtn = page.locator('.btn-primary').first();
        const styles = await primaryBtn.evaluate(el => getComputedStyle(el));

        // At desktop, .btn-primary has padding-based height, not 44px min-height
        expect(parseFloat(styles.minHeight)).toBeLessThan(44);
        expect(styles.display).toBe('inline-flex');
    });

    test('Nav links inside .nav-menu at desktop have global block display (existing behavior)', async ({ page }) => {
        await ensureLoggedIn(page);

        // The nav links are inside .nav-menu which is inside <details>
        // At desktop, the menu is not open (no is-open class), so links are hidden
        // But we can verify the 375px rule doesn't ADD block display (it's already global)
        const details = page.locator('details.nav-toggle');
        await details.evaluate(el => el.setAttribute('open', ''));
        
        const navLink = page.locator('.nav-menu .nav-link').first();
        const styles = await navLink.evaluate(el => getComputedStyle(el));

        // .nav-menu .nav-link has display:block GLOBALLY (line 162 in app.css)
        // This is existing behavior, not from 375px rule
        // The 375px rule also sets display:block but it's redundant
        // What matters: 375px rule should NOT add min-height: 44px at desktop
        expect(styles.display).toBe('block');
        const minHeight = parseFloat(styles.minHeight);
        if (!isNaN(minHeight)) {
            expect(minHeight).toBeLessThan(44);
        }
    });

    test('Card title links at desktop are inline (not block)', async ({ page }) => {
        await ensureLoggedIn(page);

        const cardTitleLink = page.locator('.card-title a').first();
        if (!(await cardTitleLink.isVisible().catch(() => false))) test.skip();

        const styles = await cardTitleLink.evaluate(el => getComputedStyle(el));
        expect(styles.display).not.toBe('block');
    });

    test('Form inputs at desktop have original height (no 44px min-height)', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');

        const usernameInput = page.locator('input[name="username"]').first();
        const passwordInput = page.locator('input[name="password"]').first();

        const usernameStyles = await usernameInput.evaluate(el => getComputedStyle(el));
        const passwordStyles = await passwordInput.evaluate(el => getComputedStyle(el));

        expect(parseFloat(usernameStyles.minHeight)).toBeLessThan(44);
        expect(parseFloat(passwordStyles.minHeight)).toBeLessThan(44);
    });

    test('Focus states work at desktop (keyboard accessibility)', async ({ page }) => {
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

    test('No horizontal layout shift on focus at desktop', async ({ page }) => {
        await page.goto('/login');
        await page.waitForLoadState('networkidle');

        const usernameInput = page.locator('input[name="username"]').first();
        const initialBox = await usernameInput.boundingBox();

        await usernameInput.focus();
        const focusedBox = await usernameInput.boundingBox();

        expect(focusedBox.width).toBeCloseTo(initialBox.width, 1);
    });

    test('Details summary at desktop has no 44px min-height', async ({ page }) => {
        await ensureLoggedIn(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        
        // Go to exercise detail if exercises exist
        const firstCardLink = page.locator('.card-title a').first();
        if (await firstCardLink.isVisible().catch(() => false)) {
            await firstCardLink.click();
            await page.waitForURL(/\/exercises\//, { timeout: 10000 });
            await page.waitForLoadState('networkidle');
            
            const detailsSummary = page.locator('details summary').first();
            if (await detailsSummary.isVisible().catch(() => false)) {
                const styles = await detailsSummary.evaluate(el => getComputedStyle(el));
                expect(parseFloat(styles.minHeight)).toBeLessThan(44);
            }
        }
    });

    test('Checkbox inputs at desktop are ~17.6px (not 24px from 375px)', async ({ page }) => {
        await ensureLoggedIn(page);
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        
        const firstCardLink = page.locator('.card-title a').first();
        if (await firstCardLink.isVisible().catch(() => false)) {
            await firstCardLink.click();
            await page.waitForURL(/\/exercises\//, { timeout: 10000 });
            await page.waitForLoadState('networkidle');
            
            const checkboxInput = page.locator('.checkbox-label input[type="checkbox"]').first();
            if (await checkboxInput.isVisible().catch(() => false)) {
                const styles = await checkboxInput.evaluate(el => getComputedStyle(el));
                expect(parseFloat(styles.width)).toBeCloseTo(17.6, 1);
                expect(parseFloat(styles.height)).toBeCloseTo(17.6, 1);
            }
        }
    });
});