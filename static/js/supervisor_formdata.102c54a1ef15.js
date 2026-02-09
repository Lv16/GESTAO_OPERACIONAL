// supervisor_formdata.js - helper externo para montar o FormData do modal Supervisor
// Define window.buildSupervisorFormDataExternal(form) para uso por rdo.js
(function(){
    'use strict';
    // Sempre definir/atualizar o builder externo para garantir a lógica de deduplicação

    function _qs(sel, ctx){ return (ctx || document).querySelector(sel); }
    function _qsa(sel, ctx){ return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
    function _closest(el, sel){ try { return el && el.closest ? el.closest(sel) : null; } catch(_) { return null; } }
    function _val(node){ return (node && typeof node.value === 'string') ? node.value.trim() : ''; }

    window.buildSupervisorFormDataExternal = function(form) {
        var fd = new FormData();
        if (!form) return fd;

        // 1) Passo genérico: anexar campos simples, evitando inputs que serão serializados explicitamente
        Array.prototype.forEach.call(form.elements, function(el){
            if (!el || !el.name) return;
            if (el.type === 'file') return; // arquivos tratados adiante
            if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
            // Pular inputs dentro de linhas dinâmicas de atividades/equipe
            if (_closest(el, '.activities-row, .team-row')) return;
            // Pular inputs dentro dos wrappers (Supervisor e Editor) para evitar duplicação
            if (_closest(el, '#atividades-wrapper, #equipe-wrapper, #edit-atividades-wrapper, #edit-equipe-wrapper')) return;
            // Pular EC para serializar de forma controlada depois
            if (el.name === 'entrada_confinado[]' || el.name === 'entrada_confinado' || el.name === 'saida_confinado[]' || el.name === 'saida_confinado') return;
            // Pular quaisquer nomes de campos de atividades/equipe mesmo que fora do wrapper (ex.: templates escondidos)
            if (/^(atividade_|equipe_)/.test(el.name)) return;
            fd.append(el.name, el.value);
        });

        // 2) Fotos (enviar cada arquivo uma única vez para evitar payload gigante)
        (function(){
            var files = [];
            var inputFotos = _qsa('input[type=file][name="fotos"]', form);
            if (inputFotos && inputFotos.length) {
                inputFotos.forEach(function(inp){ if (inp.files && inp.files.length) Array.prototype.forEach.call(inp.files, function(f){ files.push(f); }); });
            }
            if (!files.length) {
                for (var i=1;i<=5;i++) {
                    var fIn = _qs('input[type=file][name="foto' + i + '"]', form);
                    if (fIn && fIn.files && fIn.files.length) files.push(fIn.files[0]);
                }
            }
            files.forEach(function(f){
                try { fd.append('fotos', f); } catch(e){}
            });
        })();

        // 3) Atividades — serialização explícita com deduplicação por tupla completa
        (function(){
            try { if (typeof fd.delete === 'function') { fd.delete('atividade_nome[]'); fd.delete('atividade_inicio[]'); fd.delete('atividade_fim[]'); fd.delete('atividade_comentario_pt[]'); fd.delete('atividade_comentario_en[]'); } } catch(_){ }
            var seen = new Set();
            var rows = [];
            // Priorizar Editor se presente, depois Supervisor (ordem de leitura preservada)
            rows = rows.concat(_qsa('#edit-atividades-wrapper .activities-row', form));
            rows = rows.concat(_qsa('#atividades-wrapper .activities-row', form));
            rows.forEach(function(row){
                var nome = _val(row.querySelector('[name="atividade_nome[]"]')) || _val(row.querySelector('[name="atividade_nome"]'));
                var ini  = _val(row.querySelector('[name="atividade_inicio[]"]')) || _val(row.querySelector('[name="atividade_inicio"]'));
                var fim  = _val(row.querySelector('[name="atividade_fim[]"]')) || _val(row.querySelector('[name="atividade_fim"]'));
                var cpt  = _val(row.querySelector('[name="atividade_comentario_pt[]"]')) || _val(row.querySelector('[name="atividade_comentario_pt"]'));
                var cen  = _val(row.querySelector('[name="atividade_comentario_en[]"]')) || _val(row.querySelector('[name="atividade_comentario_en"]'));
                // Ignorar linhas completamente vazias
                if (!nome && !ini && !fim && !cpt && !cen) return;
                var key = [nome, ini, fim, cpt, cen].join('||');
                if (seen.has(key)) return; // deduplicar entradas idênticas
                seen.add(key);
                fd.append('atividade_nome[]', nome);
                fd.append('atividade_inicio[]', ini);
                fd.append('atividade_fim[]', fim);
                fd.append('atividade_comentario_pt[]', cpt);
                fd.append('atividade_comentario_en[]', cen);
            });
        })();

        // 4) Equipe — serialização explícita com deduplicação
        (function(){
            try { if (typeof fd.delete === 'function') { fd.delete('equipe_pessoa_id[]'); fd.delete('equipe_nome[]'); fd.delete('equipe_funcao[]'); fd.delete('equipe_em_servico[]'); } } catch(_){ }
            var seen = new Set();
            var pobCount = 0;
            var rows = [];
            rows = rows.concat(_qsa('#edit-equipe-wrapper .team-row', form));
            rows = rows.concat(_qsa('#equipe-wrapper .team-row', form));
            rows.forEach(function(row){
                var pidEl = row.querySelector('[name="equipe_pessoa_id[]"]') || row.querySelector('[name="equipe_pessoa_id"]');
                var nomeEl = row.querySelector('input[name="equipe_nome[]"]') || row.querySelector('input[name="equipe_nome"]') || row.querySelector('select[name="equipe_nome[]"]') || row.querySelector('select[name="equipe_nome"]');
                var funcEl = row.querySelector('input[name="equipe_funcao[]"]') || row.querySelector('input[name="equipe_funcao"]') || row.querySelector('select[name="equipe_funcao[]"]') || row.querySelector('select[name="equipe_funcao"]');
                var pid = _val(pidEl);
                var nom = _val(nomeEl);
                var fun = _val(funcEl);
                var srv = _val(row.querySelector('[name="equipe_em_servico[]"]')) || _val(row.querySelector('[name="equipe_em_servico"]'));

                // Se o nome vier de <select>, preferir o data-id da opção selecionada
                try {
                    var nomeSel = row.querySelector('select[name="equipe_nome[]"]') || row.querySelector('select[name="equipe_nome"]');
                    if (nomeSel) {
                        var opt = (nomeSel.options && nomeSel.selectedIndex >= 0) ? nomeSel.options[nomeSel.selectedIndex] : null;
                        var optPid = opt && (opt.getAttribute('data-id') || (opt.dataset && opt.dataset.id));
                        if (optPid != null && String(optPid).trim() !== '') {
                            pid = String(optPid).trim();
                        } else {
                            pid = '';
                        }
                        if (pidEl) pidEl.value = pid;
                    }
                } catch(_){ }
                if (!pid && !nom && !fun && !srv) return;
                var key = [pid, nom, fun, srv].join('||');
                if (seen.has(key)) return;
                seen.add(key);
                pobCount += 1;
                fd.append('equipe_pessoa_id[]', pid);
                fd.append('equipe_nome[]', nom);
                fd.append('equipe_funcao[]', fun);
                fd.append('equipe_em_servico[]', srv);
            });
            try {
                if (typeof fd.set === 'function') fd.set('pob', String(pobCount));
                else fd.append('pob', String(pobCount));
            } catch(_){ }
        })();

        // 5) EC (Entradas/Saídas de Espaço Confinado) — anexar de forma controlada
        (function(){
            try { if (typeof fd.delete === 'function') { fd.delete('entrada_confinado[]'); fd.delete('saida_confinado[]'); } } catch(_){ }
            _qsa('input[name="entrada_confinado[]"], input[name="entrada_confinado"]', form).forEach(function(e){ if (e && e.value !== null && e.value !== undefined && String(e.value).trim() !== '') fd.append('entrada_confinado[]', String(e.value).trim()); });
            _qsa('input[name="saida_confinado[]"], input[name="saida_confinado"]', form).forEach(function(s){ if (s && s.value !== null && s.value !== undefined && String(s.value).trim() !== '') fd.append('saida_confinado[]', String(s.value).trim()); });
        })();

        // Flag de versão/diagnóstico
        try {
            fd.__rdo_builder = 'external_v2_dedupe';
            fd.__rdo_external = true;
        } catch(_){ }
        // Log opcional: defina window.__RDO_DEBUG=true para imprimir contagem de chaves
        try {
            if (window.__RDO_DEBUG) {
                var counts = {};
                try {
                    // FormData#forEach não é suportado em todos os navegadores antigos; fallback iterável
                    if (typeof fd.forEach === 'function') {
                        fd.forEach(function(_, k){ counts[k] = (counts[k]||0) + 1; });
                    } else if (typeof fd.entries === 'function') {
                        var it = fd.entries(); var n = it.next();
                        while (!n.done) { var k = n.value && n.value[0]; counts[k] = (counts[k]||0) + 1; n = it.next(); }
                    }
                } catch(_){ }
                console.log('[RDO] FormData keys count (external builder):', counts);
            }
        } catch(_){ }
        return fd;
    };
})();
