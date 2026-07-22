import { describe, expect, it } from "vitest";

import { normalizeTerminalLogText } from "./logText";

describe("normalizeTerminalLogText", () => {
  it("renders serialized log escapes like terminal text", () => {
    expect(normalizeTerminalLogText("line 1\\n{'msg': \\'failed\\', \"code\": \\\"E_CONN\\\"}\\tend")).toBe(
      "line 1\n{'msg': 'failed', \"code\": \"E_CONN\"}\tend",
    );
  });
});
