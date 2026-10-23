import { useEffect, useState } from "react";

/**
 * False on the first frame after `key` changes, true from the next one. Rendering a value at its
 * start (e.g. a bar at 0%) and then at its target lets a CSS transition animate between them.
 */
export function useRevealed(key: unknown): boolean {
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    setRevealed(false);
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setRevealed(true));
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [key]);
  return revealed;
}
