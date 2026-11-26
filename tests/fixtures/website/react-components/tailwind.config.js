/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        brand: {
          50: '#f0fdf4',
          500: '#10b981',
          600: '#059669',
        },
      },
      fontFamily: {
        sans: ['Geist', 'Inter', 'sans-serif'],
        display: ['Cal Sans', 'sans-serif'],
      },
      borderRadius: {
        lg: 'var(--radius)',
      },
    },
  },
  plugins: [],
}
