// Inserir botão flutuante
;(function(){
	function loadScript(src, cb){
		var s = document.createElement('script');
		s.src = src;
		s.onload = cb;
		s.onerror = function(){
			console.error('Falha ao carregar', src);
			try { cb && cb(new Error('load_failed')); } catch(e){}
		};
		document.head.appendChild(s);
	}

	function createButton(){
		// Evita criar múltiplos botões se já existir
		if (document.querySelector('.export-btn')) return;
		var btn = document.createElement('button');
		btn.className = 'export-btn';
		btn.textContent = 'Exportar PDF';
		btn.title = 'Exportar relatório como PDF';
		btn.addEventListener('click', onExport);
		// posição fixa no canto inferior direito
		btn.style.position = 'fixed';
		btn.style.right = '18px';
		btn.style.bottom = '18px';
		btn.style.zIndex = '999999';
		btn.style.padding = '10px 14px';
		btn.style.borderRadius = '6px';
		btn.style.background = '#78a533';
		btn.style.color = '#fff';
		btn.style.border = 'none';
		btn.style.cursor = 'pointer';
		btn.style.boxShadow = '0 6px 18px rgba(0,0,0,0.12)';
		document.body.appendChild(btn);
	}

	function onExport(){
		var element = document.querySelector('.page');
		if(!element){ alert('Elemento .page não encontrado'); return; }

		// Exportação determinística em 2 páginas:
		// 1) Clona o conteúdo para um container offscreen (evita interferência do overlay/scroll)
		// 2) Renderiza com html2canvas
		// 3) Corta o canvas em exatamente 2 fatias e grava no jsPDF (2 páginas)
		function ensureLibs(cb){
			// Prefer explicit libs (more reliable globals than html2pdf bundle)
			if (window.html2canvas && ((window.jspdf && window.jspdf.jsPDF) || window.jsPDF)) return cb();

			var pending = 2;
			function done(){ pending--; if (pending <= 0) cb(); }

			// html2canvas (sets window.html2canvas)
			if (!window.html2canvas){
				loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js', function(){ done(); });
			} else {
				done();
			}

			// jsPDF (sets window.jspdf.jsPDF)
			if (!((window.jspdf && window.jspdf.jsPDF) || window.jsPDF)){
				loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js', function(){ done(); });
			} else {
				done();
			}
		}

		function getJsPdfCtor(){
			return (window.jspdf && window.jspdf.jsPDF) ? window.jspdf.jsPDF : (window.jsPDF || null);
		}

		function mmToPx(mm){
			try{
				var div = document.createElement('div');
				div.style.height = String(mm) + 'mm';
				div.style.position = 'absolute';
				div.style.visibility = 'hidden';
				div.style.left = '-9999px';
				div.style.top = '0';
				document.body.appendChild(div);
				var px = div.getBoundingClientRect().height;
				document.body.removeChild(div);
				return px || 0;
			}catch(e){
				return 0;
			}
		}

		function exportAsTwoPages(){
			var elementForMeasure = element;
			// Detecta orientação natural do elemento (largura x altura) e escolhe portrait/landscape.
			var isPortrait = (elementForMeasure.clientHeight > elementForMeasure.clientWidth);
			var orientation = isPortrait ? 'portrait' : 'landscape';
			var jsPDFCtor = getJsPdfCtor();
			if (!jsPDFCtor || !window.html2canvas){
				alert('Biblioteca de exportação não carregada. Verifique bloqueio de scripts (CSP/adblock) e tente novamente.');
				return;
			}

			// Modo exportação: evita page-break e efeitos visuais que geram páginas vazias
			document.body.classList.add('exporting-pdf');

			// Container offscreen
			var host = document.createElement('div');
			host.style.position = 'fixed';
			host.style.left = '-10000px';
			host.style.top = '0';
			host.style.width = elementForMeasure.offsetWidth + 'px';
			host.style.background = '#fff';
			host.style.zIndex = '-1';

			var clone = elementForMeasure.cloneNode(true);
			// Garanta que o clone não esteja com transform/zoom de impressão
			clone.style.transform = 'none';
			clone.style.zoom = '1';
			clone.style.maxHeight = 'none';
			clone.style.overflow = 'visible';
			clone.style.width = elementForMeasure.offsetWidth + 'px';

			// Coletar possíveis pontos de quebra (em px do DOM do clone)
			function collectBreakpointsDomPx(root){
				var pts = [];
				function addTop(node){
					try{
						var rootRect = root.getBoundingClientRect();
						var r = node.getBoundingClientRect();
						var y = r.top - rootRect.top;
						if (isFinite(y) && y > 8) pts.push(y);
					}catch(e){}
				}
				// Início de seções
				Array.from(root.querySelectorAll('section')).forEach(addTop);
				// Início de tabelas (evita cortar cabeçalho)
				Array.from(root.querySelectorAll('table')).forEach(addTop);
				// Início de linhas (evita cortar linha ao meio)
				Array.from(root.querySelectorAll('table tbody tr')).forEach(addTop);
				// Ordenar e remover duplicatas próximas
				pts.sort(function(a,b){ return a-b; });
				var dedup = [];
				for (var i=0;i<pts.length;i++){
					if (!dedup.length || Math.abs(pts[i] - dedup[dedup.length-1]) > 3) dedup.push(pts[i]);
				}
				return dedup;
			}

			// Aplicar classe portrait quando necessário (para CSS existente)
			try{
				if (isPortrait) clone.classList.add('portrait');
				else clone.classList.remove('portrait');
			}catch(e){}

			host.appendChild(clone);
			document.body.appendChild(host);

			// Agora que o clone está no DOM, coletar pontos de quebra com medidas válidas
			var breakpointsDomPx = collectBreakpointsDomPx(clone);
			var cloneRectHeightPx = 0;
			try{ cloneRectHeightPx = clone.getBoundingClientRect().height || 0; }catch(e){}
			var cloneScrollHeightPx = clone.scrollHeight || 0;
			var cloneMeasuredHeightPx = Math.max(cloneRectHeightPx, cloneScrollHeightPx);

			// Configuração de página
			var marginMm = isPortrait ? 5 : 6;
			var doc = new jsPDFCtor({ unit: 'mm', format: 'a4', orientation: orientation });
			var pageWidthMm = doc.internal.pageSize.getWidth();
			var pageHeightMm = doc.internal.pageSize.getHeight();
			var usableWidthMm = pageWidthMm - (marginMm * 2);
			var usableHeightMm = pageHeightMm - (marginMm * 2);

			// Renderizar em canvas
			// Tenta reduzir problemas de imagem (CORS/taint)
			Array.from(clone.querySelectorAll('img')).forEach(function(img){
				try { img.crossOrigin = 'anonymous'; } catch(e){}
			});

			// Ajustes para reduzir tamanho do PDF: reduzir escala do canvas e usar JPEG comprimido
			var canvasScale = 1.25; // reduzir para diminuir resolução (ajuste se precisar mais qualidade)
			var jpgQuality = 0.78; // qualidade JPEG (0..1)
			window.html2canvas(clone, {
				scale: canvasScale,
				useCORS: true,
				allowTaint: false,
				logging: false,
				backgroundColor: '#ffffff'
			}).then(function(canvas){
				try{
					// ===== Garantir 2 páginas SEM cortar conteúdo =====
					// Se o conteúdo for alto demais para 2 páginas na largura total, reduzimos a largura
					// do desenho no PDF (mantendo proporção), para que a altura total caiba em 2 páginas.
					var maxTotalHeightMm = usableHeightMm * 2;
					var maxWidthMmForTwoPages = (maxTotalHeightMm * canvas.width) / canvas.height;
					// Use a largura total quando possível; senão, reduza (com pequena folga)
					var drawWidthMm = Math.min(usableWidthMm, maxWidthMmForTwoPages * 0.98);
					if (!isFinite(drawWidthMm) || drawWidthMm <= 0) drawWidthMm = usableWidthMm;

					// Conversão mm->px baseada na largura efetiva do desenho
					var pxPerMm = canvas.width / drawWidthMm;
					var sliceHeightPx = Math.floor(usableHeightMm * pxPerMm);
					if (sliceHeightPx <= 0) sliceHeightPx = canvas.height;

					// Centralizar horizontalmente quando drawWidthMm < usableWidthMm
					var xMm = marginMm + ((usableWidthMm - drawWidthMm) / 2);

					// Converter breakpoints DOM(px) -> canvas(px)
					var breakpointsCanvasPx = [];
					var mapHeightPx = cloneMeasuredHeightPx;
					if (mapHeightPx > 0 && isFinite(canvas.height)){
						for (var bi=0; bi<breakpointsDomPx.length; bi++){
							var yc = Math.round((breakpointsDomPx[bi] / mapHeightPx) * canvas.height);
							if (isFinite(yc)) breakpointsCanvasPx.push(yc);
						}
						breakpointsCanvasPx.sort(function(a,b){ return a-b; });
					}

					// Escolher um ponto de quebra seguro (entre as 2 páginas)
					// Regras:
					// - aplicar uma pequena sobreposição entre páginas para evitar cortes por arredondamento
					var overlapMm = 2; // ~2mm de sobreposição
					var overlapPx = Math.max(0, Math.round(overlapMm * pxPerMm));
					// não exagerar: até 8% da altura útil
					overlapPx = Math.min(overlapPx, Math.floor(sliceHeightPx * 0.08));
					// - yCut >= (canvas.height - (sliceHeightPx - overlapPx)) para garantir que a página 2 alcance o rodapé
					// - yCut <= sliceHeightPx para evitar perder topo na página 1
					// - Preferir o breakpoint mais próximo de sliceHeightPx (sem ultrapassar)
					var cutMinPx = Math.max(0, canvas.height - (sliceHeightPx - overlapPx));
					var cutMaxPx = Math.min(sliceHeightPx, canvas.height);
					var yCutPx = cutMaxPx;
					for (var ci = breakpointsCanvasPx.length - 1; ci >= 0; ci--){
						var c = breakpointsCanvasPx[ci];
						if (c <= cutMaxPx && c >= cutMinPx){
							yCutPx = c;
							break;
						}
					}
					// Pequena margem de segurança para cortar ANTES do breakpoint (evita palavra cortada)
					var safetyMm = 1; // ~1mm
					var safetyPx = Math.max(0, Math.round(safetyMm * pxPerMm));
					yCutPx = yCutPx - safetyPx;
					// Garantia final de limites
					if (yCutPx < cutMinPx) yCutPx = cutMinPx;
					if (yCutPx > cutMaxPx) yCutPx = cutMaxPx;

					// Para não cortar elementos no meio, renderizamos:
					// - Página 1: janela [yCut - sliceHeight, yCut]
					// - Página 2: janela [yCut, yCut + sliceHeight]
					var page1StartY = Math.round(yCutPx - sliceHeightPx);
					// Página 2 começa um pouco antes para sobrepor (evita cortes por arredondamento)
					var page2StartY = Math.round(yCutPx - overlapPx);

					function makeSlice(yStart){
						var slice = document.createElement('canvas');
						slice.width = canvas.width;
						slice.height = sliceHeightPx;
						var ctx = slice.getContext('2d');
						// fundo branco
						ctx.fillStyle = '#fff';
						ctx.fillRect(0, 0, slice.width, slice.height);
						var srcY = Math.max(0, yStart);
						var dstY = Math.max(0, -yStart);
						var srcH = Math.min(sliceHeightPx - dstY, canvas.height - srcY);
						if (srcH > 0){
							ctx.drawImage(canvas, 0, srcY, canvas.width, srcH, 0, dstY, canvas.width, srcH);
						}
						return slice;
					}

					// Sempre gerar exatamente 2 páginas (com quebra segura)
					doc.setPage(1);
					var sliceCanvas1 = makeSlice(page1StartY);
					// PNG evita artefatos de compressão/linhas finas que podem aparecer em JPEG
					// usar JPEG para compressão (menor tamanho que PNG)
					var imgData1 = sliceCanvas1.toDataURL('image/jpeg', jpgQuality);
					doc.addImage(imgData1, 'JPEG', xMm, marginMm, drawWidthMm, usableHeightMm);
					doc.addPage();
					var sliceCanvas2 = makeSlice(page2StartY);
					var imgData2 = sliceCanvas2.toDataURL('image/jpeg', jpgQuality);
					doc.addImage(imgData2, 'JPEG', xMm, marginMm, drawWidthMm, usableHeightMm);

					// Montar nome do arquivo no formato: RDO-<OS>-<DATA>.pdf
					try{
						function normalizeText(s){
							try{ return String(s||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase(); }catch(e){ return String(s||'').toLowerCase(); }
						}
						function getFieldFromInfoTable(headerKey){
							try{
								var table = document.querySelector('.general-info-azul table');
								if (!table) return null;
								var ths = table.querySelectorAll('thead th');
								var idx = -1;
								for (var i=0;i<ths.length;i++){
									var txt = ths[i].textContent || '';
									if (normalizeText(txt).indexOf(normalizeText(headerKey)) !== -1){ idx = i; break; }
								}
								if (idx === -1) return null;
								var td = table.querySelector('tbody tr td:nth-child(' + (idx+1) + ')');
								return td ? td.textContent.trim() : null;
							}catch(e){ return null; }
						}

						var osNumber = getFieldFromInfoTable('os') || getFieldFromInfoTable('os nº') || getFieldFromInfoTable('os no') || '';
						var dateRaw = getFieldFromInfoTable('data') || '';

						// Formatar data para YYYY-MM-DD quando possível (aceita DD/MM/YYYY ou ISO)
						var dateForFilename = '';
						if (dateRaw){
							var m = dateRaw.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
							if (m){
								var d = String(m[1]).padStart(2,'0');
								var mo = String(m[2]).padStart(2,'0');
								var y = String(m[3]); if (y.length === 2) y = '20' + y;
								// formato Brasil: DD-MM-YYYY
								dateForFilename = d + '-' + mo + '-' + y;
							} else {
								var m2 = dateRaw.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
								if (m2){ dateForFilename = String(m2[3]).padStart(2,'0') + '-' + String(m2[2]).padStart(2,'0') + '-' + m2[1]; }
								else { dateForFilename = dateRaw.replace(/\s+/g,'_').replace(/[^0-9A-Za-z_\-]/g,''); }
							}
						}
						if (!dateForFilename){ var now = new Date(); dateForFilename = String(now.getDate()).padStart(2,'0') + '-' + String(now.getMonth()+1).padStart(2,'0') + '-' + now.getFullYear(); }
						if (!osNumber) osNumber = 'unknown';
						// limpar caracteres indesejados da OS
						osNumber = String(osNumber).trim().replace(/\s+/g,'').replace(/[^0-9A-Za-z\-_.]/g,'');
						var filename = 'RDO-' + osNumber + '-' + dateForFilename + '.pdf';
						doc.save(filename);
					}catch(e){
						// fallback simples
						try{ doc.save('rdo.pdf'); }catch(_){ }
					}
				}catch(e){
					console.error(e);
					alert('Falha ao gerar PDF.');
				}
			}).catch(function(err){
				console.error(err);
				alert('Falha ao renderizar para PDF. Se houver imagens externas/bloqueadas, tente remover fotos ou permitir carregamento de imagens/CORS e tente novamente.');
			}).finally(function(){
				try{
					document.body.classList.remove('exporting-pdf');
					if (host && host.parentNode) host.parentNode.removeChild(host);
				}catch(e){}
			});
		}

		ensureLibs(exportAsTwoPages);
		return;

		// (fluxo antigo removido) 

	}

	// Criar botão e pré-carregar lib
	function init(){
		try{
			createButton();
			loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.9.3/html2pdf.bundle.min.js', function(){
				console.info('html2pdf carregado');
			});
		}catch(e){ console.error('rdo_pdf init failed', e); }
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		// DOM já pronto
		init();
	}

	// Expor API simples para acionamento manual
	window.rdoPdfExport = onExport;
})();

