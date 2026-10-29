/* Instagram feed-specific checks. Reel/Story and other networks retain their upload flow. */
function getInstagramMediaError() {
    const list = document.getElementById('media-list');
    if (list?.dataset.instagramCarousel !== 'true') return '';
    const items = Array.from(list.querySelectorAll('.media-thumb[data-asset-id]'));
    if (items.length > 10) return 'O carrossel do Instagram aceita até 10 fotos e vídeos no total.';
    if (items.length < 2) return '';
    const videos = items.filter(item => item.querySelector('video'));
    if (videos.length && list.dataset.mixedAllowed !== 'true') {
        return 'Para usar fotos e vídeos no mesmo carrossel, selecione apenas Instagram no formato Post.';
    }
    for (const item of videos) {
        if (item.dataset.extension && !['mp4', 'mov'].includes(item.dataset.extension)) return 'Use vídeos MP4 ou MOV no carrossel.';
        const duration = Number(item.dataset.duration) || item.querySelector('video').duration;
        if (Number.isFinite(duration) && duration > 60) return 'Cada vídeo do carrossel aceita até 60 segundos.';
    }
    return '';
}

function refreshInstagramMediaError() {
    const warning = document.getElementById('carousel-media-error');
    if (!warning) return;
    warning.textContent = getInstagramMediaError();
    warning.hidden = !warning.textContent;
}

function readComposerVideoMetadata(file) {
    return new Promise((resolve, reject) => {
        const video = document.createElement('video');
        const url = URL.createObjectURL(file);
        const done = (error) => {
            clearTimeout(timer);
            video.onloadedmetadata = video.onerror = null;
            const result = { duration: video.duration, width: video.videoWidth, height: video.videoHeight };
            video.removeAttribute('src'); video.load(); URL.revokeObjectURL(url);
            if (error || !Number.isFinite(result.duration) || result.duration <= 0) reject(new Error('Não foi possível ler o vídeo. Use MP4 ou MOV compatível com o navegador.'));
            else resolve(result);
        };
        const timer = setTimeout(() => done(true), 15000);
        video.preload = 'metadata';
        video.onloadedmetadata = () => done(false);
        video.onerror = () => done(true);
        video.src = url;
    });
}
