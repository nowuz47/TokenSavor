import assert from "node:assert/strict";
import { calculate, tokenize } from "./calculator-core.mjs";

assert.equal(calculate("2 + 2 * 3"), 8);
assert.equal(calculate("(2 + 2) * 3"), 12);
assert.equal(calculate("-4 + 10 / 2"), 1);
assert.equal(calculate("2 ^ 3 ^ 2"), 512);
assert.deepEqual(tokenize("1 + .5").map((token) => token.type), ["number", "operator", "number"]);
assert.throws(() => calculate("2 / 0"), /divide by zero/);
assert.throws(() => calculate("2 +"), /Incomplete expression/);

console.log("calculator app tests passed");
