import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: "#121417",
        panel: "#191d22",
        line: "#2a3038",
        signal: "#e65045",
        cyanSoft: "#6bd6d6",
        silver: "#d7dde5"
      }
    }
  },
  plugins: []
};

export default config;
