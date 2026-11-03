import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const css = readFileSync(new URL('../src/assets/tokens.css', import.meta.url), 'utf8');
const colors = Object.fromEntries([...css.matchAll(/--ep-([a-z-]+):\s*(#[0-9A-Fa-f]{6});/g)].map(match => [match[1], match[2]]));
function luminance(hex: string) {
  const rgb = [1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16) / 255)
    .map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
for (const [foreground, background, minimum] of [
  ['ink','paper',4.5], ['ink','white',4.5], ['muted','paper',4.5], ['muted','white',4.5],
  ['white','terra',4.5], ['white','terra-hover',4.5], ['white','danger',4.5],
  ['ink','soft',4.5], ['info','info-bg',4.5], ['success','success-bg',4.5],
  ['warning','warning-bg',4.5], ['danger','danger-bg',4.5], ['danger','white',4.5],
  ['control','white',3], ['control','paper',3],
] as const) {
  test(`contraste ${foreground} sobre ${background} alcanza ${minimum}:1`, () => {
    const [light, dark] = [luminance(colors[foreground]), luminance(colors[background])].sort((a,b) => b-a);
    assert.ok((light + 0.05) / (dark + 0.05) >= minimum);
  });
}
