const { mkdtempSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const { join } = require("node:path");
const { checkFiles, findComments, main } = require("../tools/check-comments.cjs");

const lines = (source, fileName) => findComments(source, fileName).map((finding) => finding.line);

describe("findComments", () => {
  it("reports line comments, block comments and JSDoc", () => {
    const source = ["const a = 1; // trailing", "/* block */", "/** doc */ const b = 2;"].join("\n");

    expect(lines(source)).toEqual([1, 2, 3]);
  });

  it("reports the first line of a multi-line block comment", () => {
    const [finding] = findComments("/*\n  first\n  second\n*/\nconst a = 1;");

    expect(finding).toEqual({ line: 1, text: "first" });
  });

  it("ignores comment markers inside strings", () => {
    const source = [
      "const a = 'not // a comment';",
      'const b = "nor /* this */";',
      "const c = 'https://example.com/path';",
    ].join("\n");

    expect(findComments(source)).toEqual([]);
  });

  it("ignores comment markers inside template literals, including substitutions", () => {
    const source = [
      "const a = `// plain ${1 + 1} /* still text */`;",
      "const b = `${'x'}//${'y'}`;",
      "const c = `line one",
      "// line two",
      "`;",
    ].join("\n");

    expect(findComments(source)).toEqual([]);
  });

  it("reports a comment inside a template substitution", () => {
    const source = "const a = `${1 /* real */}`;";

    expect(lines(source)).toEqual([1]);
  });

  it("ignores comment markers inside regular expression literals", () => {
    const source = [
      "const a = /\\/\\//;",
      "const b = /https?:\\/\\/[a-z]+/;",
      "const c = /[/*]/.test('x');",
      "const d = 4 / 2 / 1;",
    ].join("\n");

    expect(findComments(source)).toEqual([]);
  });

  it("reports comments in TSX including JSX expression comments", () => {
    const source = [
      "export const A = () => (",
      "  <div>",
      "    {/* jsx comment */}",
      "    <a href='https://example.com'>https://example.com</a>",
      "    <p>// not a comment</p>",
      "    <p>/* nor this */</p>",
      "  </div>",
      ");",
    ].join("\n");

    expect(lines(source, "a.tsx")).toEqual([3]);
  });

  it("reports comments between JSX attributes", () => {
    const source = "export const A = () => <div /* attr */ id='x' />;";

    expect(lines(source, "a.tsx")).toEqual([1]);
  });

  it.each([
    "// eslint-disable-next-line no-console",
    "// eslint-disable-line no-console",
    "/* eslint-disable no-console */",
    "/* eslint-enable no-console */",
    "// @ts-expect-error legacy typing gap",
    "// istanbul ignore next",
    "/* c8 ignore next */",
    "// prettier-ignore",
    "/** @jest-environment node */",
    "/// <reference types='node' />",
  ])("allows the pragma %s", (pragma) => {
    expect(findComments(`${pragma}\nconst a = 1;`)).toEqual([]);
  });

  it("rejects @ts-expect-error without a reason", () => {
    expect(lines("// @ts-expect-error\nconst a: number = 'x';")).toEqual([1]);
  });

  it("rejects @ts-ignore", () => {
    expect(lines("// @ts-ignore\nconst a = 1;")).toEqual([1]);
  });

  it("rejects prose that merely mentions a pragma word", () => {
    expect(lines("// do not eslint-disable this\nconst a = 1;")).toEqual([1]);
  });

  it("allows a shebang on the first line", () => {
    expect(findComments("#!/usr/bin/env node\nconst a = 1;")).toEqual([]);
  });

  it("finds nothing in an empty file", () => {
    expect(findComments("")).toEqual([]);
  });
});

describe("checkFiles and main", () => {
  const directory = mkdtempSync(join(tmpdir(), "check-comments-"));
  const clean = join(directory, "clean.ts");
  const dirty = join(directory, "dirty.tsx");
  writeFileSync(clean, "export const a = 1;\n");
  writeFileSync(dirty, "export const b = <p>x</p>; // note\n");

  it("reports findings with their path", () => {
    expect(checkFiles([clean, dirty])).toEqual([{ path: dirty, line: 1, text: "note" }]);
  });

  it("serializes findings read from a newline separated list", () => {
    expect(JSON.parse(main(`${clean}\n${dirty}\n`))).toEqual([
      { path: dirty, line: 1, text: "note" },
    ]);
  });
});
