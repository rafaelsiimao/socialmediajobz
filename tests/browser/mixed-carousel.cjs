// Real composer + Alpine/HTMX/Cropper. All requests use synthetic local fixtures.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');

(async () => {
    const root = path.resolve(__dirname, '../..');
    const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
    const videoPath = path.join(root, 'media/.local/mixed-browser-fixture.mp4');
    const generated = spawnSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=10', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100', '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', videoPath], { windowsHide: true });
    assert.equal(generated.status, 0, generated.stderr?.toString() || 'FFmpeg must be available to generate the synthetic video');
    const videoBytes = fs.readFileSync(videoPath), videoMime = 'video/mp4';
    const browser = await chromium.launch({ channel: 'msedge', headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
        const uploads = [], saves = [], errors = [];
        const extraVideoId = '22222222-2222-4222-8222-222222222222';
        page.on('pageerror', error => errors.push(error.message));
        await page.addInitScript(() => {
            window._testRejections = [];
            window.addEventListener('unhandledrejection', event => window._testRejections.push({
                keys: Object.keys(event.reason || {}), reason: event.reason?.reason,
                message: event.reason?.message, stack: event.reason?.stack,
            }));
        });
        page.on('console', message => { if (message.text().includes('Alpine Expression Error')) console.error(message.text()); });
        await page.route('**/*', route => {
            const req = route.request(), url = new URL(req.url());
            if (url.origin !== 'https://mixed.local') return route.abort();
            if (url.pathname.startsWith('/static/')) {
                for (const dir of ['static', 'theme/static']) {
                    const base = path.resolve(root, dir), file = path.resolve(base, url.pathname.slice(8));
                    if (file.startsWith(base + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
                        return route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'application/javascript', body: fs.readFileSync(file) });
                    }
                }
                return route.fulfill({ status: 404, body: '' });
            }
            if (url.pathname.endsWith('/preview/')) return route.fulfill({ contentType: 'text/html', body: fixture.preview });
            if (url.pathname.endsWith('/save/') || url.pathname.endsWith('/autosave/')) {
                saves.push(new URLSearchParams(req.postData()));
                return route.fulfill({ body: 'Salvo' });
            }
            if (url.pathname.endsWith('/upload-media/')) {
                const body = req.postData();
                const name = body.match(/filename="([^"]+)"/)[1];
                uploads.push(name);
                let html = name.endsWith('.mp4') ? fixture.thumbs[1] : fixture.thumbs[0];
                if (name.endsWith('.mp4')) assert.ok(body.includes('name="inspect_video"'));
                if (name === 'second.mp4') html = html.replaceAll(fixture.mediaIds[1], extraVideoId);
                return route.fulfill({ contentType: 'text/html', body: html });
            }
            if (url.pathname.startsWith('/media/')) {
                if (url.pathname.endsWith('.mp4')) return route.fulfill({ status: videoBytes.length ? 200 : 404, headers: { 'Cache-Control': 'no-store' }, contentType: videoMime, body: videoBytes });
                return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350"><rect width="100%" height="100%" fill="lightblue"/></svg>' });
            }
            return route.fulfill({ contentType: 'text/html', body: fixture.html });
        });
        await page.goto('https://mixed.local/editor/');
        await page.waitForFunction(() => window.Alpine && document.querySelector('[name=caption]')?._x_model);
        await page.waitForFunction(() => document.querySelector('video[aria-label="Vídeo do carrossel"]')?.readyState >= 1);
        const preview = page.locator('.preview-card');
        await preview.locator('button.absolute.right-2').click();
        const movie = page.locator('video[aria-label="Vídeo do carrossel"]');
        await movie.waitFor({ state: 'visible' });
        await movie.evaluate(video => { video.loop = true; video.currentTime = 0; return video.play(); });
        assert.equal(await movie.evaluate(video => video.paused), false);
        assert.equal(await movie.getAttribute('controls'), '');
        assert.equal(await movie.getAttribute('muted'), null);
        await preview.locator('button.absolute.right-2').click();
        await page.waitForFunction(() => document.querySelector('video[aria-label="Vídeo do carrossel"]').paused);
        const thumbs = page.locator('#media-list .media-thumb');
        const ids = () => page.locator('#media-list input[name=media_ids]').evaluateAll(inputs => inputs.map(input => input.value));
        await thumbs.nth(1).getByRole('button', { name: 'Mover para a esquerda' }).click();
        assert.deepEqual(await ids(), [fixture.mediaIds[1], fixture.mediaIds[0], fixture.mediaIds[2]]);
        assert.equal(await thumbs.first().locator('.media-crop-btn').isVisible(), false);
        assert.equal(await page.locator('#media-list .media-crop-warning').count(), 2);
        await thumbs.nth(1).getByRole('button', { name: 'Ajustar recorte' }).click();
        await page.waitForFunction(() => !document.getElementById('composer-crop-apply').disabled);
        const ratio = await page.evaluate(() => { const crop = composerCrop.cropper.getData(); return crop.width / crop.height; });
        assert.ok(Math.abs(ratio - 16 / 9) < .02);
        await page.keyboard.press('Escape');
        await page.locator('.acct-pill').filter({ hasText: 'facebook' }).click();
        await page.locator('#carousel-media-error').waitFor({ state: 'visible' });
        const beforeInvalidSave = saves.length;
        await page.getByRole('button', { name: 'Salvar Rascunho', exact: true }).click();
        assert.equal(saves.length, beforeInvalidSave);
        await page.locator('.acct-pill').filter({ hasText: 'facebook' }).click();
        while (await thumbs.count()) await thumbs.first().locator('.remove-btn').click();
        const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9xkAAAAASUVORK5CYII=', 'base64');
        await page.locator('input[type=file]').first().setInputFiles([
            { name: 'photo.jpg', mimeType: 'image/jpeg', buffer: pixel },
            { name: 'first.mp4', mimeType: 'video/mp4', buffer: videoBytes },
            { name: 'second.mp4', mimeType: 'video/mp4', buffer: videoBytes },
        ]);
        await page.waitForFunction(() => document.querySelectorAll('#media-list input[name=media_ids]').length === 3 || Alpine.$data(document.querySelector('.composer-main')).formError);
        assert.equal(await page.evaluate(() => Alpine.$data(document.querySelector('.composer-main')).formError), '');
        assert.deepEqual(uploads, ['photo.jpg', 'first.mp4', 'second.mp4']);
        assert.deepEqual(await ids(), [fixture.mediaIds[0], fixture.mediaIds[1], extraVideoId]);
        assert.equal(await page.locator('#media-list video').count(), 2);
        await page.locator('input[type=file]').first().setInputFiles(Array.from({ length: 8 }, (_, i) => ({ name: `extra-${i}.jpg`, mimeType: 'image/jpeg', buffer: pixel })));
        await page.getByText('O carrossel do Instagram aceita até 10 fotos e vídeos no total.', { exact: true }).first().waitFor();
        assert.equal(uploads.length, 3);
        await page.evaluate(() => { window._originalVideoMetadata = readComposerVideoMetadata; window.readComposerVideoMetadata = async () => ({ duration: 61, width: 160, height: 90 }); });
        await page.locator('input[type=file]').first().setInputFiles({ name: 'long.mp4', mimeType: 'video/mp4', buffer: videoBytes });
        await page.getByText('Cada vídeo do carrossel aceita até 60 segundos.', { exact: true }).first().waitFor();
        assert.equal(uploads.length, 3);
        if (errors.length) console.error('Browser rejections:', await page.evaluate(() => window._testRejections));
        assert.deepEqual(errors, []);
        console.log('PASS: mixed uploads, multiple videos, playback/audio/pause, video cover crop, network conflict, 10-item and 60-second limits.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
