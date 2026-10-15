const { readFileSync } = require("node:fs");
const ts = require("typescript");

const PRAGMA = new RegExp(
  [
    String.raw`^\s*eslint-(?:disable|enable)(?:-next-line|-line)?\b`,
    String.raw`^\s*@ts-expect-error\s+\S+`,
    String.raw`^\s*(?:istanbul|c8|v8)\s+ignore\b`,
    String.raw`^\s*prettier-ignore\b`,
    String.raw`^\s*@(?:jest|vitest)-environment\b`,
    String.raw`^\s*@(?:jsx|jsxImportSource|jsxRuntime)\b`,
    String.raw`^\s*/\s*<reference\b`,
  ].join("|"),
);

const TEXT_FOLLOWS_KINDS = new Set([ts.SyntaxKind.GreaterThanToken, ts.SyntaxKind.CloseBraceToken]);

const JSX_PARENT_KINDS = new Set([
  ts.SyntaxKind.JsxOpeningElement,
  ts.SyntaxKind.JsxClosingElement,
  ts.SyntaxKind.JsxSelfClosingElement,
  ts.SyntaxKind.JsxOpeningFragment,
  ts.SyntaxKind.JsxClosingFragment,
  ts.SyntaxKind.JsxExpression,
]);

function isFollowedByJsxText(node) {
  return TEXT_FOLLOWS_KINDS.has(node.kind) && JSX_PARENT_KINDS.has(node.parent.kind);
}

function commentBody(text, range) {
  const raw = text.slice(range.pos, range.end);
  if (range.kind === ts.SyntaxKind.SingleLineCommentTrivia) {
    return raw.slice(2);
  }
  return raw.slice(2, -2).replace(/^[\s*]+/, "");
}

function scriptKindFor(fileName) {
  return fileName.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
}

function collectRanges(sourceFile) {
  const text = sourceFile.text;
  const seen = new Map();

  const remember = (ranges) => {
    for (const range of ranges ?? []) {
      seen.set(range.pos, range);
    }
  };

  const visit = (node) => {
    const children = node.getChildren(sourceFile);
    if (children.length === 0) {
      if (node.kind !== ts.SyntaxKind.JsxText) {
        remember(ts.getLeadingCommentRanges(text, node.getFullStart()));
        if (!isFollowedByJsxText(node)) {
          remember(ts.getTrailingCommentRanges(text, node.getEnd()));
        }
      }
      return;
    }
    children.forEach(visit);
  };

  visit(sourceFile);
  return [...seen.values()].sort((a, b) => a.pos - b.pos);
}

function findComments(source, fileName = "file.ts") {
  const sourceFile = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
    scriptKindFor(fileName),
  );
  const findings = [];
  for (const range of collectRanges(sourceFile)) {
    const body = commentBody(source, range);
    if (PRAGMA.test(body)) {
      continue;
    }
    const { line } = sourceFile.getLineAndCharacterOfPosition(range.pos);
    const firstLine = body.trim().split("\n")[0]?.trim() ?? "";
    findings.push({ line: line + 1, text: firstLine });
  }
  return findings;
}

function checkFiles(paths) {
  return paths.flatMap((path) =>
    findComments(readFileSync(path, "utf8"), path).map((finding) => ({ path, ...finding })),
  );
}

function main(input) {
  return JSON.stringify(checkFiles(input.split("\n").filter(Boolean)));
}

if (require.main === module) {
  process.stdout.write(main(readFileSync(0, "utf8")));
}

module.exports = { findComments, checkFiles, main };
