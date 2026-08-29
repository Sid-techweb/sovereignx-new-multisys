/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      colors: {
        console: {
          bg:        '#081119',
          panel:     'rgba(12, 24, 35, 0.66)',
          panelSolid:'#0d1a26',
          inset:     'rgba(6, 14, 21, 0.55)',
          line:      'rgba(146, 178, 208, 0.11)',
          lineSoft:  'rgba(146, 178, 208, 0.06)',
          text:      '#e6eef5',
          text2:     '#9db0c2',
          muted:     '#6b8095',
          amber:     '#ef8f2b',
          amberSoft: 'rgba(239, 143, 43, 0.14)',
          green:     '#4ec77f',
          greenSoft: 'rgba(78, 199, 127, 0.13)',
          red:       '#e2604c',
        },
        brand: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          900: '#0c4a6e',
        }
      }
    },
  },
  plugins: [],
}
