import { describe, expect, it } from "vitest";

import { findLogKeywordMatchRanges, normalizeTerminalLogText } from "./logText";

describe("normalizeTerminalLogText", () => {
  it("renders serialized log escapes like terminal text", () => {
    expect(normalizeTerminalLogText("line 1\\n{'msg': \\'failed\\', \"code\": \\\"E_CONN\\\"}\\tend")).toBe(
      "line 1\n{'msg': 'failed', \"code\": \"E_CONN\"}\tend",
    );
  });

  it("finds standalone log words but ignores field names", () => {
    const text = "{'error': 'Token refresh failed', 'error_description': 'Client authentication failed'}";

    expect(findLogKeywordMatchRanges(text, "error").map((range) => text.slice(range.start, range.end))).toEqual(["error"]);
  });
});
