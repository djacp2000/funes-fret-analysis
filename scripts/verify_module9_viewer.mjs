import fs from "node:fs";

const [path] = process.argv.slice(2);
if (!path) {
  throw new Error("usage: node verify_module9_viewer.mjs <viewer.html>");
}

const html = fs.readFileSync(path, "utf8");
const scripts = [...html.matchAll(/<script(?: [^>]*)?>([\s\S]*?)<\/script>/g)];
if (scripts.length < 2) {
  throw new Error("expected viewer-data and executable script blocks");
}

JSON.parse(scripts[0][1]);
new Function(scripts.at(-1)[1]);
console.log("viewer JSON and inline JavaScript parse successfully");
