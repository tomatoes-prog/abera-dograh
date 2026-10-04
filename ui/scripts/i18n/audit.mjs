import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

import ts from "typescript";

const ui = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const src = path.join(ui, "src");
const read = name => JSON.parse(fs.readFileSync(path.join(src, "i18n/messages", name + ".json"), "utf8"));
const ids = read("sources"), en = read("en").copy, es = read("es-419").copy;
const exceptions = new Set(read("technical"));
const issues = [];
const has = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
for (const [source, id] of Object.entries(ids)) {
  if (!has(en, id) || !has(es, id)) issues.push(`Missing catalog entry: ${source}`);
  if (en[id] === es[id] && !exceptions.has(source)) issues.push(`Unreviewed English copy: ${source}`);
}
for (const id of [...Object.keys(en), ...Object.keys(es)]) {
  if (!Object.values(ids).includes(id)) issues.push(`Orphan catalog key: ${id}`);
}
const attrs = new Set(["placeholder", "title", "aria-label", "label", "description", "alt", "helperText", "emptyMessage"]);
function visible(text) { return /[A-Za-z]{2}/.test(text) && !/^https?:|^#[a-f0-9]{6}$/i.test(text); }
function clean(text) {return text.split(/\r?\n/).map((line, i, lines) => {
  if (i) line = line.replace(/^\s+/, "");
  if (i < lines.length - 1) line = line.replace(/\s+$/, "");
  return line;
}).filter(Boolean).join(" ");}
function excluded(node, sf) {
  for (let parent = node.parent; parent; parent = parent.parent) {
    if (ts.isJsxElement(parent) && ["code", "pre", "script", "Script", "style"].includes(parent.openingElement.tagName.getText(sf))) return true;
  }
  return false;
}
function walk(dir) {
  for (const entry of fs.readdirSync(dir, {withFileTypes: true})) {
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) {if (!["client", "i18n"].includes(entry.name)) walk(file);}
    else if (/\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)) issues.push(...inspectSource(file, fs.readFileSync(file, "utf8")));
  }
}
export function inspectSource(file, source) {
  const findings = new Set();
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith("tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const constants = new Map();
  function collect(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const name = node.name.text;
      // Do not resolve ambiguous names from different component scopes.
      constants.set(name, constants.has(name) ? null : node.initializer);
    }
    ts.forEachChild(node, collect);
  }
  collect(sf);
  function issue(node, message) {
    findings.add(`${path.relative(ui, file).replaceAll("\\", "/")}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1}: ${message}`);
  }
  function requireMessage(node, text) {if (visible(text) && !has(ids, text)) issue(node, `Missing copy: ${text}`);}
  function visibleExpression(node, seen = new Set()) {
    if (!node || seen.has(node)) return;
    seen.add(node);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      if (visible(node.text) && !exceptions.has(node.text)) issue(node, `Wrap visible expression in copy(): ${node.text}`);
    } else if (ts.isTemplateExpression(node)) {
      const parts = [node.head.text, ...node.templateSpans.map(span => span.literal.text)];
      if (parts.some(visible)) issue(node, `Translate a whole message with parameters: ${node.getText(sf)}`);
    } else if (ts.isConditionalExpression(node)) {
      visibleExpression(node.whenTrue, seen);
      visibleExpression(node.whenFalse, seen);
    } else if (ts.isBinaryExpression(node) && [ts.SyntaxKind.PlusToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(node.operatorToken.kind)) {
      visibleExpression(node.left, seen);
      visibleExpression(node.right, seen);
    } else if (ts.isParenthesizedExpression(node)) {
      visibleExpression(node.expression, seen);
    } else if (ts.isIdentifier(node) && constants.get(node.text)) {
      visibleExpression(constants.get(node.text), seen);
    }
    // Calls, member access and JSX elements are handled at their own display
    // sites. Never interpret values from forms, API data or customer content.
  }
  function visit(node) {
    if (excluded(node, sf)) return;
    if (ts.isJsxText(node)) {
      const text = clean(node.text);
      if (visible(text) && !/^&[a-z]+;$/.test(text)) issue(node, `Wrap visible text in copy(): ${text}`);
    }
    if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer)) {
      const name = node.name.getText(sf), value = node.initializer.text;
      if (name === "text" && node.parent.tagName?.getText(sf) === "CopyText") requireMessage(node, value);
      else if (attrs.has(name) && visible(value) && !exceptions.has(value)) issue(node, `Wrap ${name} in copy(): ${value}`);
    }
    if (ts.isJsxExpression(node) && node.expression) {
      if (!ts.isJsxAttribute(node.parent) || attrs.has(node.parent.name.getText(sf))) visibleExpression(node.expression);
    }
    if (ts.isCallExpression(node)) {
      const name = node.expression.getText(sf);
      if (name === "copy" && ts.isStringLiteral(node.arguments[0])) requireMessage(node, node.arguments[0].text);
      if (/^(toast\.(error|success|info|warning|message)|setError|setSuccess)$/.test(name) && node.arguments[0] && ts.isStringLiteral(node.arguments[0]) && visible(node.arguments[0].text)) issue(node, `Wrap notification in copy(): ${node.arguments[0].text}`);
      else if (/^(toast\.(error|success|info|warning|message)|setError|setSuccess)$/.test(name)) visibleExpression(node.arguments[0]);
      if (name === "detailFromError" && node.arguments[1] && ts.isStringLiteral(node.arguments[1])) requireMessage(node, node.arguments[1].text);
    }
    // Static metadata is intentionally kept in its original module for small
    // upstream diffs. Its display site must call copy(); values stay untouched.
    if (ts.isPropertyAssignment(node) && ["label", "title", "description", "hint", "heading", "subtitle"].includes(node.name.getText(sf).replace(/["']/g, "")) && ts.isStringLiteral(node.initializer)) requireMessage(node, node.initializer.text);
    ts.forEachChild(node, visit);
  }
  visit(sf);
  return [...findings];
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  walk(src);
  if (issues.length) {console.error(issues.join("\n")); process.exitCode = 1;}
  else console.log(`i18n audit passed: ${Object.keys(ids).length} messages, ${exceptions.size} reviewed exceptions.`);
}
