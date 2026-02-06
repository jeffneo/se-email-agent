import { useState, useEffect, useRef } from "react";

export function useSmoothStreaming(incomingText: string, speedMs: number = 10) {
  const [displayedText, setDisplayedText] = useState("");
  const indexRef = useRef(0);

  // We use a ref for the incoming text to avoid effect dependency loops
  const targetTextRef = useRef(incomingText);

  // Update target whenever the parent passes new data
  useEffect(() => {
    targetTextRef.current = incomingText;
  }, [incomingText]);

  useEffect(() => {
    const timer = setInterval(() => {
      // If we have shown everything, stop
      if (indexRef.current >= targetTextRef.current.length) {
        return;
      }

      // Calculate how many characters to add.
      // If the buffer is HUGE (e.g. pasted text), we speed up slightly to catch up.
      const bufferSize = targetTextRef.current.length - indexRef.current;

      // Variable speed:
      // If we are way behind (>50 chars), type FAST (5 chars/tick).
      // If we are close (<20 chars), type SLOW (1 char/tick) for that human feel.
      let jump = 1;
      if (bufferSize > 250)
        jump = 20; // Super catch-up for code blocks
      else if (bufferSize > 50)
        jump = 5; // Fast catch-up
      else if (bufferSize > 20) jump = 2; // Mild catch-up

      // Slice the next chunk
      const nextChunk = targetTextRef.current.slice(
        indexRef.current,
        indexRef.current + jump,
      );

      setDisplayedText((prev) => prev + nextChunk);
      indexRef.current += jump;
    }, speedMs);

    return () => clearInterval(timer);
  }, [speedMs]);

  return displayedText;
}
