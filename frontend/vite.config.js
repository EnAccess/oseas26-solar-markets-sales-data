import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development, /api requests are proxied to the FastAPI backend (avoids CORS entirely).
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

/**
 * rwanda-location-lookup builds one fallback URL with a template literal
 * (`new URL(`../../${PACKAGE_NAME}/data/${fileName}`, import.meta.url)`). Vite turns such templates
 * into a glob over node_modules/<every package>/data/ and eagerly imports all matches, which breaks
 * the dev server (e.g. tldts' trie.js.map). Rewriting it as string concatenation keeps the same
 * runtime URL without the glob.
 */
function rwandaLookupNoGlob() {
  const template = "new URL(`../../${PACKAGE_NAME}/data/${fileName}`, import.meta.url)";
  return {
    name: "rwanda-location-lookup-no-glob",
    enforce: "pre",
    transform(code, id) {
      if (!id.includes("rwanda-location-lookup") || !code.includes(template)) return null;
      return { code: code.replace(template, 'new URL("../../" + PACKAGE_NAME + "/data/" + fileName, import.meta.url)'), map: null };
    },
  };
}

export default defineConfig({
  plugins: [rwandaLookupNoGlob(), react()],
  server: { host: true, port: 5173, proxy: { "/api": { target, changeOrigin: true } } },
  preview: { proxy: { "/api": { target, changeOrigin: true } } },
  test: { environment: "jsdom", include: ["src/**/*.test.{js,jsx}"] },
});
