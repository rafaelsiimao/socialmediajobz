/* Uses the bundled Cropper.js. Pixels are cropped on the server, avoiding canvas CORS issues. */
let composerCrop = null;

function openComposerCrop(button) {
    const thumb = button.closest('.media-thumb');
    const list = document.getElementById('media-list');
    const cover = list.querySelector('.media-thumb[data-asset-id]');
    if (!thumb || !cover || list.dataset.instagramCarousel !== 'true') return;
    const coverImage = cover.querySelector('img');
    const width = Number(cover.dataset.width) || coverImage?.naturalWidth;
    const height = Number(cover.dataset.height) || coverImage?.naturalHeight;
    if (!width || !height) return;
    const dialog = document.getElementById('composer-crop-dialog');
    const image = document.getElementById('composer-crop-image');
    const error = document.getElementById('composer-crop-error');
    const apply = document.getElementById('composer-crop-apply');
    const ratio = Math.min(1.91, Math.max(.8, width / height));
    error.hidden = true;
    apply.disabled = true;
    document.getElementById('composer-crop-preview').style.aspectRatio = ratio;
    composerCrop = { thumb, coverId: cover.dataset.assetId, cropper: null, busy: false };
    dialog.oncancel = event => { event.preventDefault(); closeComposerCrop(); };
    dialog.showModal();
    image.onerror = () => {
        error.textContent = 'Não foi possível carregar a foto. Feche e tente novamente.';
        error.hidden = false;
    };
    image.src = thumb.querySelector('img').src;
    const state = composerCrop;
    state.cropper = new Cropper(image, {
        aspectRatio: ratio, viewMode: 1, autoCropArea: 1,
        background: false, responsive: true, dragMode: 'move',
        checkCrossOrigin: false, checkOrientation: false,
        rotatable: false, scalable: false,
        preview: '#composer-crop-preview',
        ready() { if (composerCrop === state) apply.disabled = false; },
    });
}

function zoomComposerCrop(amount) { if (!composerCrop?.busy) composerCrop?.cropper?.zoom(amount); }
function resetComposerCrop() { if (!composerCrop?.busy) composerCrop?.cropper?.reset(); }

function closeComposerCrop() {
    if (composerCrop?.busy) return;
    composerCrop?.cropper?.destroy();
    composerCrop = null;
    document.getElementById('composer-crop-dialog').close();
}

async function applyComposerCrop() {
    const state = composerCrop;
    if (!state?.cropper || state.busy) return;
    const dialog = document.getElementById('composer-crop-dialog');
    const apply = document.getElementById('composer-crop-apply');
    const cancel = document.getElementById('composer-crop-cancel');
    const error = document.getElementById('composer-crop-error');
    const data = state.cropper.getData(true);
    const body = new FormData();
    for (const key of ['x', 'y', 'width', 'height']) body.append(key, data[key]);
    body.append('cover_asset_id', state.coverId);
    const url = dialog.dataset.cropUrl.replace('00000000-0000-0000-0000-000000000000', state.thumb.dataset.assetId);
    state.busy = true;
    apply.disabled = cancel.disabled = true;
    apply.textContent = 'Aplicando…';
    error.hidden = true;
    try {
        const response = await fetch(url, {
            method: 'POST', body,
            headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value },
        });
        if (!response.ok) {
            const details = await response.json().catch(() => ({}));
            throw new Error(details.error || 'Não foi possível aplicar. Recarregue a página e tente novamente.');
        }
        const result = await response.json();
        if (!state.thumb.isConnected) throw new Error('Esta foto foi removida. Feche e selecione outra foto.');
        state.thumb.insertAdjacentHTML('afterend', result.html);
        const replacement = state.thumb.nextElementSibling;
        state.thumb.remove();
        initMediaListSortable();
        composerMediaChanged();
        state.busy = false;
        closeComposerCrop();
        replacement.querySelector('.media-crop-btn')?.focus();
    } catch (failure) {
        error.textContent = failure.message;
        error.hidden = false;
    } finally {
        state.busy = false;
        apply.disabled = cancel.disabled = false;
        apply.textContent = 'Aplicar recorte';
    }
}
