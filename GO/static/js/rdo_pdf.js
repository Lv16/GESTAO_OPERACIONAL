// Inserir botão flutuante
;(function(){
	function loadScript(src, cb){
		var s = document.createElement('script');
		s.src = src;
		s.onload = cb;
		s.onerror = function(){ console.error('Falha ao carregar', src); };
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

		// Opções para html2pdf
		// Detecta orientação natural do elemento (largura x altura) e escolhe portrait/landscape.
	var isPortrait = (element.clientHeight > element.clientWidth);
		var orientation = isPortrait ? 'portrait' : 'landscape';
		var jsPDFoptions = { unit: 'mm', format: 'a4', orientation: orientation };

		var opt = {
			margin:       isPortrait ? 6 : 8, // mm (slightly smaller margins in portrait)
			filename:     'rdo.pdf',
			image:        { type: 'jpeg', quality: 0.98 },
			html2canvas:  { scale: 2, useCORS: true, logging: false, allowTaint: false },
			jsPDF:        jsPDFoptions,
			pagebreak: { mode: ['avoid-all', 'css', 'legacy'], avoid: ['.photo-slot', '.photo-grid', '.section-block'] }
		};

		// Gera o PDF (aguarda imagens carregarem, aplica pagebreak avoid e marca a página como portrait quando aplicável)
		function generate(){
			// aplica classe portrait para que CSS específico entre em vigor antes da captura
			try{
				if (isPortrait) element.classList.add('portrait');
				else element.classList.remove('portrait');
			}catch(e){}

			if(window.html2pdf){
				window.html2pdf().set(opt).from(element).save();
			} else {
				alert('Biblioteca de exportação não carregada. Tentando carregar...');
				loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.9.3/html2pdf.bundle.min.js', function(){
					if(window.html2pdf){
						window.html2pdf().set(opt).from(element).save();
					} else {
						alert('Não foi possível carregar a biblioteca html2pdf.');
					}
				});
			}
		}
	// pequena espera para permitir que imagens embutidas terminem de carregar
	// aumentar timeout em portrait para dar mais tempo quando necessário
	var wait = isPortrait ? 1200 : 600;
	setTimeout(generate, wait);

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

