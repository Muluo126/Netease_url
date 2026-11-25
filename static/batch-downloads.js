/* 解析结果中的勾选下载；只请求一次 ZIP，避免浏览器拦截多个文件。 */
$(function () {
    'use strict';

    const lists = {search: '#search-list', playlist: '#playlist-tracks', album: '#album-tracks'};
    const qualityNames = {standard: '标准', exhigh: '极高', lossless: '无损', hires: 'Hi-Res',
        jyeffect: '高清环绕声', sky: '沉浸环绕声', jymaster: '超清母带', vivid: '臻音全景声', dolby: '杜比全景声'};
    let activeJob = null;
    let polling = false;
    let pollFailures = 0;

    const panel = $('<section id="batch-progress" class="card mt-4 d-none" aria-label="批量下载进度">')
        .appendTo($('#search-result').parent());
    panel.insertBefore('#search-result').append(`
        <div class="card-body">
            <h5>批量下载</h5>
            <p id="batch-status" role="status" aria-live="polite"></p>
            <div class="progress mb-3">
                <div id="batch-progress-bar" class="progress-bar" role="progressbar"
                     aria-label="歌曲下载进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" style="width:0%"></div>
            </div>
            <a id="batch-file" class="btn btn-success mt-0 d-none" download>下载 ZIP（1 小时内有效）</a>
            <button id="batch-resume" class="btn btn-outline-primary d-none" type="button">继续查询进度</button>
            <details id="batch-errors" class="mt-3 d-none"><summary>下载失败的歌曲</summary><ul></ul></details>
            <details id="batch-fallbacks" class="mt-3 d-none"><summary>已降低音质下载的歌曲</summary><ul></ul></details>
        </div>`);

    Object.entries(lists).forEach(([scope, selector]) => {
        const toolbar = $('<div class="batch-toolbar d-flex flex-wrap align-items-center gap-2 my-3">')
            .attr('data-scope', scope).insertBefore(selector);
        const selectAll = $('<input type="checkbox" class="form-check-input batch-select-all me-1">');
        $('<label class="mb-0">').append(selectAll, document.createTextNode('全选')).appendTo(toolbar);
        const quality = $('#download_quality').clone().removeAttr('id')
            .addClass('batch-quality').attr('aria-label', '批量下载音质').css('width', 'auto');
        toolbar.append(quality,
            $('<button type="button" class="btn btn-success mt-0 batch-selected" disabled>').text('下载选中（0）'),
            $('<button type="button" class="btn btn-outline-success batch-all" disabled>').text('下载全部（0）'));
    });

    function updateSelection(scope) {
        const toolbar = $(`.batch-toolbar[data-scope="${scope}"]`);
        const boxes = $(lists[scope]).find('.batch-song');
        const count = boxes.filter(':checked').length;
        toolbar.find('.batch-select-all').prop('checked', boxes.length > 0 && count === boxes.length)
            .prop('indeterminate', count > 0 && count < boxes.length).prop('disabled', !!activeJob || !boxes.length);
        toolbar.find('.batch-selected').text(`下载选中（${count}）`).prop('disabled', !!activeJob || !count);
        toolbar.find('.batch-all').text(`下载全部（${boxes.length}）`).prop('disabled', !!activeJob || !boxes.length);
        toolbar.find('.batch-quality').prop('disabled', !!activeJob);
        boxes.prop('disabled', !!activeJob);
    }

    function updateAll() {
        Object.keys(lists).forEach(updateSelection);
    }

    window.batchDownloads = {
        renderTracks(scope, songs) {
            const list = $(lists[scope]).empty();
            songs.forEach((song, index) => {
                const item = $('<li class="list-group-item d-flex justify-content-between align-items-center gap-2 flex-wrap">');
                const details = $('<div class="d-flex align-items-center flex-grow-1">');
                $('<input type="checkbox" class="form-check-input batch-song me-2">')
                    .attr('data-id', String(song.id)).attr('aria-label', `选择 ${song.name}`).appendTo(details);
                $('<img alt="封面" loading="lazy">').attr('src', song.picUrl || '')
                    .css({width: '32px', height: '32px', objectFit: 'cover', borderRadius: '4px', marginRight: '8px'}).appendTo(details);
                const info = $('<span>');
                $('<strong class="song-title">').text(`${index + 1}. ${song.name}`).appendTo(info);
                info.append(document.createTextNode(` - ${song.artists || ''} [${song.album || ''}]`));
                details.append(info);
                const buttons = $('<div class="d-flex gap-2 flex-shrink-0">');
                $('<button type="button" class="btn btn-sm btn-outline-primary select-song">').text('解析')
                    .attr('data-id', String(song.id)).attr('data-name', song.name).appendTo(buttons);
                $('<button type="button" class="btn btn-sm btn-success mt-0 download-song">').text('下载')
                    .attr('data-id', String(song.id)).attr('data-name', song.name).appendTo(buttons);
                list.append(item.append(details, buttons));
            });
            if (!songs.length) list.append($('<li class="list-group-item">').text('没有可下载的歌曲'));
            updateSelection(scope);
        }
    };

    $(document).on('change', '.batch-song', function () {
        const scope = Object.keys(lists).find(key => $(this).closest(lists[key]).length);
        updateSelection(scope);
    });
    $(document).on('change', '.batch-select-all', function () {
        const scope = $(this).closest('.batch-toolbar').attr('data-scope');
        $(lists[scope]).find('.batch-song').prop('checked', this.checked);
        updateSelection(scope);
    });

    function finish() {
        activeJob = null;
        polling = false;
        updateAll();
    }

    async function poll() {
        if (!activeJob || polling) return;
        polling = true;
        $('#batch-resume').addClass('d-none');
        try {
            const response = await fetch(`/download/batch/${activeJob}`, {cache: 'no-store'});
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                if (response.status === 404) {
                    $('#batch-status').text(payload.message);
                    finish();
                    return;
                }
                throw new Error(payload.message || '进度查询失败');
            }
            pollFailures = 0;
            const job = payload.data;
            const percent = Math.round(job.completed / job.total * 100);
            $('#batch-progress-bar').css('width', `${percent}%`).attr('aria-valuenow', percent).text(`${percent}%`);
            const currentQuality = job.current_quality ? `（${qualityNames[job.current_quality] || job.current_quality}）` : '';
            $('#batch-status').text(`${job.message}${currentQuality}：${job.completed}/${job.total}，成功 ${job.succeeded} 首，失败 ${job.failed} 首，降级成功 ${job.fallback_count || 0} 首`);
            const errors = $('#batch-errors').toggleClass('d-none', !job.failures.length).find('ul').empty();
            job.failures.forEach(failure => $('<li>').text(`歌曲 ${failure.id}：${failure.message}`).appendTo(errors));
            const fallbacks = job.fallbacks || [];
            const fallbackList = $('#batch-fallbacks').toggleClass('d-none', !fallbacks.length).find('ul').empty();
            fallbacks.forEach(song => $('<li>').text(`歌曲 ${song.id}：${qualityNames[song.requested_quality] || song.requested_quality} → ${qualityNames[song.quality] || song.quality}`).appendTo(fallbackList));
            if (job.state === 'completed') {
                const link = $('#batch-file').attr('href', `/download/batch/${job.id}/file`)
                    .attr('download', job.filename).removeClass('d-none');
                link[0].click();
                finish();
                return;
            }
            if (job.state === 'failed') {
                finish();
                return;
            }
        } catch (error) {
            pollFailures += 1;
            $('#batch-status').text(`暂时无法查询进度：${error.message}。后台任务仍可能继续。`);
            if (pollFailures >= 3) {
                polling = false;
                $('#batch-resume').removeClass('d-none');
                return;
            }
        }
        polling = false;
        window.setTimeout(poll, 1500);
    }

    $('#batch-resume').on('click', function () { pollFailures = 0; poll(); });

    $(document).on('click', '.batch-selected, .batch-all', async function () {
        if (activeJob) return;
        const toolbar = $(this).closest('.batch-toolbar');
        const scope = toolbar.attr('data-scope');
        const selector = $(this).hasClass('batch-selected') ? '.batch-song:checked' : '.batch-song';
        const ids = $(lists[scope]).find(selector).map(function () { return $(this).attr('data-id'); }).get();
        if (!ids.length) return;
        if (ids.length > 500) {
            alert('每批最多下载 500 首，请勾选部分歌曲后下载');
            return;
        }
        const quality = toolbar.find('.batch-quality').val();
        const name = scope === 'search' ? '搜索结果' : $(`#${scope}-name`).text();
        activeJob = 'creating';
        updateAll();
        panel.removeClass('d-none');
        $('#batch-file, #batch-resume, #batch-errors, #batch-fallbacks').addClass('d-none');
        $('#batch-progress-bar').css('width', '0%').attr('aria-valuenow', 0).text('0%');
        $('#batch-status').text(`正在创建任务，共 ${ids.length} 首歌曲…`);
        let response;
        try {
            response = await fetch('/download/batch', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ids, quality, name})
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error(payload.message || '创建任务失败');
            activeJob = payload.data.id;
            pollFailures = 0;
            poll();
        } catch (error) {
            $('#batch-status').text(`创建任务失败：${error.message}`);
            finish();
        }
    });
    updateAll();
});
