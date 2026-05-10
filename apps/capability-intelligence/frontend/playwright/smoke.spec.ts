import { expect, test } from '@playwright/test';

test('home page loads and shows Zennify branding', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Zennify')).toBeVisible();
  await expect(page.getByText('Capability Intelligence')).toBeVisible();
  await expect(page.getByText('Mission Control')).toBeVisible();
});

test('api health endpoint is reachable', async ({ request }) => {
  const r = await request.get('/api/health');
  expect(r.ok()).toBeTruthy();
  const body = await r.json();
  expect(body.status).toBe('ok');
});
