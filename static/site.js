(() => {
  const dlg = document.getElementById('join');
  if (dlg && dlg.showModal) {
    // Without JavaScript the links still open the email app.
    document.querySelectorAll('[data-join]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); dlg.showModal(); }));
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.close(); });
    dlg.querySelector('[data-copy]').addEventListener('click', async e => {
      const b = e.currentTarget;
      try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = 'Copied'; }
      catch { getSelection().selectAllChildren(dlg.querySelector('code')); b.textContent = 'Selected'; }
      setTimeout(() => { b.textContent = 'Copy'; }, 2000);
    });
  }
  const menu = document.querySelector('.menu');
  document.addEventListener('click', e => { if (menu.open && !menu.contains(e.target)) menu.open = false; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') menu.open = false; });
  const items = document.querySelectorAll('.rise');
  if (!('IntersectionObserver' in window)) return items.forEach(i => i.classList.add('in'));
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
  items.forEach(i => io.observe(i));
})();
