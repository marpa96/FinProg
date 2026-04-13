import { existsSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const args = process.argv.slice(2);
const isWindows = process.platform === "win32";
const venvPython = isWindows
  ? join(".venv", "Scripts", "python.exe")
  : join(".venv", "bin", "python");

const candidates = [
  ...(existsSync(venvPython) ? [[venvPython]] : []),
  ...(isWindows ? [["py", "-3"], ["python"]] : [["python3"], ["python"]]),
];

for (const candidate of candidates) {
  const [command, ...prefixArgs] = candidate;
  const result = spawnSync(command, [...prefixArgs, ...args], {
    cwd: process.cwd(),
    stdio: "inherit",
    shell: false,
  });

  if (result.error?.code === "ENOENT") {
    continue;
  }

  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }

  process.exit(result.status ?? 1);
}

console.error("Could not find Python. Create .venv or install Python 3.");
process.exit(1);
