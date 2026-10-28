// Uses the full real composer HTML rendered with synthetic pytest data.
// Export: STORY_BROWSER_FIXTURE_DIR=media/.local pytest tests/test_story_composer.py -k editor_keeps_ordered
// Run with Playwright in NODE_PATH: node tests/browser/story-composer.cjs media/.local/story-editor.json
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
        const errors = [];
        const saves = [];
        const autosaves = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const req = route.request();
            const url = new URL(req.url());
            if (url.origin !== 'http://story.local') return route.abort();
            if (url.pathname.startsWith('/static/')) {
                const relative = url.pathname.slice('/static/'.length);
                for (const dir of ['static', 'theme/static']) {
                    const base = path.resolve(root, dir);
                    const file = path.resolve(base, relative);
                    if (file.startsWith(base + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
                        const contentType = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'application/javascript' : 'application/octet-stream';
                        return route.fulfill({ contentType, body: fs.readFileSync(file) });
                    }
                }
                return route.fulfill({ status: 404, body: '' });
            }
            if (url.pathname.endsWith('/save/')) {
                saves.push(new URLSearchParams(req.postData()));
                return route.fulfill({ status: 204, body: '' });
            }
            if (url.pathname.endsWith('/autosave/')) {
                autosaves.push(new URLSearchParams(req.postData()));
                return route.fulfill({ body: 'Salvo' });
            }
            if (url.pathname.endsWith('/preview/')) return route.fulfill({ body: '<p>Prévia</p>' });
            if (url.pathname.startsWith('/media/')) return route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9xkAAAAASUVORK5CYII=', 'base64') });
            return route.fulfill({ contentType: 'text/html; charset=utf-8', body: fixture.html });
        });
        await page.goto('http://story.local/editor/');
        await page.waitForFunction(() => window.Alpine && document.querySelector('[name=caption]')?._x_model);
        const caption = page.locator('textarea[name=caption]');
        const comment = page.locator('textarea[name=first_comment]');
        const format = async (platform, value) => {
            await page.locator(`input[name="ig_format_${fixture.accounts[platform]}"][value="${value}"]`).locator('..').click();
        };
        const account = platform => page.locator('.acct-pill').filter({ hasText: new RegExp(`^\\s*${platform}\\s*$`) });
        const visible = locator => locator.evaluate(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length));
        const mediaIds = () => page.locator('#media-list input[name=media_ids]').evaluateAll(inputs => inputs.map(input => input.value));
        await caption.fill('Legenda preservada na troca');
        await comment.fill('Comentário preservado na troca');
        assert.deepEqual(await mediaIds(), fixture.mediaIds);
        await format('instagram', 'story');
        await page.getByText('Mídias do Story', { exact: true }).waitFor();
        assert.equal(await visible(caption), false);
        assert.equal(await visible(comment), false);
        assert.equal(await visible(page.getByRole('button', { name: 'Usar Modelo', exact: true, includeHidden: true })), false);
        assert.equal(await visible(page.locator('#media-list')), true);
        assert.deepEqual(await mediaIds(), fixture.mediaIds);
        assert.equal(await caption.inputValue(), 'Legenda preservada na troca');
        assert.equal(await comment.inputValue(), 'Comentário preservado na troca');

        await account('facebook').click();
        const conflict = page.locator('p[role=alert]').filter({ hasText: 'Story não pode ser combinado' });
        await conflict.waitFor();
        await page.getByRole('button', { name: 'Salvar Rascunho', exact: true }).click();
        await page.evaluate(() => {
            const trigger = document.getElementById('autosave-trigger');
            htmx.ajax('POST', trigger.getAttribute('hx-post'), { source: trigger });
        });
        await page.waitForTimeout(250);
        assert.equal(saves.length, 0, 'Mixed Story selection must not submit');
        assert.equal(autosaves.length, 0, 'Mixed Story selection must not autosave');
        await account('facebook').click();
        for (const value of ['reel', 'feed', 'story', 'feed']) {
            await format('instagram', value);
            await page.waitForFunction(expected => {
                const el = document.querySelector('textarea[name=caption]');
                return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) === expected;
            }, value !== 'story');
            assert.equal(await caption.inputValue(), 'Legenda preservada na troca');
            assert.equal(await comment.inputValue(), 'Comentário preservado na troca');
            assert.deepEqual(await mediaIds(), fixture.mediaIds);
        }
        await page.getByRole('button', { name: 'Salvar Rascunho', exact: true }).click();
        await page.waitForFunction(() => document.querySelector('#composer-form').getAttribute('hx-post'));
        await page.waitForTimeout(200);
        assert.equal(saves.length, 1);
        assert.equal(saves[0].get('caption'), 'Legenda preservada na troca');
        assert.equal(saves[0].get('first_comment'), 'Comentário preservado na troca');
        assert.deepEqual(errors, []);
        console.log('PASS: Story hides text only; Post/Reel restore it; media order stays intact; mixed selection is blocked.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
