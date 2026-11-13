import { test } from "node:test";
import assert from "node:assert/strict";
import { slug } from "./slug.ts";

test("words are joined by one hyphen, in lower case", () => {
  assert.equal(slug("Juniper Bakery Proposal"), "juniper-bakery-proposal");
});

test("punctuation and runs of spaces collapse to one hyphen", () => {
  assert.equal(slug("Q3:  scope, rates & dates!"), "q3-scope-rates-dates");
});

test("accents are dropped, not the letters under them", () => {
  assert.equal(slug("Café Crème"), "cafe-creme");
});

test("nothing but punctuation gives an empty slug", () => {
  assert.equal(slug(" -- "), "");
});

test("a maximum length cuts at the last whole word that fits", () => {
  assert.equal(slug("Juniper Bakery Proposal", 20), "juniper-bakery");
});

test("a slug no longer than the maximum is unchanged", () => {
  assert.equal(slug("Juniper Bakery Proposal", 23), "juniper-bakery-proposal");
});

test("a single word longer than the maximum is cut at the maximum", () => {
  assert.equal(slug("Supercalifragilistic", 5), "super");
});

test("a word that ends exactly at the maximum is kept", () => {
  assert.equal(slug("Juniper Bakery Proposal", 14), "juniper-bakery");
});

test("a maximum that lands just after a hyphen drops the hyphen", () => {
  assert.equal(slug("Juniper Bakery Proposal", 15), "juniper-bakery");
});

test("a maximum only shortens the slug, never changes its characters", () => {
  assert.equal(
    slug("Q3:  scope, rates & dates!", 100),
    slug("Q3:  scope, rates & dates!"),
  );
  assert.equal(slug("Café Crème", 4), "cafe");
});

for (const bad of [0, -1, 2.5, NaN]) {
  test(`a maximum of ${bad} throws a RangeError naming it`, () => {
    assert.throws(
      () => slug("Juniper", bad),
      (e) => e instanceof RangeError && e.message.includes(String(bad)),
    );
  });
}
