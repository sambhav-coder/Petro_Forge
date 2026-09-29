import path from "node:path";
import { fileURLToPath } from "node:url";

// Resolve the Tailwind config next to this file, not from the process cwd,
// so the frontend styles correctly however `next dev` is launched.
const here = path.dirname(fileURLToPath(import.meta.url));

export default {
  plugins: {
    tailwindcss: { config: path.join(here, "tailwind.config.ts") },
    autoprefixer: {},
  },
};
