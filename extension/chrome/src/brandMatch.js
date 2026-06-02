export function normalizeRequiredBrand(brand) {
  return String(brand || "").trim();
}

export function hasBrandMatch(offers, brand) {
  const needles = brandNeedles(brand);
  if (needles.length === 0) return true;
  return offers.some((offer) => {
    const text = `${offer.title || ""} ${offer.brand || ""} ${offer.specText || ""}`.toLowerCase();
    return needles.some((needle) => text.includes(needle));
  });
}

export function brandNeedles(brand) {
  const normalized = brand.toLowerCase().replace(/\s+/g, "");
  const aliases = {
    美和: ["toho", "美和toho"],
    诺霸: ["norbar", "英国诺霸"],
  };
  return [normalized, ...(aliases[normalized] || [])].filter(Boolean);
}
