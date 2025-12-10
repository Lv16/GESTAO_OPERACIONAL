document.addEventListener('DOMContentLoaded', function() {
  try {
    const container = document.querySelector('.os-widget');
    if (!container) return;
    const select = container.querySelector('select');
    if (!select) return;

    const options = Array.from(select.options).map(o => ({ value: o.value, label: o.text }));
    const inlineList = document.getElementById('os-inline-list');
    const verMaisBtn = document.getElementById('os-ver-mais-btn');
    const popover = document.getElementById('os-popover');
    const popList = document.getElementById('os-popover-list');
    const search = document.getElementById('os-popover-search');
    const closeBtn = document.getElementById('os-popover-close');

    const VISIBLE_N = 6;

    function renderInline() {
      inlineList.innerHTML = '';
      options.slice(0, VISIBLE_N).forEach(opt => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'os-inline-item';
        btn.textContent = opt.label;
        btn.dataset.value = opt.value;
        btn.addEventListener('click', () => selectOption(opt.value, opt.label));
        inlineList.appendChild(btn);
      });
      if (options.length > VISIBLE_N) {
        verMaisBtn.style.display = 'inline-block';
      } else {
        verMaisBtn.style.display = 'none';
      }
      // If a value already selected in the select, reflect it
      if (select.value) {
        markSelected(select.value);
      }
    }

    function renderPop(list) {
      popList.innerHTML = '';
      list.forEach(opt => {
        const row = document.createElement('div');
        row.className = 'os-pop-item';
        row.tabIndex = 0;
        row.textContent = opt.label;
        row.dataset.value = opt.value;
        row.addEventListener('click', () => { selectOption(opt.value, opt.label); hidePopover(); });
        row.addEventListener('keydown', (e) => { if (e.key === 'Enter') { selectOption(opt.value, opt.label); hidePopover(); } });
        popList.appendChild(row);
      });
    }

    function selectOption(value, label) {
      // set the real select value so form submits normally
      select.value = value;
      // dispatch change event in case any listeners rely on it
      select.dispatchEvent(new Event('change', { bubbles: true }));
      markSelected(value);
      showChosenLabel(label);
    }

    function markSelected(value) {
      inlineList.querySelectorAll('.selected').forEach(n => n.classList.remove('selected'));
      const chosen = Array.from(inlineList.querySelectorAll('[data-value]')).find(n => n.dataset.value === value);
      if (chosen) chosen.classList.add('selected');
    }

    function showChosenLabel(label) {
      let disp = document.getElementById('os-selected-display');
      if (!disp) {
        disp = document.createElement('div');
        disp.id = 'os-selected-display';
        disp.className = 'os-selected-display';
        inlineList.parentNode.insertBefore(disp, inlineList.nextSibling);
      }
      disp.textContent = label;
    }

    function showPopover() {
      popover.hidden = false;
      popover.setAttribute('aria-modal', 'true');
      renderPop(options);
      search.value = '';
      search.focus();
    }

    function hidePopover() {
      popover.hidden = true;
      popover.setAttribute('aria-modal', 'false');
      verMaisBtn.focus();
    }

    verMaisBtn.addEventListener('click', showPopover);
    closeBtn.addEventListener('click', hidePopover);
    search.addEventListener('input', function() {
      const q = this.value.trim().toLowerCase();
      if (!q) renderPop(options);
      else renderPop(options.filter(o => o.label.toLowerCase().includes(q)));
    });

    // Close popover on Esc
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && !popover.hidden) hidePopover();
    });

    renderInline();
  } catch (err) {
    // fail silently to avoid breaking the page
    console.error('os-popover error', err);
  }
});
