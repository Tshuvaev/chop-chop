/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["'Press Start 2P'", "monospace"],
        body: ["'VT323'", "monospace"],
      },
      colors: {
        ink: "#f3f3f3",
        cream: "#101010",
        coral: "#d8d8d8",
        moss: "#c7ef9a",
        sand: "#1a1a1a",
      },
      boxShadow: {
        punch: "inset 0 0 0 1px #000, 0 0 0 1px #262626",
      },
    },
  },
  plugins: [],
};
