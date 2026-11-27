import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#0F2544',
          hover: '#1E3A5F',
        },
        legalBlue: {
          DEFAULT: '#2563EB',
          light: '#EFF6FF',
        },
        surface: '#F8FAFC',
        ink: {
          DEFAULT: '#0F172A',
          muted: '#64748B',
        },
      },
    },
  },
  plugins: [],
};

export default config;
