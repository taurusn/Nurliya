/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        foreground: '#fafafa',
        card: '#18181b',
        'card-hover': '#1f1f23',
        border: '#27272a',
        muted: '#71717a',
        primary: {
          DEFAULT: '#3b82f6',
          foreground: '#ffffff',
          hover: '#2563eb',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#ffffff',
        },
        success: {
          DEFAULT: '#10b981',
          foreground: '#ffffff',
        },
        warning: {
          DEFAULT: '#f59e0b',
          foreground: '#ffffff',
        },
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
