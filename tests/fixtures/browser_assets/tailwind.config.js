// Builds tests/fixtures/browser_assets/factory-tailwind.css, the local stand-in the
// real-browser tests serve instead of https://cdn.tailwindcss.com (see
// tests/test_ebook_real_browser_customer_path.py). Same Tailwind major
// version the CDN serves (v3) and the same theme extension as
// templates/index.html, compiled from every file the page's classes come from.
//
// Regenerate after adding new Tailwind classes to the app:
//   npx tailwindcss@3.4.19 -c tests/fixtures/browser_assets/tailwind.config.js \
//     -i tests/fixtures/browser_assets/tailwind-input.css -o tests/fixtures/browser_assets/factory-tailwind.css --minify
module.exports = {
  content: {
    relative: true,
    files: [
      "../../../templates/**/*.html",
      "../../../static/js/**/*.js",
      "../../../app.py",
      "../../../services/**/*.py",
    ],
  },
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc",
          400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
          800: "#3730a3", 900: "#312e81", 950: "#1e1b4b",
        },
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"] },
    },
  },
};
