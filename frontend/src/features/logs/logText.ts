export function normalizeTerminalLogText(value: string) {
  return value
    .replaceAll("\\r\\n", "\n")
    .replaceAll("\\n", "\n")
    .replaceAll("\\t", "\t")
    .replaceAll('\\"', '"')
    .replaceAll("\\'", "'");
}

export type LogKeywordMatchRange = {
  start: number;
  end: number;
};

export function findLogKeywordMatchRanges(text: string, keyword: string): LogKeywordMatchRange[] {
  const normalizedKeyword = keyword.trim();
  if (!normalizedKeyword) {
    return [];
  }

  const lowerText = text.toLowerCase();
  const lowerKeyword = normalizedKeyword.toLowerCase();
  const ranges: LogKeywordMatchRange[] = [];
  let cursor = 0;
  let index = lowerText.indexOf(lowerKeyword, cursor);

  while (index !== -1) {
    const end = index + normalizedKeyword.length;
    if (!requiresTokenBoundary(normalizedKeyword) || hasTokenBoundary(text, index, end)) {
      ranges.push({ start: index, end });
    }
    cursor = end;
    index = lowerText.indexOf(lowerKeyword, cursor);
  }

  return ranges;
}

function requiresTokenBoundary(keyword: string) {
  return /^[A-Za-z][A-Za-z0-9_]*$/.test(keyword);
}

function hasTokenBoundary(text: string, start: number, end: number) {
  return !isWordCharacter(text[start - 1]) && !isWordCharacter(text[end]);
}

function isWordCharacter(value: string | undefined) {
  return value !== undefined && /[A-Za-z0-9_]/.test(value);
}
