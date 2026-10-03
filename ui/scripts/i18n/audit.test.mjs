import assert from "node:assert/strict";
import test from "node:test";

import { inspectSource } from "./audit.mjs";

const inspect = source => inspectSource("Example.tsx", source).join("\n");

test("detects new visible JSX and attribute copy", () => {
  const result = inspect('<button title="New upstream action">New upstream label</button>');
  assert.match(result, /Wrap title/);
  assert.match(result, /Wrap visible text/);
});

test("detects messages hidden in conditional constants and notifications", () => {
  const result = inspect('const text = ready ? "New ready message" : `Failed ${name}`; toast.error(text);');
  assert.match(result, /New ready message/);
  assert.match(result, /Translate a whole message with parameters/);
});

test("requires catalog coverage for new translations and display metadata", () => {
  const result = inspect('copy("Missing catalog text"); const field = {label: "New field label"};');
  assert.match(result, /Missing catalog text/);
  assert.match(result, /New field label/);
});

test("accepts reviewed copy and preserves customer data, code and proper names", () => {
  const source = [
    'const value = api.customerInput;',
    '<div title={copy("Save")}>',
    '  {copy("Save")}{value}<span>{copy("OpenAI")}</span>',
    '  <code>Untranslated code example</code>',
    "  <Script>{`window.unchanged = 'Untranslated script';`}</Script>",
    '</div>;',
  ].join("\n");
  assert.equal(inspect(source), "");
});
