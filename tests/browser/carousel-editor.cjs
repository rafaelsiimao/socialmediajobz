// Synthetic full composer fixture; all requests are intercepted locally.
// Export with CAROUSEL_BROWSER_FIXTURE_DIR=media/.local pytest -k carousel_browser_fixture
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
    const browser = await chromium.launch({ channel: 'msedge', headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
        const errors = [], saves = [], previews = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const req = route.request(), url = new URL(req.url());
            if (url.origin !== 'http://carousel.local') return route.abort();
            if (url.pathname.startsWith('/static/')) {
                for (const dir of ['static', 'theme/static']) {
                    const base = path.resolve(root, dir);
                    const file = path.resolve(base, url.pathname.slice(8));
                    if (file.startsWith(base + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
                        return route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'application/javascript', body: fs.readFileSync(file) });
                    }
                }
                return route.fulfill({ status: 404, body: '' });
            }
            if (url.pathname.endsWith('/autosave/') || url.pathname.endsWith('/save/')) {
                saves.push(new URLSearchParams(req.postData()));
                return route.fulfill({ body: 'Salvo' });
            }
            if (url.pathname.endsWith('/preview/')) {
                previews.push(url.searchParams);
                return route.fulfill({ body: '<p>Prévia</p>' });
            }
            if (url.pathname.startsWith('/media/')) return route.fulfill({ body: '' });
            return route.fulfill({ contentType: 'text/html; charset=utf-8', body: fixture.html });
        });
        await page.goto('http://carousel.local/editor/');
        await page.waitForFunction(() => window.Alpine && document.querySelector('[name=caption]')?._x_model);
        const ids = () => page.locator('#media-list input[name=media_ids]').evaluateAll(inputs => inputs.map(i => i.value));
        // Framing follows slide 1, compares ratios (not pixel sizes), and never blocks saving.
        await page.evaluate(() => {
            const thumbs = document.querySelectorAll('#media-list .media-thumb');
            [[800, 1000], [1600, 2000], [1600, 900]].forEach(([width, height], i) => {
                thumbs[i].dataset.width = width;
                thumbs[i].dataset.height = height;
            });
            updateInstagramCarouselFraming();
        });
        const warning = page.locator('#carousel-crop-warning');
        await warning.waitFor({ state: 'visible' });
        assert.equal(await page.locator('#media-list .media-crop-warning').count(), 1);
        assert.equal(await page.locator('#media-list .media-crop-warning').getAttribute('data-asset-id'), fixture.mediaIds[2]);
        assert.equal(await page.locator('#media-list .media-crop-warning').evaluate(el => getComputedStyle(el).borderColor), 'rgb(220, 38, 38)');
        await page.locator('#media-list .media-thumb').nth(2).getByRole('button', { name: 'Mover para a esquerda' }).click();
        await page.locator('#media-list .media-thumb').nth(1).getByRole('button', { name: 'Mover para a esquerda' }).click();
        assert.equal(await page.locator('#media-list .media-crop-warning').count(), 2);
        assert.equal(await page.locator('#media-list .media-thumb').first().evaluate(el => el.classList.contains('media-crop-warning')), false);
        const frame = await page.locator('#media-list .media-thumb').first().evaluate(el => ({ width: el.offsetWidth, height: el.offsetHeight }));
        assert.ok(Math.abs(frame.width / frame.height - 1600 / 900) < .05);
        // Story and non-Instagram selections must not inherit feed crop warnings.
        await page.locator('input[name^="ig_format_"][value="story"]').first().locator('..').click();
        await warning.waitFor({ state: 'hidden' });
        assert.equal(await page.locator('#media-list .media-crop-warning').count(), 0);
        await page.locator('input[name^="ig_format_"][value="feed"]').first().locator('..').click();
        await warning.waitFor({ state: 'visible' });
        await page.locator('#media-list .media-thumb').first().getByRole('button', { name: 'Mover para a direita' }).click();
        await page.locator('#media-list .media-thumb').nth(1).getByRole('button', { name: 'Mover para a direita' }).click();
        assert.deepEqual(await ids(), fixture.mediaIds);
        // Mimic successive upload responses: old nodes already initialized, new node inserted later.
        await page.evaluate(() => {
            const list = document.getElementById('media-list');
            const thumb = list.lastElementChild;
            const html = thumb.outerHTML.replace('data-sortable-initialized="true"', '');
            thumb.remove();
            initMediaListSortable();
            list.insertAdjacentHTML('beforeend', html);
            initMediaListSortable();
        });
        const thumbs = page.locator('#media-list .media-thumb');
        const transfer = await page.evaluateHandle(() => new DataTransfer());
        await thumbs.nth(0).dispatchEvent('dragstart', { dataTransfer: transfer });
        const box = await thumbs.nth(2).boundingBox();
        await thumbs.nth(2).dispatchEvent('dragover', { dataTransfer: transfer, clientX: box.x + box.width - 1 });
        await thumbs.nth(0).dispatchEvent('dragend', { dataTransfer: transfer });
        assert.deepEqual(await ids(), [fixture.mediaIds[1], fixture.mediaIds[2], fixture.mediaIds[0]], 'Drag between separate uploads must reorder');
        await thumbs.nth(2).getByRole('button', { name: 'Mover para a esquerda' }).click();
        assert.deepEqual(await ids(), [fixture.mediaIds[1], fixture.mediaIds[0], fixture.mediaIds[2]]);
        await thumbs.nth(0).getByRole('button', { name: 'Mover para a direita' }).click();
        assert.deepEqual(await ids(), [fixture.mediaIds[0], fixture.mediaIds[1], fixture.mediaIds[2]]);
        await thumbs.nth(1).locator('.remove-btn').click();
        assert.deepEqual(await ids(), [fixture.mediaIds[0], fixture.mediaIds[2]], 'X must remove newly inserted media');
        await page.waitForTimeout(1600);
        assert.deepEqual(saves.at(-1).getAll('media_ids'), [fixture.mediaIds[0], fixture.mediaIds[2]]);
        while (await thumbs.count()) await thumbs.first().locator('.remove-btn').click();
        await page.waitForTimeout(1600);
        assert.deepEqual(saves.at(-1).getAll('media_ids'), []);
        assert.equal(saves.at(-1).get('media_submitted'), '1');
        assert.deepEqual(previews.at(-1).getAll('media_ids'), []);
        assert.equal(previews.at(-1).get('media_submitted'), '1');
        // Before first autosave, upload responses use the pending partial.
        await page.setViewportSize({ width: 390, height: 844 });
        await page.evaluate(html => {
            document.getElementById('media-list').insertAdjacentHTML('beforeend', html);
            initMediaListSortable();
        }, fixture.pendingHtml);
        assert.deepEqual(await ids(), fixture.mediaIds);
        await thumbs.nth(1).locator('.remove-btn').click();
        await thumbs.nth(1).getByRole('button', { name: 'Mover para a esquerda' }).click();
        assert.deepEqual(await ids(), [fixture.mediaIds[2], fixture.mediaIds[0]]);
        await page.waitForTimeout(1600);
        assert.deepEqual(saves.at(-1).getAll('media_ids'), [fixture.mediaIds[2], fixture.mediaIds[0]]);
        assert.deepEqual(saves.at(-1).getAll('pending_media_ids'), [fixture.mediaIds[2], fixture.mediaIds[0]]);
        assert.deepEqual(errors, []);
        console.log('PASS: successive uploads, drag, left/right controls, remove, empty preview and autosave payloads.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
