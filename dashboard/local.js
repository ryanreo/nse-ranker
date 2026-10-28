// Local stand-in for the online dashboard's `dash` functions, so dashboard/index.html runs unchanged on
// localhost. Data comes from the local server's /data/<id>.json (the files `export` writes).
(function () {
  const store = {};          // id -> {status, data, message}
  const calcs = {};          // id -> {inputs, fn}
  const draws = {};          // name -> fn(el)
  const listeners = [];      // dash.onData callbacks

  function ids() {
    const found = new Set();
    document.querySelectorAll('[data-source]').forEach((el) => {
      el.dataset.source.split(/\s+/).filter(Boolean).forEach((id) => found.add(id));
    });
    Object.values(calcs).forEach((c) => c.inputs.forEach((id) => found.add(id)));
    return [...found].filter((id) => !calcs[id]);
  }

  function runCalcs() {
    Object.entries(calcs).forEach(([id, calc]) => {
      const inputs = calc.inputs.map((input) => store[input]);
      if (inputs.every((d) => d && d.status === 'ok')) {
        try {
          store[id] = { status: 'ok', data: calc.fn(...inputs.map((d) => d.data)) };
        } catch (error) {
          store[id] = { status: 'error', data: [], message: String(error) };
        }
      } else {
        store[id] = { status: 'loading', data: [] };
      }
    });
  }

  function runDraw(name) {
    document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
      if (el.closest('[hidden]')) return;   // like the online dashboard: hidden drawings wait
      try { draws[name](el); } catch (error) { console.error(`drawing ${name}:`, error); }
    });
  }

  function redrawAll() {
    listeners.forEach((fn) => { try { fn(); } catch (error) { console.error(error); } });
    Object.keys(draws).forEach(runDraw);
  }

  window.dash = {
    data(id) {
      const d = store[id] || { status: 'loading', data: [] };
      return { ...d, rows: d.data, columns: d.data && d.data[0] ? Object.keys(d.data[0]) : [], meta: [] };
    },
    onData(fn) { listeners.push(fn); try { fn(); } catch (error) { console.error(error); } },
    draw(name, fn) {
      if (fn) {
        draws[name] = typeof fn === 'function' ? fn : (el) => fn.update(el, fn.mount && fn.mount(el));
      }
      if (draws[name]) runDraw(name);
    },
    calc(id, { inputs, fn }) { calcs[id] = { inputs, fn }; },
    loader() {},             // local data is already rows
    colors: ['#3b6ea8', '#c2703d', '#4f8a5b', '#8a5aa8', '#b04a5a', '#5a8a8a', '#a8913b', '#6b6b6b'],
    params: () => ({}),
    setParams() {},
    resetParams() {},
    setLink(name) { history.replaceState(null, '', `#${name}`); },
    refresh() { load(); },
  };

  async function load() {
    const wanted = ids();
    await Promise.all(wanted.map(async (id) => {
      try {
        const response = await fetch(`/data/${encodeURIComponent(id)}.json`);
        if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
        store[id] = { status: 'ok', data: await response.json() };
      } catch (error) {
        store[id] = { status: 'error', data: [], message: String(error) };
        console.error(`data ${id}:`, error);
      }
    }));
    runCalcs();
    redrawAll();
    const missing = wanted.filter((id) => store[id].status !== 'ok');
    const note = document.getElementById('local-status');
    if (note) {
      note.textContent = missing.length
        ? `Couldn't load: ${missing.join(', ')}. Run "python -m nse_ranker export" and refresh.`
        : '';
    }
  }

  // Show/hide panes run their drawings once visible; redraw charts when the window changes size.
  new MutationObserver(() => Object.keys(draws).forEach(runDraw))
    .observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['hidden'] });
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(redrawAll, 150); });
  document.addEventListener('DOMContentLoaded', load);
})();
