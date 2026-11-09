# Example: a TypeScript project tested with Node alone

A TypeScript project the loop can test with nothing but Node and one package.
Node 22.18.0 and newer run `.ts` files directly by stripping the types, so the
tests need no build step, no `ts-node` and no test framework: `node --test`
runs them and `tsc` checks the types. Copy this folder to start a project, or
lift its settings into one you have.

```
examples/typescript/
  package.json       the Node floor, the two scripts, typescript as the one dependency
  package-lock.json  the exact typescript that npm ci installs
  tsconfig.json      keeps tsc and Node's type stripping in agreement
  .gitignore         node_modules/, which npm ci creates here
  src/slug.ts        one exported function
  src/slug.test.ts   its tests, using node:test and node:assert/strict
```

| File | Does |
|---|---|
| [`package.json`](package.json) | `"type": "module"`, `engines.node` at `>=22.18.0`, `npm test` (runs `node --test src/*.test.ts`) and `npm run typecheck` (runs `tsc --noEmit`). `typescript` is its only dependency, pinned to an exact version |
| [`package-lock.json`](package-lock.json) | What `npm ci` installs, so every round gets the same `tsc` |
| [`tsconfig.json`](tsconfig.json) | `strict`, plus `allowImportingTsExtensions`, `verbatimModuleSyntax` and `erasableSyntaxOnly`, which make `tsc` reject what Node can't strip: an `enum`, a `namespace`, an import without its `.ts` |
| [`src/slug.ts`](src/slug.ts) | The code under test |
| [`src/slug.test.ts`](src/slug.test.ts) | Its tests, beside it |

The typecheck covers the source and leaves the test files out, because typing
`node:test` would take `@types/node` as a second dependency. The tests are
checked by running them.

## Run it

```bash
cd examples/typescript
npm ci
npm run typecheck
npm test
```

You need Node 22.18.0 or newer. That's the first release that strips types
without a flag (it came to 22 from 23.6). On an older Node, `npm test` fails
before a single test runs.

## Put it on the loop

Set the loop's `test_command` in the `loop.json` at the project's root:

```json
"test_command": "npm ci && npm run typecheck && npm test"
```

Every round starts from a fresh checkout with no `node_modules`, so `npm ci`
runs every round and needs the network to reach the npm registry. A type error
fails the round as surely as a failing test. [`HOW-IT-WORKS.md`](../../HOW-IT-WORKS.md) has the
rest of the loop's settings.

## How this repo checks it

The `typescript` job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs the three commands
above on Node 22.18.0, then runs [`tests/test_typescript_example.py`](../../tests/test_typescript_example.py). That
test copies this folder, runs `npm test` and expects a pass, then breaks
`slug` and expects a failure. On a machine without Node 22.18.0 or newer, it
skips and says why.
