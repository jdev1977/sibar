// Menu data
const menuItems = [
  { name: 'Ethiopian Yirgacheffe', price: '$4.50', emoji: '🌸', description: 'Bright and floral with notes of jasmine and bergamot.' },
  { name: 'Colombian Supremo', price: '$4.00', emoji: '🍫', description: 'Rich chocolate notes with a smooth, balanced finish.' },
  { name: 'House Cold Brew', price: '$5.00', emoji: '🧊', description: 'Steeped for 18 hours for a bold, refreshing cup.' },
];

const menuGrid = document.getElementById('menuGrid');
menuGrid.innerHTML = menuItems.map(item => `
  <div class="menu-card">
    <div class="menu-emoji">${item.emoji}</div>
    <h3>${item.name}</h3>
    <p>${item.description}</p>
    <span class="price">${item.price}</span>
  </div>
`).join('');

// Theme toggle
const toggle = document.getElementById('themeToggle');
toggle.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
});

// Animated counters
const counters = document.querySelectorAll('.stat-number');
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const el = entry.target;
      const target = +el.dataset.target;
      let count = 0;
      const step = target / 100;
      const tick = () => {
        count += step;
        if (count < target) { el.textContent = Math.ceil(count); requestAnimationFrame(tick); }
        else { el.textContent = target.toLocaleString() + '+'; }
      };
      tick();
    }
  });
});
counters.forEach(c => observer.observe(c));
