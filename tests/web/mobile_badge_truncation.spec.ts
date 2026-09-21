import { test, expect } from '@playwright/test';

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

const VIEWPORTS = [
    { name: '375px', width: 375, height: 667, expectTruncation: true },
    { name: '640px', width: 640, height: 800, expectTruncation: false },
    { name: '1024px', width: 1024, height: 768, expectTruncation: false },
];

for (const vp of VIEWPORTS) {
    test.describe(`Mobile badge truncation @ ${vp.name}`, () => {
        test.use({ viewport: { width: vp.width, height: vp.height } });

        test('Dashboard badge truncation for INSUFFICIENT DATA', async ({ page }) => {
            await ensureLoggedIn(page);
            await page.waitForTimeout(500);

            const badge = page.locator('.status-badge.status-insufficient_data').first();
            await expect(badge).toBeVisible();

            const boundingBox = await badge.boundingBox();
            expect(boundingBox).not.toBeNull();

            if (vp.expectTruncation) {
                // At 375px, badge should be truncated (max-width 100px)
                expect(boundingBox!.width).toBeLessThanOrEqual(100);
                // Text should be truncated with ellipsis
                const text = await badge.textContent();
                expect(text).toContain('INSUFFICIENT');
                // Full text should be in title attribute (tooltip)
                const title = await badge.getAttribute('title');
                expect(title).toBe('INSUFFICIENT DATA');
            } else {
                // At 640px+, no truncation - full width
                const text = await badge.textContent();
                expect(text?.trim()).toBe('INSUFFICIENT DATA');
                const title = await badge.getAttribute('title');
                expect(title).toBe('INSUFFICIENT DATA');
            }
        });

        test('Badge tooltip on hover', async ({ page }) => {
            await ensureLoggedIn(page);
            await page.waitForTimeout(500);

            const badge = page.locator('.status-badge.status-insufficient_data').first();
            await expect(badge).toBeVisible();

            // Hover to trigger tooltip
            await badge.hover();
            await page.waitForTimeout(100); // Allow tooltip to appear

            // Native title tooltip is browser-rendered, verify title attribute exists
            const title = await badge.getAttribute('title');
            expect(title).toBeTruthy();
            expect(title?.length).toBeGreaterThan(0);
        });

        test('Badge tooltip on keyboard focus', async ({ page }) => {
            await ensureLoggedIn(page);
            await page.waitForTimeout(500);

            const badge = page.locator('.status-badge.status-insufficient_data').first();
            await expect(badge).toBeVisible();

            // Focus via keyboard (tab navigation)
            await badge.focus();
            await page.waitForTimeout(100);

            // Verify focus state and title attribute
            const title = await badge.getAttribute('title');
            expect(title).toBeTruthy();
            // Focus should be visible (browser focus ring)
            const focused = await page.evaluate(() => document.activeElement === document.querySelector('.status-badge.status-insufficient_data'));
            expect(focused).toBe(true);
        });

        test('All status badge variants have title attribute', async ({ page }) => {
            await ensureLoggedIn(page);
            await page.waitForTimeout(500);

            const badges = page.locator('.status-badge');
            const count = await badges.count();

            for (let i = 0; i < count; i++) {
                const badge = badges.nth(i);
                const title = await badge.getAttribute('title');
                expect(title).toBeTruthy();
                expect(title?.length).toBeGreaterThan(0);
            }
        });

        test('Exercise detail page badges use shared partial', async ({ page }) => {
            const hasExercises = await goToFirstExerciseDetail(page);
            if (!hasExercises) {
                test.skip();
                return;
            }
            await page.waitForTimeout(500);

            // Status summary badge
            const statusSummaryBadge = page.locator('.status-summary .status-badge').first();
            await expect(statusSummaryBadge).toBeVisible();
            const summaryTitle = await statusSummaryBadge.getAttribute('title');
            expect(summaryTitle).toBeTruthy();

            // History table badges
            const historyBadges = page.locator('.history-table .status-badge');
            const historyCount = await historyBadges.count();
            if (historyCount > 0) {
                for (let i = 0; i < historyCount; i++) {
                    const badge = historyBadges.nth(i);
                    const title = await badge.getAttribute('title');
                    expect(title).toBeTruthy();
                }
            }

            // Mobile history cards badges
            const cardBadges = page.locator('.history-cards .status-badge');
            const cardCount = await cardBadges.count();
            if (cardCount > 0) {
                for (let i = 0; i < cardCount; i++) {
                    const badge = cardBadges.nth(i);
                    const title = await badge.getAttribute('title');
                    expect(title).toBeTruthy();
                }
            }
        });
    });
}