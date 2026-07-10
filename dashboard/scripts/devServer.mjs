import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, '..');
const viteBin = path.resolve(dashboardRoot, 'node_modules', 'vite', 'bin', 'vite.js');
const parentPid = process.ppid;

const child = spawn(process.execPath, [viteBin, ...process.argv.slice(2)], {
  cwd: dashboardRoot,
  stdio: 'inherit',
  env: process.env,
});

let exiting = false;
function shutdown(signal = 'SIGTERM') {
  if (exiting) return;
  exiting = true;
  if (!child.killed) child.kill(signal);
  setTimeout(() => {
    if (!child.killed) child.kill('SIGKILL');
    process.exit(signal === 'SIGINT' ? 130 : 143);
  }, 1200).unref();
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

child.on('exit', (code, signal) => {
  if (signal) process.exit(signal === 'SIGINT' ? 130 : 143);
  process.exit(code ?? 0);
});

setInterval(() => {
  if (process.ppid !== parentPid && process.ppid === 1) shutdown('SIGTERM');
}, 500).unref();
