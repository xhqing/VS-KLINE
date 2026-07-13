// 同步 VERSION → package.json.version，避免两处版本漂移。
// 由 `npm run package` 的 prepackage 钩子触发。
import { readFileSync, writeFileSync } from 'node:fs';

const version = readFileSync('VERSION', 'utf8').trim();
const pkg = JSON.parse(readFileSync('package.json', 'utf8'));

if (pkg.version !== version) {
  pkg.version = version;
  writeFileSync('package.json', JSON.stringify(pkg, null, 2) + '\n');
  console.log(`[sync-version] package.json → ${version}`);
} else {
  console.log(`[sync-version] already ${version}`);
}
