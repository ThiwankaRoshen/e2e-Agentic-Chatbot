/**
 * Async generator that parses a Server-Sent Events stream from a
 * ReadableStreamDefaultReader<Uint8Array>.
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

    const frames = buffer.split("\n\n");
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

      if (!dataLine) continue;

      let parsedData: unknown;
      try {
        parsedData = JSON.parse(dataLine);
      } catch {
        continue;
      }

      yield { event: eventType, data: parsedData };
    }
  }
}
