// Run with Node and playwright available through node_modules or NODE_PATH.
// Uses bundled HTMX and the real template expression; no external requests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const template = fs.readFileSync(path.join(root, 'templates/composer/compose.html'), 'utf8');
    const vals = template.match(/hx-vals='(js:getPreviewVals\(\)|js:\{\.\.\.getPreviewVals\(\)\})'/)[1];
    const helper = template.match(/function getPreviewVals\(\) \{[\s\S]*?\n\}/)[0];
    const htmx = fs.readFileSync(path.join(root, 'static/js/htmx.min.js'), 'utf8');
    const html = `<form id="composer-form">
        <input name="selected_accounts" value="instagram-account">
        <textarea name="caption"></textarea>
        <div id="media-list"><input name="media_ids" value="uploaded-image"></div>
        </form><div id="preview-panel" hx-get="/preview/"
        hx-trigger="previewUpdate from:body" hx-include="#composer-form" hx-vals='${vals}'>Empty</div>
        <script>${helper}</script><script>${htmx}</script>`;
    const browser = await chromium.launch({ channel: 'msedge', headless: true });
    try {
        const page = await browser.newPage();
        const errors = [];
        const requests = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://preview.local') return route.abort();
            if (url.pathname === '/preview/') {
                requests.push(url.searchParams);
                return route.fulfill({ contentType: 'text/html', body: '<div>Rendered preview</div>' });
            }
            return route.fulfill({ contentType: 'text/html', body: html });
        });
        await page.goto('http://preview.local/');
        await page.evaluate(() => document.body.dispatchEvent(new CustomEvent('previewUpdate')));
        await page.waitForFunction(() => document.querySelector('#preview-panel').textContent === 'Rendered preview', null, { timeout: 3000 });
        assert.deepEqual(errors, []);
        assert.equal(requests[0].get('selected_accounts'), 'instagram-account');
        assert.equal(requests[0].get('caption'), '');
        assert.equal(requests[0].get('media_ids'), 'uploaded-image');
        await page.fill('[name=caption]', 'Nova legenda');
        const updated = page.waitForResponse(response => response.url().includes('/preview/') && response.status() === 200);
        await page.evaluate(() => document.body.dispatchEvent(new CustomEvent('previewUpdate')));
        await updated;
        assert.equal(requests.at(-1).get('caption'), 'Nova legenda');
        console.log('PASS: image-only preview and caption updates reach HTMX endpoint.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
