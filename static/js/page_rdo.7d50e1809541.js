(function(){
    'use strict';

    // Simple controller to show the printable page (#rdo) only when user clicks a View button
    // Usage: any button with class .action-btn.view (existing in the table rows) will open the page

    function qs(sel, ctx){ try { return (ctx || document).querySelector(sel); } catch(e) { return null; } }
    function qsa(sel, ctx){ try { return Array.from((ctx || document).querySelectorAll(sel)); } catch(e) { return []; } }

    // Interpretador tolerante de valores booleanos vindos do backend
    function parseBoolish(v){
        if (v === true) return true;
        if (v === false) return false;
        if (v === 1 || v === '1') return true;
        if (v === 0 || v === '0') return false;
        if (typeof v === 'string'){
            var s = v.trim().toLowerCase();
            if (s === 'sim' || s === 's' || s === 'true' || s === 'yes' || s === 'y') return true;
            if (s === 'nao' || s === 'não' || s === 'n' || s === 'false' || s === 'no') return false;
        }
        return null;
    }

    var page = qs('#rdo');
    // Do NOT return early: the page template (`#rdo`) exists only on the dedicated
    // rdo_page view. We still want the delegated click handler on listings to work
    // (it opens the server-rendered `/rdo/<id>/page/`). Functions that require
    // `page` already defensively check for its presence.
    if (!page) page = null;

    // ===== Force print into exactly 2 pages (A4 landscape) =====
    // Strategy:
    // - CSS limits the printable container height to 2 pages and applies a CSS var --print-zoom.
    // - Here we compute --print-zoom before printing, based on current DOM height.
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

    function computeTwoPageZoom(el){
        try{
            if (!el) return 1;
            // Must match CSS @page margin and A4 landscape height.
            var marginMm = 6;
            var pageHeightMm = 210;
            var usablePerPageMm = pageHeightMm - (marginMm * 2);
            var targetMm = usablePerPageMm * 2;
            var targetPx = mmToPx(targetMm);
            if (!targetPx) return 1;
            var actualPx = el.scrollHeight || el.getBoundingClientRect().height || 0;
            if (!actualPx) return 1;
            var z = targetPx / actualPx;
            // keep a small safety margin
            z = z * 0.98;
            // Avoid zero/NaN
            if (!isFinite(z) || z <= 0) return 1;
            // Allow strong squeezing if needed
            return Math.min(1, z);
        }catch(e){
            return 1;
        }
    }

    var _prevPrintZoom = null;
    function applyPrintZoom(){
        try{
            if (!page) return;
            _prevPrintZoom = document.documentElement.style.getPropertyValue('--print-zoom');
            var z = computeTwoPageZoom(page);
            document.documentElement.style.setProperty('--print-zoom', String(z));
        }catch(e){}
    }
    function resetPrintZoom(){
        try{
            if (_prevPrintZoom === null) {
                document.documentElement.style.removeProperty('--print-zoom');
            } else {
                document.documentElement.style.setProperty('--print-zoom', _prevPrintZoom);
            }
            _prevPrintZoom = null;
        }catch(e){}
    }

    // Hook browser printing (Ctrl+P or window.print)
    window.addEventListener('beforeprint', applyPrintZoom);
    window.addEventListener('afterprint', resetPrintZoom);

    // Create an overlay wrapper to host the page in a modal-like view
    // use a tighter namespace to avoid conflicts with other page elements/CSS
    var overlayId = 'rdo-print-overlay';
    var overlay = qs('#' + overlayId);
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = overlayId;
        overlay.style.position = 'fixed';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.background = 'rgba(0,0,0,0.6)';
        overlay.style.zIndex = '99999';
        overlay.style.display = 'none';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
    overlay.style.overflow = 'auto';
    document.body.appendChild(overlay);
    // Don't close on outside click anymore; use explicit buttons or ESC to close
    }

    // Helpers to populate printable with backend data
    function pick(obj, keys){
        try{
            for (var i=0;i<keys.length;i++){
                var k = keys[i];
                if (Object.prototype.hasOwnProperty.call(obj, k)){
                    var v = obj[k];
                    // treat common placeholders as empty so backend/model values can be used
                    if (v !== undefined && v !== null && v !== ''){
                        try{
                            if (typeof v === 'string'){
                                var s = v.trim().toLowerCase();
                                if (s === '' || s === '-' || s === '—' || s === 'none' || s === 'null') {
                                    // placeholder -> skip
                                } else {
                                    return v;
                                }
                            } else {
                                return v;
                            }
                        }catch(e){ return v; }
                    }
                }
            }
        }catch(e){}
        return '';
    }
    function populatePrintable(rdo){
        try{
            var root = page; if (!root || !rdo) return;

            // General info (Contrato/PO, Empresa, Unidade, Data, RDO Nº, OS Nº)
            try {
                var row = root.querySelector('.general-info tbody tr');
                if (row){
                    var cells = row.querySelectorAll('td');
                    if (cells.length >= 6){
                        cells[0].textContent = rdo.po || '';
                        cells[1].textContent = rdo.empresa || '';
                        cells[2].textContent = rdo.unidade || rdo.embarcacao || '';
                        cells[3].textContent = rdo.data_inicio || '';
                        cells[4].textContent = rdo.rdo || '';
                        cells[5].textContent = rdo.numero_os || '';
                    }
                }
            } catch(e){}

            // PT table (status, turnos, números)
            try{
                var ptTable = root.querySelector('.table.table-pt tbody tr');
                if (ptTable){
                    var tds = ptTable.querySelectorAll('td');
                    if (tds.length >= 5){
                        tds[0].textContent = (rdo.exist_pt === true ? 'Sim' : (rdo.exist_pt === false ? 'Não' : ''));
                        var turnos = Array.isArray(rdo.select_turnos) ? rdo.select_turnos.join(', ') : '';
                        tds[1].textContent = turnos || '';
                        tds[2].textContent = rdo.pt_manha || '';
                        tds[3].textContent = rdo.pt_tarde || '';
                        tds[4].textContent = rdo.pt_noite || '';
                    }
                }
            } catch(e){}

            // Activities table
            try{
                var candidateTables = Array.from(root.querySelectorAll('.section-block .table'));
                var actBody = null;
                for (var i=0;i<candidateTables.length;i++){
                    var th = candidateTables[i].querySelector('thead th');
                    if (th && /Atividades/i.test(th.textContent || '')){
                        actBody = candidateTables[i].querySelector('tbody');
                        break;
                    }
                }
                if (actBody){
                    actBody.innerHTML = '';
                    (rdo.atividades || []).forEach(function(a){
                        var tr = document.createElement('tr');
                        function td(text){ var el=document.createElement('td'); el.textContent = text||''; return el; }
                        tr.appendChild(td(a.atividade_label || a.atividade || ''));
                        tr.appendChild(td(a.inicio || ''));
                        tr.appendChild(td(a.fim || ''));
                        tr.appendChild(td(a.comentario_pt || ''));
                        tr.appendChild(td(a.comentario_en || ''));
                        actBody.appendChild(tr);
                    });
                }
            } catch(e){}

            // Tank info
            try{
                var tankSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /INFORMAÇÕES DO\(S\) TANQUE\(S\)/i.test(sec.textContent || '');
                });
                if (tankSection){
                    var tbody = tankSection.querySelector('tbody');
                    try {
                        // If payload provides an array of tanques, render each as a row (with extra per-tank columns)
                        if (Array.isArray(rdo.tanques) && rdo.tanques.length && tbody){
                            tbody.innerHTML = '';
                            rdo.tanques.forEach(function(t){
                                try {
                                    // Pick values with tolerant fallbacks
                                    var codigo = (t && (t.codigo || t.tanque_codigo || t.tank_code)) || '-';
                                    var volume = (t && (t.volume || t.volume_tanque_exec || t.volume_m3)) || '-';
                                    var patamar = (t && (t.patamar || t.patamares)) || '-';
                                    var tipo = (t && (t.tipo_tanque || t.tipo)) || '-';
                                    var num_comp = (t && (t.numero_compartimentos || t.numero_compartimento)) || '-';
                                    var gavetas = (t && (t.gavetas || t.gaveta)) || '-';
                                    var percentuais = (t && (t.percentuais || t.percentual || t.percentual_percent)) || '-';
                                    // Preferir sempre o sentido definido no RDO; se ausente, aceitar valor por-tanque como fallback
                                    var rdoSentido = null;
                                    try {
                                        function _sentidoToLabel(raw){
                                            try{
                                                if (raw === null || typeof raw === 'undefined') return null;
                                                // aceitar booleanos explícitos ou flags textuais
                                                if (raw === true || raw === 'true' || raw === 1 || raw === '1') return 'Vante > Ré';
                                                if (raw === false || raw === 'false' || raw === 0 || raw === '0') return 'Ré > Vante';
                                                var s = String(raw).toLowerCase().trim();
                                                // tokens canônicos
                                                if (s === 'vante > ré' || s === 'vante > re' || s === 'vante > ré') return 'Vante > Ré';
                                                if (s === 'ré > vante' || s === 're > vante' || s === 'ré > vante') return 'Ré > Vante';
                                                if (s.indexOf('bombordo') > -1 && s.indexOf('boreste') > -1){
                                                    // distinguir direção quando possível
                                                    if (s.indexOf('boreste') < s.indexOf('bombordo')) return 'Boreste < Bombordo';
                                                    return 'Bombordo > Boreste';
                                                }
                                                if (s.indexOf('vante') > -1 && (s.indexOf('ré') > -1 || s.indexOf('re') > -1)) return 'Vante > Ré';
                                                if ((s.indexOf('ré') > -1 || s.indexOf('re') > -1) && s.indexOf('vante') > -1) return 'Ré > Vante';
                                                // fallback: return original string trimmed
                                                return String(raw);
                                            }catch(e){ return String(raw); }
                                        }
                                        if (typeof rdo.sentido_limpeza !== 'undefined' && rdo.sentido_limpeza !== null) {
                                            rdoSentido = _sentidoToLabel(rdo.sentido_limpeza);
                                        } else if (typeof rdo.sentido_label !== 'undefined' && rdo.sentido_label !== null) {
                                            rdoSentido = _sentidoToLabel(rdo.sentido_label);
                                        } else if (typeof rdo.sentido_limpeza_bool !== 'undefined' && rdo.sentido_limpeza_bool !== null) {
                                            rdoSentido = (rdo.sentido_limpeza_bool === true) ? 'Vante > Ré' : 'Ré > Vante';
                                        }
                                    } catch(e){ rdoSentido = null; }
                                    // Estrito: usar apenas o sentido definido no RDO; não usar fallback por-tanque
                                    var sentido = rdoSentido || '-';
                                    var servico = (t && t.servico_exec) || rdo.servico_exec || '-';
                                    var metodo = (t && t.metodo_exec) || rdo.metodo_exec || '-';
                                    var h2s = (t && (t.h2s_ppm || t.H2S_ppm)) || (rdo.h2s_ppm || rdo.H2S_ppm) || '-';
                                    var lel = (t && (t.lel || t.LEL)) || (rdo.lel || rdo.LEL) || '-';
                                    var co  = (t && (t.co_ppm || t.CO_ppm)) || (rdo.co_ppm || rdo.CO_ppm) || '-';
                                    var o2  = (t && (t.o2_percent || t.O2_percent)) || (rdo.o2_percent || rdo.O2_percent) || '-';
                                    var fotosCount = '-';
                                    try{
                                        if (t && Array.isArray(t.fotos)) fotosCount = t.fotos.length || 0;
                                        else if (Array.isArray(rdo.fotos)) fotosCount = rdo.fotos.length || 0;
                                    }catch(e){ fotosCount = '-'; }

                                    var tr = document.createElement('tr');
                                    function td(text){ var d = document.createElement('td'); d.textContent = (text !== undefined && text !== null ? text : ''); return d; }
                                    tr.appendChild(td(codigo));
                                    tr.appendChild(td(volume));
                                    tr.appendChild(td(patamar));
                                    tr.appendChild(td(tipo));
                                    tr.appendChild(td(num_comp));
                                    tr.appendChild(td(gavetas));
                                    // extra columns: percentuais, sentido, fotos
                                    tr.appendChild(td(percentuais));
                                    tr.appendChild(td(sentido));
                                    tr.appendChild(td(fotosCount));
                                    // extra columns: servico, metodo, h2s, lel, co, o2
                                    tr.appendChild(td(servico));
                                    tr.appendChild(td(metodo));
                                    tr.appendChild(td(h2s));
                                    tr.appendChild(td(lel));
                                    tr.appendChild(td(co));
                                    tr.appendChild(td(o2));
                                    tbody.appendChild(tr);
                                } catch(_){/* ignore single-tank row */}
                            });
                        } else if (tbody){
                            // Fallback: update the first existing row if present
                            var trow = tbody.querySelector('tr');
                            if (trow){
                                var tds = trow.querySelectorAll('td');
                                if (tds.length >= 6){
                                    tds[0].textContent = rdo.tanque_codigo || rdo.tanque || '';
                                    tds[1].textContent = rdo.volume_tanque_exec || rdo.volume || '';
                                    tds[2].textContent = rdo.patamares || rdo.patamar || '';
                                    tds[3].textContent = rdo.tipo_tanque || rdo.tipo || '';
                                    tds[4].textContent = rdo.numero_compartimentos || rdo.numero_compartimento || '';
                                    tds[5].textContent = rdo.gavetas || '';
                                    // if template contains extra columns, fill them too
                                    if (tds.length >= 9){
                                        tds[6].textContent = rdo.percentuais || rdo.percentual || '';
                                        tds[7].textContent = rdo.sentido_limpeza || '';
                                        tds[8].textContent = Array.isArray(rdo.fotos) ? rdo.fotos.length : '';
                                    }
                                    if (tds.length >= 15){
                                        tds[9].textContent  = rdo.servico_exec || '';
                                        tds[10].textContent = rdo.metodo_exec || '';
                                        tds[11].textContent = rdo.h2s_ppm || rdo.H2S_ppm || '';
                                        tds[12].textContent = rdo.lel || rdo.LEL || '';
                                        tds[13].textContent = rdo.co_ppm || rdo.CO_ppm || '';
                                        tds[14].textContent = rdo.o2_percent || rdo.O2_percent || '';
                                    }
                                }
                            }
                        }
                    } catch(e){}
                }
            } catch(e){}

            // Service info
            try{
                var svcSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /INFORMAÇÕES DO SERVIÇO/i.test(sec.textContent || '');
                });
                if (svcSection){
                    var thCount = (svcSection.querySelectorAll('thead th') || []).length;
                    // Só preenche automaticamente no layout simples de 2 colunas (Serviço | Método)
                    if (thCount === 2){
                        var row2 = svcSection.querySelector('tbody tr');
                        if (row2){
                            var c = row2.querySelectorAll('td');
                            if (c.length >= 2){
                                c[0].textContent = rdo.servico_exec || '';
                                c[1].textContent = rdo.metodo_exec || '';
                            }
                        }
                    }
                }
            } catch(e){}

            // Atmosfera (usar IDs se existirem e múltiplos fallbacks de chaves)
            try{
                var atmSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /ATMOSFERA DO TANQUE/i.test(sec.textContent || '');
                });
                if (atmSection){
                    // Primeiro, tente preencher via IDs (resiliente a mudanças no layout)
                    var elH2S = qs('#rdo-atm-h2s', root);
                    var elLEL = qs('#rdo-atm-lel', root);
                    var elCO  = qs('#rdo-atm-co', root);
                    var elO2  = qs('#rdo-atm-o2', root);

                    var h2s = pick(rdo, ['h2s_ppm','H2S_ppm','H2S','h2s','h2sPPM']);
                    var lel = pick(rdo, ['lel','LEL','lel_percent','LEL_percent']);
                    var co  = pick(rdo, ['co_ppm','CO_ppm','CO','co']);
                    var o2  = pick(rdo, ['o2_percent','O2_percent','o2','O2','O2_percentual']);

                    if (elH2S) elH2S.textContent = (h2s !== null ? h2s : '');
                    if (elLEL) elLEL.textContent = (lel !== null ? lel : '');
                    if (elCO)  elCO.textContent  = (co  !== null ? co  : '');
                    if (elO2)  elO2.textContent  = (o2  !== null ? o2  : '');

                    // Fallback: se IDs não existirem, localizar a linha de dados (segunda linha do tbody)
                    if (!elH2S || !elLEL || !elCO || !elO2){
                        var rows = atmSection.querySelectorAll('tbody tr');
                        var dataRow = null;
                        if (rows.length >= 2) dataRow = rows[1];
                        else {
                            // procurar a primeira linha que contenha >=4 tds
                            for (var r=0; r<rows.length; r++){
                                if (rows[r].querySelectorAll('td').length >= 4){ dataRow = rows[r]; break; }
                            }
                        }
                        if (dataRow){
                            var t = dataRow.querySelectorAll('td');
                            if (t.length >= 4){
                                t[0].textContent = (h2s !== null ? h2s : '');
                                t[1].textContent = (lel !== null ? lel : '');
                                t[2].textContent = (co  !== null ? co  : '');
                                t[3].textContent = (o2  !== null ? o2  : '');
                            }
                        }
                    }
                }
            } catch(e){}

            // Confined space
            try{
                var confSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /ACESSO AO ESPAÇO CONFINADO/i.test(sec.textContent || '');
                });
                if (confSection){
                    var rows = confSection.querySelectorAll('tbody tr');
                    if (rows.length >= 2){
                        var r1 = rows[0].querySelectorAll('td');
                        if (r1.length >= 8){
                            // interpretar valores booleanos de forma tolerante (aceita 'sim'/'nao', true/false, 'true'/'false', 1/0)
                            var confVal = parseBoolish(rdo.confinado);
                            if (confVal === true) r1[0].textContent = 'Sim';
                            else if (confVal === false) r1[0].textContent = 'Não';
                            else r1[0].textContent = '';
                            for (var i=1;i<=6;i++){
                                var v = (rdo.ec_times && rdo.ec_times['entrada_'+i]) || '';
                                if (r1[i+1]) r1[i+1].textContent = v || '';
                            }
                        }
                        var r2 = rows[1].querySelectorAll('td');
                        if (r2.length >= 8){
                            r2[0].textContent = rdo.operadores_simultaneos || '';
                            for (var j=1;j<=6;j++){
                                var sv = (rdo.ec_times && rdo.ec_times['saida_'+j]) || '';
                                if (r2[j+1]) r2[j+1].textContent = sv || '';
                            }
                        }
                    }
                }
            } catch(e){}

            // Production data (por tanque quando disponível)
            try{
                var prodSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /DADOS DE PRODUÇÃO/i.test(sec.textContent || '');
                });
                if (prodSection){
                    var tbody = prodSection.querySelector('tbody');
                    if (!tbody) throw new Error('tbody not found');

                    var tanquesArr = Array.isArray(rdo.tanques) ? rdo.tanques : null;
                    if (tanquesArr && tanquesArr.length){
                        // Reconstruir linhas por tanque
                        tbody.innerHTML = '';
                        var makeTd = function(text){ var td=document.createElement('td'); td.textContent = (text!=null && text!==undefined)? text : ''; return td; };

                        var sentidoLabel = function(t){
                            try{
                                function _sentidoToLabel(raw){
                                    try{
                                        if (raw === null || typeof raw === 'undefined') return null;
                                        if (raw === true || raw === 'true' || raw === 1 || raw === '1') return 'Vante > Ré';
                                        if (raw === false || raw === 'false' || raw === 0 || raw === '0') return 'Ré > Vante';
                                        var s = String(raw).toLowerCase().trim();
                                        if (s === 'vante > ré' || s === 'vante > re' || s === 'vante > ré') return 'Vante > Ré';
                                        if (s === 'ré > vante' || s === 're > vante' || s === 'ré > vante') return 'Ré > Vante';
                                        if (s.indexOf('bombordo') > -1 && s.indexOf('boreste') > -1){
                                            if (s.indexOf('boreste') < s.indexOf('bombordo')) return 'Boreste < Bombordo';
                                            return 'Bombordo > Boreste';
                                        }
                                        if (s.indexOf('vante') > -1 && (s.indexOf('ré') > -1 || s.indexOf('re') > -1)) return 'Vante > Ré';
                                        if ((s.indexOf('ré') > -1 || s.indexOf('re') > -1) && s.indexOf('vante') > -1) return 'Ré > Vante';
                                        return String(raw);
                                    }catch(e){ return String(raw); }
                                }
                                // Estrito: sempre retornar o sentido do RDO quando definido.
                                try {
                                    if (typeof rdo.sentido_limpeza !== 'undefined' && rdo.sentido_limpeza !== null) return _sentidoToLabel(rdo.sentido_limpeza);
                                    if (typeof rdo.sentido_label !== 'undefined' && rdo.sentido_label !== null) return _sentidoToLabel(rdo.sentido_label);
                                    if (typeof rdo.sentido_limpeza_bool !== 'undefined' && rdo.sentido_limpeza_bool !== null) return (rdo.sentido_limpeza_bool === true) ? 'Vante > Ré' : 'Ré > Vante';
                                } catch(e){}
                                // Se RDO não fornecer sentido, retornar vazio (não usar valor por-tanque)
                                return '';
                            }catch(e){ return ''; }
                        };

                        tanquesArr.forEach(function(t){
                            var tr = document.createElement('tr');
                            tr.appendChild(makeTd(sentidoLabel(t)));
                            tr.appendChild(makeTd(pick(t, ['total_liquido','total_liquidos','total_liquido_dia']) || rdo.total_liquido));
                            tr.appendChild(makeTd(pick(t, ['ensacamento_dia']) || rdo.ensacamento));
                            tr.appendChild(makeTd(pick(t, ['residuos_solidos']) || rdo.total_solidos));
                            tr.appendChild(makeTd(pick(t, ['tempo_bomba']) || rdo.tempo_bomba));
                            tr.appendChild(makeTd(pick(t, ['bombeio','bombeio_dia','bombeio_total']) || rdo.bombeio));
                            tr.appendChild(makeTd(pick(t, ['tambores_dia']) || rdo.tambores));
                            tr.appendChild(makeTd(pick(t, ['residuos_totais']) || rdo.total_residuos));
                            tbody.appendChild(tr);
                        });
                    } else {
                        // Layout simples: uma linha agregada (mantém comportamento anterior)
                        var prow = tbody.querySelector('tr');
                        if (prow){
                            var p = prow.querySelectorAll('td');
                            if (p.length >= 8){
                                var lbl = '';
                                try{
                                    function _sentidoToLabel(raw){
                                        try{
                                            if (raw === null || typeof raw === 'undefined') return '';
                                            if (raw === true || raw === 'true' || raw === 1 || raw === '1') return 'Vante > Ré';
                                            if (raw === false || raw === 'false' || raw === 0 || raw === '0') return 'Ré > Vante';
                                            var s = String(raw).toLowerCase().trim();
                                            if (s === 'vante > ré' || s === 'vante > re') return 'Vante > Ré';
                                            if (s === 'ré > vante' || s === 're > vante') return 'Ré > Vante';
                                            if (s.indexOf('bombordo') > -1 && s.indexOf('boreste') > -1){
                                                if (s.indexOf('boreste') < s.indexOf('bombordo')) return 'Boreste < Bombordo';
                                                return 'Bombordo > Boreste';
                                            }
                                            if (s.indexOf('vante') > -1 && (s.indexOf('ré') > -1 || s.indexOf('re') > -1)) return 'Vante > Ré';
                                            if ((s.indexOf('ré') > -1 || s.indexOf('re') > -1) && s.indexOf('vante') > -1) return 'Ré > Vante';
                                            return String(raw);
                                        }catch(e){ return String(raw); }
                                    }
                                    if (typeof rdo.sentido_limpeza !== 'undefined' && rdo.sentido_limpeza !== null) lbl = _sentidoToLabel(rdo.sentido_limpeza);
                                    else if (typeof rdo.sentido_label !== 'undefined' && rdo.sentido_label !== null) lbl = _sentidoToLabel(rdo.sentido_label);
                                    else if (typeof rdo.sentido_limpeza_bool !== 'undefined' && rdo.sentido_limpeza_bool !== null) lbl = (rdo.sentido_limpeza_bool === true) ? 'Vante > Ré' : 'Ré > Vante';
                                }catch(e){ lbl = (rdo.sentido_limpeza || rdo.sentido_label || ''); }
                                p[0].textContent = lbl || '';
                                p[1].textContent = (rdo.total_liquido != null ? rdo.total_liquido : '');
                                p[2].textContent = (rdo.ensacamento != null ? rdo.ensacamento : '');
                                p[3].textContent = (rdo.total_solidos != null ? rdo.total_solidos : '');
                                p[4].textContent = (rdo.tempo_bomba != null ? rdo.tempo_bomba : '');
                                p[5].textContent = (rdo.bombeio != null ? rdo.bombeio : '');
                                p[6].textContent = (rdo.tambores != null ? rdo.tambores : '');
                                p[7].textContent = (rdo.total_residuos != null ? rdo.total_residuos : '');
                            }
                        }
                    }
                }
            } catch(e){}

            // Notes & Planning
            try{
                var blocks = Array.from(root.querySelectorAll('.section-block'));
                var obs = blocks.find(function(sec){ return /OBSERVAÇÕES/i.test(sec.textContent||''); });
                if (obs){
                    var ps = obs.querySelectorAll('.note-column p');
                    if (ps.length >= 2){ ps[0].textContent = rdo.observacoes_pt || ''; ps[1].textContent = rdo.observacoes_en || ''; }
                }
                var plan = blocks.find(function(sec){ return /PLANEJAMENTO/i.test(sec.textContent||''); });
                if (plan){
                    var pp = plan.querySelectorAll('.note-column p');
                    if (pp.length >= 2){ pp[0].textContent = rdo.planejamento_pt || ''; pp[1].textContent = rdo.planejamento_en || ''; }
                }
            } catch(e){}

            // Team: rebuild table rows to list all members in groups of 3 (Nome/Função pairs)
            try{
                var teamSection = Array.from(root.querySelectorAll('.section-block')).find(function(sec){
                    return /INFORMAÇÕES DA EQUIPE ATIVA/i.test(sec.textContent || '');
                });
                if (teamSection){
                    var teamTable = teamSection.querySelector('table');
                    var tbody = teamTable && teamTable.querySelector('tbody');
                    if (tbody){
                        var equipe = Array.isArray(rdo.equipe) ? rdo.equipe.slice() : [];
                        if (!equipe.length){
                            // Não limpa o conteúdo estático quando não há dados
                        } else {
                            // limpar linhas atuais antes de popular
                            tbody.innerHTML = '';
                            // dividir em grupos de 3 membros por linha
                            for (var iTeam = 0; iTeam < equipe.length; iTeam += 3){
                                var trTeam = document.createElement('tr');
                                for (var j=0; j<3; j++){
                                    var m = equipe[iTeam + j] || {};
                                    // aceita variações de chaves vindo do backend
                                    var nome = m.nome || m.nome_completo || m.name || m.display_name || '';
                                    var func = m.funcao || m.funcao_label || m.funcao_nome || m.role || '';
                                    var tdNome = document.createElement('td');
                                    tdNome.textContent = nome;
                                    var tdFunc = document.createElement('td');
                                    tdFunc.textContent = func;
                                    trTeam.appendChild(tdNome);
                                    trTeam.appendChild(tdFunc);
                                }
                                tbody.appendChild(trTeam);
                            }
                        }
                    }
                }
            } catch(e){}

            // Photos
            try{
                var photosSection = root.querySelector('.section-block.photos .photo-grid');
                if (photosSection){
                    var slots = Array.from(photosSection.querySelectorAll('.photo-slot'));
                    slots.forEach(function(s){ s.innerHTML = ''; });
                    var list = rdo.fotos || [];
                    for (var m=0; m<Math.min(slots.length, list.length); m++){
                        var url = list[m];
                        if (!url) continue;
                        var img = document.createElement('img');
                        img.src = url;
                        img.alt = 'Foto '+(m+1);
                        // ensure good fit inside slot even without CSS rule
                        img.style.width = '100%';
                        img.style.height = '100%';
                        img.style.objectFit = 'cover';
                        slots[m].appendChild(img);
                    }
                }
            } catch(e){}
        }catch(e){ console.warn('populatePrintable failed', e); }
    }

    function fetchAndPopulate(rdoId){
        if (!rdoId) return Promise.resolve(false);
        var url = '/rdo/' + encodeURIComponent(rdoId) + '/detail/';
        return fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function(resp){ if (!resp.ok) throw new Error('fetch'); return resp.json(); })
            .then(function(data){ if (!data || !data.success) throw new Error('bad'); populatePrintable(data.rdo || {}); return true; })
            .catch(function(){ return false; });
    }

    // Move the page element into the overlay when showing to ensure it's above everything
    var pagePlaceholder = null;

    var _currentRdoId = null;
    function openPage(rdoId){
        try {
            if (!page) return;
            _currentRdoId = rdoId || null;
            if (!pagePlaceholder) {
                pagePlaceholder = document.createElement('div');
                pagePlaceholder.style.display = 'none';
                page.parentNode.insertBefore(pagePlaceholder, page);
            }
            overlay.style.display = 'flex';
            page.style.display = '';
            // make page scrollable within overlay
            page.style.maxHeight = '95vh';
            page.style.overflow = 'auto';
            // create a container for toolbar + page
            var container = document.createElement('div');
            container.id = overlayId + '-container';
            container.style.background = '#fff';
            container.style.borderRadius = '6px';
            container.style.boxShadow = '0 6px 30px rgba(0,0,0,0.3)';
            container.style.maxWidth = '1100px';
            container.style.width = '95%';
            container.style.maxHeight = '95vh';
            container.style.display = 'flex';
            container.style.flexDirection = 'column';
            // toolbar
            var toolbar = document.createElement('div');
            toolbar.style.padding = '8px 12px';
            toolbar.style.background = '#f5f5f5';
            toolbar.style.borderBottom = '1px solid #e0e0e0';
            toolbar.style.display = 'flex';
            toolbar.style.justifyContent = 'flex-end';
            toolbar.style.gap = '8px';

            var printBtn = document.createElement('button');
            printBtn.type = 'button';
            printBtn.className = 'page-rdo-print-btn';
            printBtn.textContent = 'Exportar PDF';
            printBtn.style.cursor = 'pointer';
            printBtn.addEventListener('click', function(){
                try {
                    // Use client-side print flow to preserve exact site styling
                    exportPrintable();
                } catch(e){ console.warn('export pdf failed', e); }
            });
                printBtn.addEventListener('click', function(){
                    try{
                        // If we have a current rdo id, open the backend print-only page.
                        var rid = _currentRdoId || null;
                        if (!rid) return alert('RDO não identificado para exportação');
                        var url = '/rdo/' + encodeURIComponent(rid) + '/print/?auto=1';

                        // Try to open in a new tab synchronously (should not be blocked because it's inside click handler).
                        var w = null;
                        try { w = window.open(url, '_blank'); } catch (e) { w = null; }
                        // If popup blocked or window.open failed, fallback to same-tab navigation.
                        if (!w) {
                            // close overlay then navigate in same tab so the print script can run without being blocked
                            closePage();
                            window.location.href = url;
                        } else {
                            // close the overlay to keep UI tidy
                            closePage();
                            // focus the new window if possible
                            try { w.focus(); } catch (e){}
                        }
                    }catch(e){ console.warn('export button failed', e); alert('Não foi possível iniciar a exportação. Tente novamente.'); }
                });

            var closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.className = 'page-rdo-close-btn';
            closeBtn.textContent = 'Fechar';
            closeBtn.style.cursor = 'pointer';
            closeBtn.addEventListener('click', function(){ closePage(); });

            toolbar.appendChild(printBtn);
            toolbar.appendChild(closeBtn);

            // content wrapper
            var contentWrap = document.createElement('div');
            contentWrap.style.overflow = 'auto';
            contentWrap.style.padding = '16px';
            contentWrap.style.flex = '1 1 auto';
            contentWrap.appendChild(page);

            container.appendChild(toolbar);
            container.appendChild(contentWrap);
            overlay.appendChild(container);
            // allow Esc to close
            document.addEventListener('keydown', escHandler);
            // populate with data
            if (rdoId) { fetchAndPopulate(rdoId); }
        } catch(e) { console.warn('openPage failed', e); }
    }

    function closePage(){
        try {
            if (!page) return;
            overlay.style.display = 'none';
            // restore into placeholder
            var container = qs('#' + overlayId + '-container');
            if (container) {
                // if page still inside container contentWrap, restore
                try {
                    if (page && pagePlaceholder && pagePlaceholder.parentNode) pagePlaceholder.parentNode.insertBefore(page, pagePlaceholder);
                } catch(e){}
                if (container.parentNode) container.parentNode.removeChild(container);
            } else {
                if (pagePlaceholder && pagePlaceholder.parentNode) pagePlaceholder.parentNode.insertBefore(page, pagePlaceholder);
            }
            if (pagePlaceholder && pagePlaceholder.parentNode) pagePlaceholder.parentNode.removeChild(pagePlaceholder);
            pagePlaceholder = null;
            page.style.display = 'none';
            document.removeEventListener('keydown', escHandler);
        } catch(e) { console.warn('closePage failed', e); }
    }

    function escHandler(ev){ if (ev.key === 'Escape') closePage(); }

    // Client-side printable exporter: open a new window with the full RDO HTML and styles, then call window.print()
    function exportPrintable(){
        try{
            if (!page) return;

            // Abra a janela imediatamente (síncrono ao clique) para evitar bloqueio de pop-up
            var printWin = null;
            try { printWin = window.open('', '_blank', 'noopener'); } catch(e) { printWin = null; }

            // Fallback: use um iframe oculto se a janela for bloqueada
            var useIframe = !printWin;
            var iframe = null;

            // Clone do conteúdo que iremos imprimir
            var clone = page.cloneNode(true);
            Array.from(clone.querySelectorAll('img')).forEach(function(img){
                try{
                    var srcAttr = img.getAttribute('src');
                    if (srcAttr && !/^https?:\/\//i.test(srcAttr)){
                        img.src = new URL(srcAttr, window.location.href).href;
                    }
                }catch(e){}
            });

            // Montar título/filename no formato RDO-<OS>-<DATA>
            try{
                function normalizeText(s){ try{ return String(s||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase(); }catch(e){ return String(s||'').toLowerCase(); } }
                function getFieldFromClone(clone, headerKey){
                    try{
                        var table = clone.querySelector('.general-info-azul table') || clone.querySelector('.general-info table') || clone.querySelector('table');
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
                var osNumber = getFieldFromClone(clone, 'os') || getFieldFromClone(clone, 'os nº') || getFieldFromClone(clone, 'os no') || '';
                var dateRaw = getFieldFromClone(clone, 'data') || '';
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
                osNumber = String(osNumber).trim().replace(/\s+/g,'').replace(/[^0-9A-Za-z\-_.]/g,'');
                var printTitle = 'RDO-' + osNumber + '-' + dateForFilename;
            }catch(e){ var printTitle = (document.title || 'RDO'); }

            // Documento base
            var docHtml = '<!doctype html><html><head><meta charset="utf-8">';
            docHtml += '<title>' + (printTitle || (document.title || 'RDO')) + '</title>';
            docHtml += '<base href="' + window.location.origin + '" />';

            // Coleta e inlining de CSS same-origin
            var stylePromises = [];
            Array.from(document.styleSheets || []).forEach(function(ss){
                try{
                    if (!ss.href){
                        var owner = ss.ownerNode;
                        if (owner && owner.tagName === 'STYLE'){
                            docHtml += '<style>' + owner.textContent + '</style>';
                        }
                        return;
                    }
                    var url = new URL(ss.href, window.location.href);
                    if (url.origin !== window.location.origin) return;
                    stylePromises.push(
                        fetch(url.href, { credentials: 'same-origin' })
                          .then(function(r){ return r.ok ? r.text() : ''; })
                          .then(function(text){ return text ? '<style>\n'+text+'\n</style>' : ''; })
                          .catch(function(){ return ''; })
                    );
                }catch(e){}
            });
            Array.from(document.querySelectorAll('link[rel="stylesheet"]')).forEach(function(link){
                try{
                    var href = link.href;
                    if (!href) return;
                    var url = new URL(href, window.location.href);
                    if (url.origin !== window.location.origin) return;
                    stylePromises.push(
                        fetch(url.href, { credentials: 'same-origin' })
                          .then(function(r){ return r.ok ? r.text() : ''; })
                          .then(function(text){ return text ? '<style>\n'+text+'\n</style>' : ''; })
                          .catch(function(){ return ''; })
                    );
                }catch(e){}
            });

            Promise.all(stylePromises).then(function(styles){
                styles.forEach(function(s){ if (s) docHtml += s; });
                // Compress images in the cloned document to reduce final PDF size (best-effort)
                function compressImagesInClone(root, maxWidthPx, quality){
                    return new Promise(function(resolve){
                        try{
                            var imgs = Array.from(root.querySelectorAll('img'));
                            if (!imgs.length) return resolve();
                            var pending = imgs.length;
                            imgs.forEach(function(img){
                                function done(){ pending--; if (pending <= 0) resolve(); }
                                try{
                                    // ensure image is loaded
                                    if (!img.complete || (img.naturalWidth === 0 && img.naturalHeight === 0)){
                                        img.addEventListener('load', process);
                                        img.addEventListener('error', done);
                                    } else {
                                        process();
                                    }
                                }catch(e){ done(); }

                                function process(){
                                    try{
                                        var nw = img.naturalWidth || img.width;
                                        var nh = img.naturalHeight || img.height || Math.round(nw * 0.75);
                                        if (!nw || !nh){ return done(); }
                                        var targetW = Math.min(nw, maxWidthPx || 1200);
                                        if (targetW <= 0 || targetW >= nw){ return done(); }
                                        var targetH = Math.round((targetW / nw) * nh);
                                        var c = document.createElement('canvas');
                                        c.width = targetW;
                                        c.height = targetH;
                                        var ctx = c.getContext('2d');
                                        ctx.fillStyle = '#ffffff'; ctx.fillRect(0,0,c.width,c.height);
                                        ctx.drawImage(img, 0, 0, nw, nh, 0, 0, targetW, targetH);
                                        try{
                                            var data = c.toDataURL('image/jpeg', quality || 0.75);
                                            img.src = data;
                                        }catch(e){}
                                    }catch(e){}
                                    done();
                                }
                            });
                        }catch(e){ resolve(); }
                    });
                }
                // CSS de impressão mínimo e regras para evitar quebras ruins e imagens gigantes
                docHtml += '<style>'+
                    'html,body{background:#fff;color:#000;-webkit-print-color-adjust:exact;print-color-adjust:exact;}'+
                    '@page{size:A4 landscape;margin:12mm;}'+
                    '#rdo img{max-width:100%;height:auto;object-fit:contain;}'+
                    'table{width:100%;border-collapse:collapse}'+
                    'table,thead,tbody,tr,td,th{page-break-inside:avoid;break-inside:avoid}'+
                    '.section-block{page-break-inside:avoid;break-inside:avoid}'+
                    '.no-print{display:none!important}'+
                '</style>';
                // compress images before inlining HTML to reduce transfer to print window
                compressImagesInClone(clone, 1200, 0.72).then(function(){
                    docHtml += '</head><body>' + clone.outerHTML;
                // Script para esperar imagens e acionar impressão
                docHtml += '<script>'+
                  '(function(){'+
                  ' function whenImagesLoaded(cb){ var imgs=Array.from(document.images||[]); if(!imgs.length) return cb(); var c=0; function ch(){ if(++c>=imgs.length) cb(); } imgs.forEach(function(i){ if(i.complete) ch(); else { i.addEventListener("load", ch); i.addEventListener("error", ch);} }); }'+
                  ' whenImagesLoaded(function(){ setTimeout(function(){ try{ window.focus(); window.print(); }catch(e){ try{ print(); }catch(_){} } }, 150); });'+
                  '})();'+
                '</script>';
                docHtml += '</body></html>';

                    if (useIframe){
                    // Fallback por iframe oculto
                    iframe = document.createElement('iframe');
                    iframe.style.position = 'fixed';
                    iframe.style.right = '0';
                    iframe.style.bottom = '0';
                    iframe.style.width = '0';
                    iframe.style.height = '0';
                    iframe.style.border = '0';
                    iframe.setAttribute('aria-hidden', 'true');
                    document.body.appendChild(iframe);
                    var idoc = iframe.contentWindow || iframe.contentDocument;
                    if (idoc.document) idoc = idoc.document;
                    idoc.open(); idoc.write(docHtml); idoc.close();
                    // limpeza após impressão
                    try {
                        iframe.onload = function(){
                            try{
                                (iframe.contentWindow || iframe).focus();
                                (iframe.contentWindow || iframe).print();
                            }catch(_){ /* best-effort */ }
                            setTimeout(function(){ try{ document.body.removeChild(iframe); }catch(__){} }, 2000);
                        };
                    } catch(_){}
                    } else {
                    // Janela aberta sincronamente
                    try {
                        printWin.document.open();
                        printWin.document.write(docHtml);
                        printWin.document.close();
                    } catch(e){
                        // se falhar, usa fallback por iframe
                        useIframe = true;
                        try{ printWin.close(); }catch(_){ }
                        iframe = document.createElement('iframe');
                        iframe.style.position = 'fixed';
                        iframe.style.right = '0';
                        iframe.style.bottom = '0';
                        iframe.style.width = '0';
                        iframe.style.height = '0';
                        iframe.style.border = '0';
                        iframe.setAttribute('aria-hidden', 'true');
                        document.body.appendChild(iframe);
                        var idoc2 = iframe.contentWindow || iframe.contentDocument; if (idoc2.document) idoc2 = idoc2.document;
                        idoc2.open(); idoc2.write(docHtml); idoc2.close();
                        try{ (iframe.contentWindow || iframe).focus(); (iframe.contentWindow || iframe).print(); }catch(_){ }
                        setTimeout(function(){ try{ document.body.removeChild(iframe); }catch(__){} }, 2000);
                    }
                }
            }).catch(function(err){
                console.warn('exportPrintable error', err);
                alert('Erro ao preparar impressão. Tente novamente.');
            });
        }catch(e){ console.warn('exportPrintable failed', e); alert('Erro ao iniciar exportação'); }
    }

    // Attach to existing .action-btn.view buttons (delegation for future rows)
    document.addEventListener('click', function(ev){
        try {
            var btn = ev.target.closest && ev.target.closest('.action-btn.view');
            if (!btn) return;
            ev.preventDefault();
            var tr = btn.closest('tr');
            var rid = tr && tr.getAttribute('data-rdo-id');
            if (!rid) return;
            // Recommended flow: open server-rendered page for the RDO in a new tab.
            // This avoids popup-blockers (call is inside click handler) and ensures
            // the page served by Django (`rdo_page.html`) is used for pixel-perfect layout/print.
            var url = '/rdo/' + encodeURIComponent(rid) + '/page/';
            var w = null;
            try { w = window.open(url, '_blank'); } catch(e) { w = null; }
            if (!w) {
                // If popup blocked, navigate in same tab
                window.location.href = url;
            } else {
                try { w.focus(); } catch(e){}
            }
        } catch(e){}
    }, true);

    // also expose simple API
    window.pageRdo = { open: openPage, close: closePage };
})();
