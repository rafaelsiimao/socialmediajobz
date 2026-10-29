// Offline real composer: no live accounts, uploads or posts.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
    const browser = await chromium.launch({ channel: 'msedge', headless: true });
    try {
        const page = await browser.newPage();
        const mutations = [], errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('**/*', route => {
            const req = route.request(), url = new URL(req.url());
            if (url.origin !== 'https://linkedin.local') return route.abort();
            if (req.method() === 'POST') {
                mutations.push(url.pathname);
                return route.fulfill({ body: 'Salvo' });
            }
            if (url.pathname.startsWith('/static/')) {
                for (const dir of ['static', 'theme/static']) {
                    const base = path.resolve(root, dir), file = path.resolve(base, url.pathname.slice(8));
                    if (file.startsWith(base + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
                        return route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'application/javascript', body: fs.readFileSync(file) });
                    }
                }
                return route.fulfill({ status: 404, body: '' });
            }
            if (url.pathname.startsWith('/media/')) return route.fulfill({ status: 404, body: '' });
            if (url.pathname.endsWith('/preview/')) return route.fulfill({ body: '' });
            return route.fulfill({ contentType: 'text/html', body: fixture.html });
        });
        await page.goto('https://linkedin.local/editor/');
        await page.waitForFunction(() => window.Alpine && document.getElementById('media-list')?.dataset.linkedinSelected === 'true');
        assert.match(await page.locator('#carousel-media-error').innerText(), /um vídeo/);
        await page.getByRole('button', { name: 'Salvar Rascunho', exact: true }).click();
        assert.equal(mutations.length, 0, 'Invalid saved attachments must not submit');
        for (const platform of ['linkedin_personal', 'linkedin_company']) {
            await page.evaluate(id => { Alpine.$data(document.querySelector('[x-data="composerApp()"]')).selectedAccounts = [id]; }, fixture.accounts[platform]);
            await page.waitForFunction(() => getComposerMediaError().includes('um vídeo'));
        }
        // Keep just the existing video; then attempt to add another photo/video.
        await page.evaluate(() => {
            document.querySelector('#media-list .media-thumb img').closest('.media-thumb').remove();
            composerMediaChanged();
        });
        assert.equal(await page.evaluate(() => getComposerMediaError()), '');
        for (const type of ['image/jpeg', 'video/mp4']) {
            const error = await page.evaluate(async type => {
                const state = Alpine.$data(document.querySelector('[x-data="composerApp()"]'));
                await state.processFiles([new File(['synthetic'], type.startsWith('image') ? 'second.jpg' : 'second.mp4', { type })]);
                return state.formError;
            }, type);
            assert.match(error, /um vídeo/);
        }
        assert.equal(mutations.length, 0, 'Invalid uploads must not reach server');
        // Removing the video clears the warning and permits a normal draft save.
        await page.evaluate(() => { document.querySelector('#media-list .media-thumb').remove(); composerMediaChanged(); });
        assert.equal(await page.evaluate(() => getComposerMediaError()), '');
        await Promise.all([
            page.waitForRequest(req => req.method() === 'POST' && req.url().includes('/save/')),
            page.getByRole('button', { name: 'Salvar Rascunho', exact: true }).click(),
        ]);
        assert.ok(mutations.length > 0);
        assert.deepEqual(errors, []);
        console.log('PASS: LinkedIn personal/company warning, blocked save/uploads, removal and valid save');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
