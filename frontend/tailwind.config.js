const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: v('--bg'),
        surface: v('--surface'),
        sunk: v('--sunk'),
        line: v('--line'),
        ink: v('--ink'),
        muted: v('--ink2'),
        faint: v('--ink3'),
        navy: v('--navy'),
        accent: { DEFAULT: v('--accent'), ink: v('--accent-ink'), soft: v('--accent-soft') },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: { xl: '12px', '2xl': '16px' },
    },
  },
  plugins: [],
};
