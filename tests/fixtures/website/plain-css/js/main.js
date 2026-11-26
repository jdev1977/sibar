// Theme toggle and a "today's special" card rendered from a template string.
const toggle = document.querySelector('.theme-toggle');
toggle.addEventListener('click', () => {
  document.body.classList.toggle('dark');
  localStorage.setItem('theme', document.body.classList.contains('dark') ? 'dark' : 'light');
});

const special = { name: 'Cardamom bun', price: 4.5 };
document.querySelector('#menu').insertAdjacentHTML('beforeend',
  `<aside class="special"><h3>Today's special</h3><p>${special.name}</p></aside>`);
