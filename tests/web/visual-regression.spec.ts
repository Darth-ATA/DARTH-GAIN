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
    { name: '375px', width: 375, height: 667 },
    { name: '640px', width: 640, height: 800 },
    { name: '1024px', width: 1024, height: 768 },
];

for (const vp of VIEWPORTS) {
    test.describe(`Visual regression @ ${vp.name}`, () => {
        test.use({ viewport: { width: vp.width, height: vp.height } });

        test('Dashboard page', async ({ page }) => {
            await ensureLoggedIn(page);
            await page.waitForTimeout(500); // Allow any animations to complete
            await expect(page).toHaveScreenshot(`dashboard-${vp.name}.png`, {
                maxDiffPixels: 100,
                threshold: 0.1,
            });
        });

        test('Login page', async ({ page }) => {
            await page.goto('/login');
            await page.waitForLoadState('networkidle');
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`login-${vp.name}.png`, {
                maxDiffPixels: 100,
                threshold: 0.1,
            });
        });

        test('Exercise detail page', async ({ page }) => {
            const hasExercises = await goToFirstExerciseDetail(page);
            if (!hasExercises) {
                test.skip();
                return;
            }
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`exercise-detail-${vp.name}.png`, {
                maxDiffPixels: 100,
                threshold: 0.1,
            });
        });
    });
}