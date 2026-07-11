/**
 * Async generator that parses a Server-Sent Events stream from a
 * ReadableStreamDefaultReader<Uint8Array>.
 *
 * Handles:
 * - Partial chunk accumulation across read() calls
 * - Multiple frames arriving in a single chunk
 * - Frames split across two or more chunks
 * - Malformed data fields (silently skipped)
 * - Frames without an explicit `event:` line (default event type: "message")
 */
export async function* parseSSE(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<{ event: string; data: unknown }> {
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Split on the SSE frame delimiter "\n\n"
    const frames = buffer.split("\n\n");
    // The last element is either empty or an incomplete frame — keep it
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      if (!frame.trim()) continue;

      const lines = frame.split("\n");
      let eventType = "message";
      let dataLine = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLine = line.slice(6).trim();
        }
      }

      if (!dataLine) continue; // skip frames with no data

      let parsedData: unknown;
      try {
        parsedData = JSON.parse(dataLine);
      } catch {
        // Malformed JSON — silently skip
        continue;
      }

      yield { event: eventType, data: parsedData };
    }
  }
}
