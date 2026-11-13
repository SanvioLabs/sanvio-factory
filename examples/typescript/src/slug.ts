// A title as a URL slug: lower case, accents dropped, anything else between
// words turned into one hyphen.
//
// With maxLength, the slug is at most that many characters. It's cut at the
// last whole word that fits, with no trailing hyphen, and a single word longer
// than the limit is cut at the limit. A maxLength that isn't a positive whole
// number throws a RangeError.
export function slug(title: string, maxLength?: number): string {
  if (
    maxLength !== undefined &&
    (!Number.isInteger(maxLength) || maxLength < 1)
  ) {
    throw new RangeError(
      `maxLength must be a positive whole number, got ${maxLength}`,
    );
  }
  const full = title
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (maxLength === undefined || full.length <= maxLength) {
    return full;
  }
  const cut = full.slice(0, maxLength);
  if (full[maxLength] === "-") {
    return cut;
  }
  const lastHyphen = cut.lastIndexOf("-");
  if (lastHyphen > 0) {
    return cut.slice(0, lastHyphen);
  }
  return cut;
}
