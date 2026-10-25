/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bricolage Grotesque Variable"', 'system-ui', 'sans-serif'],
        sans: ['"Public Sans Variable"', 'system-ui', 'sans-serif'],
      },
      colors: {
        paper: '#F3F4F7',
        surface: '#FFFFFF',
        ink: { DEFAULT: '#1A1C2B', 2: '#4A5065', 3: '#7A8094' },
        line: { DEFAULT: '#E2E4EB', strong: '#CDD1DC' },
        brand: { DEFAULT: '#26337A', hover: '#1C275F', soft: '#E8EBFA' },
        focus: '#3B5BDB',
        f: {
          trigger: '#C98A0B', triggerbg: '#FFF2D6',
          data: '#2C7BD6', databg: '#E2EEFD',
          audience: '#7656E3', audiencebg: '#EEE9FF',
          action: '#178A63', actionbg: '#DDF4EA',
          approval: '#D2405A', approvalbg: '#FFE6EA',
          knowledge: '#13899A', knowledgebg: '#DBF3F5',
          memory: '#A0458B', memorybg: '#F9E4F3',
          output: '#C4612A', outputbg: '#FCE9DC',
        },
      },
      fontSize: {
        '2xs': ['11px', '16px'],
      },
      boxShadow: {
        card: '0 1px 0 rgba(26,28,43,0.04), 0 1px 2px rgba(26,28,43,0.05)',
        pop: '0 12px 32px -8px rgba(26,28,43,0.22), 0 2px 6px rgba(26,28,43,0.08)',
      },
      keyframes: {
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: { shimmer: 'shimmer 1.6s linear infinite' },
    },
  },
  plugins: [],
}
