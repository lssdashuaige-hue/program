export function safeNextPath(
  value: string | null | undefined,
  fallback = "/explore",
): string {
  if (
    !value?.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  ) {
    return fallback;
  }

  try {
    const base = new URL("https://pas.invalid");
    const destination = new URL(value, base);

    if (destination.origin !== base.origin) {
      return fallback;
    }

    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return fallback;
  }
}
