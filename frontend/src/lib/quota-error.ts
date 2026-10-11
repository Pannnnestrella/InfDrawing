/** Detect balance/quota failures in user-facing error strings. */

const QUOTA_PATTERNS: RegExp[] = [
  /arrearage/i,
  /insufficient[_\s-]?balance/i,
  /insufficient[_\s-]?quota/i,
  /allocation.?quota/i,
  /free.?tier/i,
  /billing_not_active/i,
  /exceeded.?your.?current.?quota/i,
  /quota.?exceeded/i,
  /余额不足/,
  /欠费/,
  /可用额度/,
  /免费额度/,
  /余额或额度不足/,
  /请充值后重试/,
];

export function isQuotaErrorMessage(message: string): boolean {
  const text = message.trim();
  if (!text) return false;
  return QUOTA_PATTERNS.some((pattern) => pattern.test(text));
}
