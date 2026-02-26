import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        'gbc-bg': '#e0f8d0',
        'gbc-primary': '#88c070',
        'gbc-dark': '#346856',
        'gbc-black': '#081820',
        'pkmn-red': '#f85858',
        'pkmn-blue': '#58a8f8',
        'pkmn-gold': '#f8d030',
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'cursive', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
