(function(){
  var currentDownloadUrl = null;
  var currentFileName = 'RDOs.pdf';
  var exportInProgress = false;

  function setStatus(text, isError){
    try{
      var el = document.getElementById('pdf-export-status');
      if (!el) return;
      el.textContent = text || '';
      if (isError) el.classList.add('mobile-pdf-export-error');
      else el.classList.remove('mobile-pdf-export-error');
    }catch(_){}
  }

  function setActionsVisible(visible){
    try{
      var el = document.getElementById('pdf-export-actions');
      if (!el) return;
      el.style.display = visible ? 'flex' : 'none';
    }catch(_){}
  }

  function revokeCurrentDownloadUrl(){
    try{
      if (currentDownloadUrl){
        URL.revokeObjectURL(currentDownloadUrl);
      }
    }catch(_){}
    currentDownloadUrl = null;
  }

  function triggerDownload(url, filename){
    if (!url) return false;
    try{
      var a = document.createElement('a');
      a.href = url;
      a.download = filename || currentFileName || 'RDOs.pdf';
      document.body.appendChild(a);
      a.click();
      try{ a.parentNode.removeChild(a); }catch(_){}
      return true;
    }catch(_){
      return false;
    }
  }

  function loadScriptOnce(src){
    return new Promise(function(resolve, reject){
      try{
        var existing = document.querySelector('script[data-mobile-pdf-src="' + src + '"]');
        if (existing) {
          if (existing.getAttribute('data-loaded') === '1') return resolve();
          existing.addEventListener('load', function(){ resolve(); }, { once: true });
          existing.addEventListener('error', function(){ reject(new Error('load_failed')); }, { once: true });
          return;
        }
        var s = document.createElement('script');
        s.src = src;
        s.async = true;
        s.setAttribute('data-mobile-pdf-src', src);
        s.onload = function(){ s.setAttribute('data-loaded', '1'); resolve(); };
        s.onerror = function(){ reject(new Error('load_failed')); };
        document.head.appendChild(s);
      }catch(e){ reject(e); }
    });
  }

  function ensurePdfLibs(){
    var tasks = [];
    if (!window.html2canvas){
      tasks.push(loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'));
    }
    if (!((window.jspdf && window.jspdf.jsPDF) || window.jsPDF)){
      tasks.push(loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js'));
    }
    return Promise.all(tasks);
  }

  function getJsPdfCtor(){
    return (window.jspdf && window.jspdf.jsPDF) ? window.jspdf.jsPDF : (window.jsPDF || null);
  }

  function waitImages(root){
    try{
      var imgs = Array.prototype.slice.call(root.querySelectorAll('img'));
      if (!imgs.length) return Promise.resolve();
      return Promise.all(imgs.map(function(img){
        return new Promise(function(resolve){
          var done = false;
          var finish = function(){ if (done) return; done = true; resolve(); };
          var timeoutId = setTimeout(finish, 5000);
          try { img.loading = 'eager'; } catch(_){}
          try { img.decoding = 'sync'; } catch(_){}
          if (img.complete && (img.naturalWidth || img.naturalHeight)){
            clearTimeout(timeoutId);
            finish();
            return;
          }
          img.onload = function(){ clearTimeout(timeoutId); finish(); };
          img.onerror = function(){ clearTimeout(timeoutId); finish(); };
          try{
            if (typeof img.decode === 'function'){
              img.decode().then(function(){ clearTimeout(timeoutId); finish(); }).catch(function(){ clearTimeout(timeoutId); finish(); });
            }
          }catch(_){}
        });
      }));
    }catch(_){ return Promise.resolve(); }
  }

  function collectBreakpointsDomPx(root){
    var pts = [];
    if (!root) return pts;
    function addTop(node){
      try{
        if (!node) return;
        var rootRect = root.getBoundingClientRect();
        var rect = node.getBoundingClientRect();
        var y = rect.top - rootRect.top;
        if (isFinite(y) && y > 8) pts.push(y);
      }catch(_){}
    }
    try{
      Array.prototype.slice.call(root.querySelectorAll('section, table, table tbody tr')).forEach(addTop);
    }catch(_){}
    pts.sort(function(a, b){ return a - b; });
    var dedup = [];
    for (var i = 0; i < pts.length; i++){
      if (!dedup.length || Math.abs(pts[i] - dedup[dedup.length - 1]) > 3) dedup.push(pts[i]);
    }
    return dedup;
  }

  function collectGapBreakpointsDomPx(root){
    var pts = [];
    if (!root || !root.children || !root.children.length) return pts;
    try{
      var rootRect = root.getBoundingClientRect();
      var blocks = Array.prototype.slice.call(root.children).filter(function(node){
        try{
          if (!node || node.nodeType !== 1) return false;
          var rect = node.getBoundingClientRect();
          return !!rect && rect.height > 0;
        }catch(_){ return false; }
      });
      for (var i = 0; i < blocks.length - 1; i++){
        var currentRect = blocks[i].getBoundingClientRect();
        var nextRect = blocks[i + 1].getBoundingClientRect();
        var gapStart = currentRect.bottom - rootRect.top;
        var gapEnd = nextRect.top - rootRect.top;
        var gapSize = gapEnd - gapStart;
        if (gapSize >= 8){
          pts.push(Math.round(gapStart + (gapSize / 2)));
        }
      }
    }catch(_){}
    pts.sort(function(a, b){ return a - b; });
    var dedup = [];
    for (var j = 0; j < pts.length; j++){
      if (!dedup.length || Math.abs(pts[j] - dedup[dedup.length - 1]) > 3) dedup.push(pts[j]);
    }
    return dedup;
  }

  function mapBreakpointsToCanvasPx(domBreakpointsPx, domHeightPx, canvasHeightPx){
    var out = [];
    if (!domHeightPx || !canvasHeightPx) return out;
    for (var i = 0; i < (domBreakpointsPx || []).length; i++){
      var val = Math.round((domBreakpointsPx[i] / domHeightPx) * canvasHeightPx);
      if (isFinite(val) && val > 0 && val < canvasHeightPx) out.push(val);
    }
    out.sort(function(a, b){ return a - b; });
    return out;
  }

  function pickBreakpointWithinRange(points, min, max){
    var best = null;
    var delta = Number.POSITIVE_INFINITY;
    for (var i = 0; i < (points || []).length; i++){
      var point = points[i];
      if (point < min || point > max) continue;
      var currentDelta = Math.abs(max - point);
      if (currentDelta < delta){
        delta = currentDelta;
        best = point;
      }
    }
    return best;
  }

  function pickTwoPageCutPx(canvasHeightPx, sliceHeightPx, breakpointsCanvasPx){
    var cutMinPx = Math.max(0, canvasHeightPx - sliceHeightPx);
    var cutMaxPx = Math.min(sliceHeightPx, canvasHeightPx);
    var yCutPx = cutMaxPx;
    var bestDelta = Number.POSITIVE_INFINITY;
    for (var i = 0; i < (breakpointsCanvasPx || []).length; i++){
      var c = breakpointsCanvasPx[i];
      if (c < cutMinPx || c > cutMaxPx) continue;
      var d = Math.abs(cutMaxPx - c);
      if (d < bestDelta){
        bestDelta = d;
        yCutPx = c;
      }
    }
    if (yCutPx < cutMinPx) yCutPx = cutMinPx;
    if (yCutPx > cutMaxPx) yCutPx = cutMaxPx;
    return yCutPx;
  }

  function selectCutChoice(canvasHeightPx, sliceHeightPx, gapBreakpointsCanvasPx, breakpointsCanvasPx){
    var cutMinPx = Math.max(0, canvasHeightPx - sliceHeightPx);
    var cutMaxPx = Math.min(sliceHeightPx, canvasHeightPx);
    var innerPaddingPx = Math.max(12, Math.floor(sliceHeightPx * 0.015));
    var gapCut = pickBreakpointWithinRange(gapBreakpointsCanvasPx || [], cutMinPx + innerPaddingPx, cutMaxPx - innerPaddingPx);
    if (gapCut === null) gapCut = pickBreakpointWithinRange(gapBreakpointsCanvasPx || [], cutMinPx, cutMaxPx);
    if (gapCut !== null){
      return { yCutPx: gapCut, usedGap: true };
    }
    var fallbackCut = pickBreakpointWithinRange(breakpointsCanvasPx || [], cutMinPx + innerPaddingPx, cutMaxPx - innerPaddingPx);
    if (fallbackCut === null) fallbackCut = pickBreakpointWithinRange(breakpointsCanvasPx || [], cutMinPx, cutMaxPx);
    return {
      yCutPx: (fallbackCut === null ? pickTwoPageCutPx(canvasHeightPx, sliceHeightPx, breakpointsCanvasPx || []) : fallbackCut),
      usedGap: false
    };
  }

  function makeCanvasSlice(sourceCanvas, yStartPx, outHeightPx){
    var sliceCanvas = document.createElement('canvas');
    sliceCanvas.width = sourceCanvas.width;
    sliceCanvas.height = Math.max(1, Math.floor(outHeightPx));
    var ctx = sliceCanvas.getContext('2d');
    try{
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, sliceCanvas.width, sliceCanvas.height);
    }catch(_){}
    var srcY = Math.max(0, Math.floor(yStartPx || 0));
    var srcHeight = Math.min(sliceCanvas.height, Math.max(0, sourceCanvas.height - srcY));
    if (srcHeight > 0){
      ctx.drawImage(sourceCanvas, 0, srcY, sourceCanvas.width, srcHeight, 0, 0, sourceCanvas.width, srcHeight);
    }
    return sliceCanvas;
  }

  async function appendRdoAsMaxTwoPages(doc, rootEl, options){
    options = options || {};
    var captureScale = options.captureScale || 2.4;
    var imageType = options.imageType || 'PNG';
    var imageMimeType = String(imageType).toUpperCase() === 'JPEG' ? 'image/jpeg' : 'image/png';
    var pdfImageCompression = options.pdfImageCompression || 'SLOW';
    var marginXmm = (typeof options.marginXmm === 'number') ? options.marginXmm : 5;
    var marginTopMm = (typeof options.marginTopMm === 'number') ? options.marginTopMm : 1.5;
    var marginBottomMm = (typeof options.marginBottomMm === 'number') ? options.marginBottomMm : 5;
    var pageAlreadyStarted = !!options.pageAlreadyStarted;
    var pagesAdded = 0;

    try{
      Array.prototype.slice.call(rootEl.querySelectorAll('img')).forEach(function(img){
        try { img.crossOrigin = 'anonymous'; } catch(_){}
      });
    }catch(_){}

    var gapBreakpointsDomPx = collectGapBreakpointsDomPx(rootEl);
    var breakpointsDomPx = collectBreakpointsDomPx(rootEl);
    var domHeightPx = 0;
    try{
      domHeightPx = Math.max(rootEl.scrollHeight || 0, (rootEl.getBoundingClientRect() || {}).height || 0);
    }catch(_){
      domHeightPx = rootEl && rootEl.scrollHeight ? rootEl.scrollHeight : 0;
    }

    var canvas = await window.html2canvas(rootEl, {
      scale: captureScale,
      useCORS: true,
      allowTaint: false,
      logging: false,
      backgroundColor: '#ffffff'
    });
    if (!canvas || !canvas.width || !canvas.height) return 0;

    var pageWidthMm = doc.internal.pageSize.getWidth();
    var pageHeightMm = doc.internal.pageSize.getHeight();
    var usableWidthMm = Math.max(1, pageWidthMm - (marginXmm * 2));
    var usableHeightMm = Math.max(1, pageHeightMm - (marginTopMm + marginBottomMm));
    var fullWidthPxPerMm = canvas.width / usableWidthMm;
    if (!isFinite(fullWidthPxPerMm) || fullWidthPxPerMm <= 0) fullWidthPxPerMm = 1;
    var fullWidthSliceHeightPx = Math.max(1, Math.floor(usableHeightMm * fullWidthPxPerMm));
    var drawWidthMm = usableWidthMm;
    var pxPerMm = fullWidthPxPerMm;
    var sliceHeightPx = fullWidthSliceHeightPx;
    var breakpointsCanvasPx = mapBreakpointsToCanvasPx(breakpointsDomPx, domHeightPx, canvas.height);
    var gapBreakpointsCanvasPx = mapBreakpointsToCanvasPx(gapBreakpointsDomPx, domHeightPx, canvas.height);
    var cutChoice = { yCutPx: canvas.height, usedGap: true };

    if (canvas.height > fullWidthSliceHeightPx){
      var maxTotalHeightMm = usableHeightMm * 2;
      var maxWidthMmForTwoPages = (maxTotalHeightMm * canvas.width) / canvas.height;
      var baseDrawWidthMm = Math.min(usableWidthMm, maxWidthMmForTwoPages * 0.965);
      if (!isFinite(baseDrawWidthMm) || baseDrawWidthMm <= 0) baseDrawWidthMm = usableWidthMm;
      var widthFactors = [1, 0.99, 0.98, 0.97, 0.955, 0.94, 0.925, 0.91];
      for (var wi = 0; wi < widthFactors.length; wi++){
        var candidateDrawWidthMm = baseDrawWidthMm * widthFactors[wi];
        if (!isFinite(candidateDrawWidthMm) || candidateDrawWidthMm <= 0) continue;
        var candidatePxPerMm = canvas.width / candidateDrawWidthMm;
        if (!isFinite(candidatePxPerMm) || candidatePxPerMm <= 0) continue;
        var candidateSliceHeightPx = Math.max(1, Math.floor(usableHeightMm * candidatePxPerMm));
        var candidateCutChoice = selectCutChoice(canvas.height, candidateSliceHeightPx, gapBreakpointsCanvasPx, breakpointsCanvasPx);
        drawWidthMm = candidateDrawWidthMm;
        pxPerMm = candidatePxPerMm;
        sliceHeightPx = candidateSliceHeightPx;
        cutChoice = candidateCutChoice;
        if (candidateSliceHeightPx >= canvas.height || candidateCutChoice.usedGap || wi === widthFactors.length - 1){
          break;
        }
      }
    }

    var xMm = marginXmm + ((usableWidthMm - drawWidthMm) / 2);

    function addSlice(sliceCanvas){
      if (!sliceCanvas || !sliceCanvas.width || !sliceCanvas.height) return;
      if (pageAlreadyStarted || pagesAdded > 0) doc.addPage();
      var imgData = sliceCanvas.toDataURL(imageMimeType);
      var renderHeightMm = Math.min(usableHeightMm, sliceCanvas.height / pxPerMm);
      doc.addImage(imgData, imageType, xMm, marginTopMm, drawWidthMm, renderHeightMm, undefined, pdfImageCompression);
      pagesAdded += 1;
      pageAlreadyStarted = true;
    }

    if (canvas.height <= sliceHeightPx){
      addSlice(makeCanvasSlice(canvas, 0, canvas.height));
      return pagesAdded;
    }

    var yCutPx = cutChoice && isFinite(cutChoice.yCutPx) ? cutChoice.yCutPx : pickTwoPageCutPx(canvas.height, sliceHeightPx, breakpointsCanvasPx);
    var page1HeightPx = Math.max(1, Math.min(canvas.height - 1, Math.round(yCutPx)));
    var page2StartY = page1HeightPx;
    var page2HeightPx = Math.max(0, canvas.height - page2StartY);
    if (page2HeightPx > sliceHeightPx){
      page2HeightPx = sliceHeightPx;
      page1HeightPx = Math.max(1, canvas.height - page2HeightPx);
      page2StartY = page1HeightPx;
    }

    addSlice(makeCanvasSlice(canvas, 0, page1HeightPx));
    if (page2HeightPx > 0){
      addSlice(makeCanvasSlice(canvas, page2StartY, page2HeightPx));
    }
    return pagesAdded;
  }

  async function fetchPages(pageUrls){
    var out = [];
    for (var i = 0; i < pageUrls.length; i++){
      setStatus('Carregando RDO ' + (i + 1) + ' de ' + pageUrls.length + '...');
      var resp = await fetch(pageUrls[i], { credentials: 'omit' });
      if (!resp.ok) throw new Error('Falha ao baixar RDO ' + (i + 1) + '.');
      var html = await resp.text();
      out.push(html);
    }
    return out;
  }

  async function exportPdf(){
    if (exportInProgress) return;
    exportInProgress = true;
    var config = window.__MOBILE_RDO_PDF_EXPORT__ || {};
    var pageUrls = Array.isArray(config.pageUrls) ? config.pageUrls : [];
    var fileName = String(config.fileName || 'RDOs.pdf').trim() || 'RDOs.pdf';
    currentFileName = fileName;
    setActionsVisible(false);
    revokeCurrentDownloadUrl();
    if (!pageUrls.length){
      setStatus('Nenhum RDO informado para exportação.', true);
      exportInProgress = false;
      return;
    }

    try{
      document.body.classList.add('exporting-pdf');
      setStatus('Carregando bibliotecas de PDF...');
      await ensurePdfLibs();

      var jsPDFCtor = getJsPdfCtor();
      if (!jsPDFCtor || !window.html2canvas){
        throw new Error('Bibliotecas de PDF não carregadas.');
      }

      var pagesHtml = await fetchPages(pageUrls);
      var container = document.createElement('div');
      container.style.position = 'fixed';
      container.style.left = '-10000px';
      container.style.top = '0';
      container.style.width = '210mm';
      container.style.background = '#fff';
      container.style.zIndex = '-1';
      document.body.appendChild(container);

      var doc = new jsPDFCtor({ unit: 'mm', format: 'a4', orientation: 'portrait' });
      var totalAdded = 0;

      for (var idx = 0; idx < pagesHtml.length; idx++){
        setStatus('Renderizando RDO ' + (idx + 1) + ' de ' + pagesHtml.length + '...');
        var docDom = new DOMParser().parseFromString(pagesHtml[idx], 'text/html');
        var pageEl = docDom.querySelector('#rdo') || docDom.querySelector('.page');
        if (!pageEl) continue;
        var imported = document.importNode(pageEl, true);
        try{ imported.classList.add('portrait'); }catch(_){}
        container.appendChild(imported);
        await waitImages(imported);
        var added = await appendRdoAsMaxTwoPages(doc, imported, {
          captureScale: Math.max(2.2, Math.min(3, (window.devicePixelRatio || 1) * 2)),
          imageType: 'PNG',
          pdfImageCompression: 'SLOW',
          marginXmm: 5,
          marginTopMm: 1.5,
          marginBottomMm: 5,
          pageAlreadyStarted: totalAdded > 0
        });
        totalAdded += added;
        try{ container.removeChild(imported); }catch(_){}
      }

      try{ document.body.removeChild(container); }catch(_){}

      if (!totalAdded){
        throw new Error('Nenhum RDO válido foi renderizado.');
      }

      setStatus('Gerando arquivo final...');
      var blob = doc.output && typeof doc.output === 'function' ? doc.output('blob') : null;
      if (blob) {
        currentDownloadUrl = URL.createObjectURL(blob);
        triggerDownload(currentDownloadUrl, fileName);
        setActionsVisible(true);
      } else {
        doc.save(fileName);
      }
      setStatus('PDF gerado. Se o download não começar, toque em "Baixar PDF agora".');
    }catch(err){
      console.error(err);
      setStatus(err && err.message ? err.message : 'Falha ao gerar PDF.', true);
      setActionsVisible(true);
    }finally{
      try{ document.body.classList.remove('exporting-pdf'); }catch(_){}
      exportInProgress = false;
    }
  }

  function bindActions(){
    try{
      var downloadBtn = document.getElementById('pdf-export-download-btn');
      if (downloadBtn){
        downloadBtn.addEventListener('click', function(){
          if (currentDownloadUrl){
            triggerDownload(currentDownloadUrl, currentFileName);
            setStatus('Tentando baixar novamente o PDF...');
            return;
          }
          exportPdf();
        });
      }
      var retryBtn = document.getElementById('pdf-export-retry-btn');
      if (retryBtn){
        retryBtn.addEventListener('click', function(){
          exportPdf();
        });
      }
    }catch(_){}
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){
      bindActions();
      exportPdf();
    }, { once: true });
  } else {
    bindActions();
    exportPdf();
  }

  window.addEventListener('beforeunload', function(){
    revokeCurrentDownloadUrl();
  });
})();
